import os
import json
import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv

# 1. Securely load the .env file
load_dotenv(find_dotenv())

from google.adk.runners import InMemoryRunner
from google.genai import types

from remote_a2a.fastapi_scraper.agent import root_agent
from remote_a2a.fastapi_scraper.tools import progress_queue, state

# Import the graph manager so the API can fetch the Graph and Chat data
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

        # --- NEW: TRIGGER THE WIPE BEFORE SCRAPING ---
        await websocket.send_text("🧹 Wiping previous Knowledge Graph from Neo4j...")
        db.clear_database()
        # ----------------------------------------------

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
        from openai import AsyncOpenAI
        import json

        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )

        # ==========================================
        # STAGE 1: TEXT-TO-CYPHER GENERATION
        # ==========================================
        cypher_prompt = f"""
        You are an expert Neo4j Database Engineer.
        Your task is to convert the user's question into a Cypher query to search a documentation database.

        GRAPH SCHEMA:
        - Node Label: `Topic`
        - Properties: `url` (String), `content` (String containing markdown text)

        RULES:
        1. The target documentation URL is: {req.url}
        2. ALWAYS filter by `url STARTS WITH '{req.url}'` so you only search this specific website.
        3. KEYWORD EXTRACTION: Do not search for long phrases. Extract 1 or 2 core keywords. (e.g., "life of a task" -> search for "task" and "life").
        4. THE SEARCH LOGIC: You must search BOTH the URL and the content using OR logic. 
           Example: `(toLower(n.content) CONTAINS "life" OR toLower(n.url) CONTAINS "life")`
        5. LIMIT your results to 3 to avoid overwhelming the context window.
        6. Return ONLY the raw Cypher query. NO markdown formatting, NO backticks, NO explanations. Just the query.

        USER QUESTION: {req.question}
        """

        cypher_response = await client.chat.completions.create(
            model="google/gemini-2.0-flash-lite-preview-02-05:free",
            messages=[{"role": "user", "content": cypher_prompt}],
            extra_headers={"HTTP-Referer": "https://a2a-doc-scraper.com", "X-Title": "A2A Doc Scraper"}
        )

        raw_cypher = cypher_response.choices[0].message.content.strip()
        raw_cypher = raw_cypher.replace("```cypher", "").replace("```", "").strip()

        print(f"🤖 Generated Cypher: {raw_cypher}")

        # ==========================================
        # STAGE 2: DATABASE EXECUTION
        # ==========================================
        db_results = db.execute_read_query(raw_cypher)
        retrieved_context = json.dumps(db_results, indent=2)

        # ==========================================
        # STAGE 3: FINAL ANSWER GENERATION
        # ==========================================
        answer_prompt = f"""
        You are a friendly, expert AI documentation assistant for {req.url}.

        Instructions:
        1. TONE & GREETING: Always start with a warm, friendly greeting (e.g., "Hello!", "Hi there!", or "I can definitely help with that!"). Speak naturally and conversationally, acting as a helpful guide.
        2. ANSWERING: After your greeting, answer the user's question based STRICTLY on the Database Results provided below. Keep the technical explanation precise and easy to understand.
        3. FALLBACK: If the Database Results contain an error or are empty, politely state: "I couldn't find the exact answer in the database." Do not hallucinate or guess.

        CRITICAL FORMATTING RULES:
        - You MUST use beautiful, strict GitHub Flavored Markdown (GFM).
        - TABLES: ALWAYS leave a blank empty line before AND after any table. 
        - LISTS: Use bullet points heavily to break up chunky text. Always leave a blank line before starting a list.
        - SPACING: Use blank lines to separate all paragraphs. Never output giant walls of text.
        - HIGHLIGHTING: Use `inline code blocks` for technical terms, variable names, or specific states (like `working`).
        - BOLDING: Bold **key concepts** and **headers** for scannability.

        Database Results:
        {retrieved_context}
        """

        final_response = await client.chat.completions.create(
            model="openai/nvidia/nemotron-3-nano-30b-a3b:free",
            messages=[
                {"role": "system", "content": answer_prompt},
                {"role": "user", "content": req.question}
            ],
            extra_headers={"HTTP-Referer": "https://a2a-doc-scraper.com", "X-Title": "A2A Doc Scraper"}
        )

        return {"answer": final_response.choices[0].message.content}

    except Exception as e:
        return {"answer": f"Error in AI Pipeline: {str(e)}"}