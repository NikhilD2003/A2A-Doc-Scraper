import os
import json
import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai

os.environ['LITELLM_LOG'] = 'DEBUG'

from google.adk.runners import InMemoryRunner
from google.genai import types

from remote_a2a.fastapi_scraper.agent import root_agent
from remote_a2a.fastapi_scraper.tools import progress_queue, state

# Import the graph manager so the API can fetch the Graph and Chat data
try:
    from database.graph_manager import db
except ModuleNotFoundError:
    from graph_manager import db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    reader_task = None
    try:
        data = await websocket.receive_text()
        config = json.loads(data)
        url = config.get("url")
        limit = config.get("limit", 500)

        await websocket.send_text(f"🚀 Starting A2A pipeline for: {url} (Limit: {limit} pages)")

        async def queue_reader():
            while True:
                msg = await progress_queue.get()
                if msg == "DONE":
                    break
                await websocket.send_text(msg)

        reader_task = asyncio.create_task(queue_reader())

        runner = InMemoryRunner(agent=root_agent, app_name="doc_builder")
        user_id = "local_user"
        session_id = "doc_session"

        await runner.session_service.create_session(
            app_name="doc_builder", user_id=user_id, session_id=session_id
        )

        message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"Build documentation for {url} with a maximum page limit of {limit}.")]
        )

        state.final_markdown = ""
        await progress_queue.put("🧠 Agent initialized, planning workflow...")

        async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message
        ):
            pass

        await progress_queue.put("💾 Packaging file for download...")

        parsed = urlparse(url)
        parts = parsed.netloc.split(".")
        if len(parts) > 1 and parts[0] in ["www", "docs"]:
            site = parts[1]
        else:
            site = parts[0]

        result_text = state.final_markdown
        if not result_text:
            result_text = "# Error\nNo text was found."

        file_payload = {
            "type": "download",
            "filename": f"{site}_docs.md",
            "content": result_text
        }
        await websocket.send_text(json.dumps(file_payload))

        await progress_queue.put("DONE")
        await reader_task
        await websocket.close()

    except WebSocketDisconnect:
        print("React dashboard disconnected.")
        if reader_task:
            reader_task.cancel()
    except Exception as e:
        print(f"Server Error: {str(e)}")
        if reader_task:
            reader_task.cancel()
        try:
            await websocket.send_text(f"❌ ERROR: {str(e)}")
            await websocket.close()
        except:
            pass


# ------------------------------------------------------------------
# --- GRAPH VISUALIZATION AND CHAT API ENDPOINTS ---
# ------------------------------------------------------------------

class ChatRequest(BaseModel):
    url: str
    question: str


@app.get("/api/graph")
async def get_graph(url: str):
    try:
        data = db.get_graph_data(url)
        return data
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/chat")
async def chat_with_docs(req: ChatRequest):
    try:
        pages = db.get_all_topics(req.url)
        if not pages:
            return {"answer": "No documentation found for this URL. Please scrape it first!"}

        # THE FIX: We added `if p.get("content")` to safely skip blank nodes!
        context = "\n".join([p["content"] for p in pages if p.get("content")])

        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = f"""
        You are an expert AI assistant. Answer the user's question based strictly on the provided documentation context.
        If the answer is not in the context, say "I cannot find the answer in the provided documentation."

        Context (Truncated to fit):
        {context[:60000]}

        Question: {req.question}
        """

        response = model.generate_content(prompt)
        return {"answer": response.text}

    except Exception as e:
        return {"answer": f"Error communicating with AI: {str(e)}"}