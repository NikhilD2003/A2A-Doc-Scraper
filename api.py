import os
import json
import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# NEW: Use the native Google GenAI client instead of OpenAI
from google import genai
from google.genai import types
from google.adk.runners import InMemoryRunner

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
print(f"API Key Loaded: {bool(os.getenv('GEMINI_API_KEY'))}")

from remote_a2a.fastapi_scraper.agent import root_agent
from remote_a2a.fastapi_scraper.tools import progress_queue, state

try:
    from database.graph_manager import db
except ModuleNotFoundError:
    from database.graph_manager import db

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

        context = "\n".join([p["content"] for p in pages if p.get("content")])

        # Native Google GenAI Client
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        system_prompt = f"""
        You are a helpful and expert AI assistant for the documentation found at {req.url}.

        Instructions:
        1. GREETINGS & CHAT: If the user says "hello", "hi", "how are you", or asks who you are, respond politely and introduce yourself as the Documentation Assistant for {req.url}. Ask how you can help them with the documentation today.
        2. DOCUMENTATION QUESTIONS: For technical or specific questions, answer them based STRICTLY on the provided Documentation Context below.
        3. OFF-TOPIC: If the user asks a specific question and the answer is not in the context, say "I cannot find the answer in the provided documentation." Do not hallucinate outside information.

        Documentation Context (Truncated to fit):
        {context[:60000]}
        """

        # Using the async client directly from the Google SDK
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=req.question,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2 # Keep it strictly factual for docs
            )
        )

        return {"answer": response.text}

    except Exception as e:
        return {"answer": f"Error communicating with AI: {str(e)}"}