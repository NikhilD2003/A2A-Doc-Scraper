import asyncio
import json
import os
import re
from dotenv import load_dotenv

# 🚨 CRITICAL FIX: Load the environment variables BEFORE importing the database
load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI

# Now that the password is loaded, we can safely import the database!
from database.graph_manager import db
from google.adk.runners import InMemoryRunner
from google.genai import types
from remote_a2a.fastapi_scraper.agent import root_agent
from remote_a2a.fastapi_scraper.tools import state, progress_queue

# ==========================================
# ☑️ THE STARTUP CHECKBOX
# ==========================================
print("\n" + "=" * 50)
if os.getenv("OPENROUTER_API_KEY"):
    print("☑️  [CHECKBOX] OpenRouter API Key successfully loaded!")
else:
    print("⚠️  [WARNING] OpenRouter API Key is MISSING from your .env file!")
print("=" * 50 + "\n")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    url: str
    question: str


@app.post("/api/chat")
async def chat_with_docs(req: ChatRequest):
    try:
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )

        model_name = "nvidia/nemotron-3-super-120b-a12b:free"

        print(f"\n🔌 Connected to Cloud AI at: {client.base_url}")
        print(f"🧠 Using OpenRouter model: {model_name}")

        # ==========================================
        # STAGE 0: READ THE KNOWLEDGE GRAPH
        # ==========================================
        graph_map = db.get_graph_summary(req.url)
        print(f"🗺️ Graph Map Loaded: {len(graph_map.split(','))} topics found.")

        # ==========================================
        # STAGE 1: GRAPH-AWARE KEYWORD EXTRACTION
        # ==========================================
        keyword_prompt = f"""
        You are a highly precise search engine indexer. Extract 1 to 5 highly specific technical keywords from the user's question. 

        CRITICAL RULES:
        1. ALWAYS extract ALL acronyms, proper nouns, and frameworks (e.g., 'MCP', 'API', 'a2a', 'TaskStore').
        2. IGNORE generic conversational words: 'what', 'is', 'how', 'compare', 'difference', 'between', 'protocol'.
        3. If the user asks for a comparison (e.g., "A2A vs MCP"), you MUST extract BOTH technologies: ["a2a", "mcp"].
        4. Return ONLY a valid JSON array of strings. Example: ["mcp", "a2a"]

        USER QUESTION: "{req.question}"
        """

        keyword_response = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": keyword_prompt}]
        )

        raw_output = keyword_response.choices[0].message.content.strip()

        # 1. Safely parse the AI's JSON response
        try:
            clean_output = raw_output.replace('```json', '').replace('```', '').strip()
            keywords = json.loads(clean_output)
            if not isinstance(keywords, list):
                keywords = []
        except json.JSONDecodeError:
            keywords = []

        # 2. 🚨 THE SAFETY NET: Upgraded for better acronym capture
        if not keywords or len(keywords) == 0:
            print("⚠️ AI returned empty keywords. Falling back to raw question extraction...")
            # Capture words 3 letters or longer, including numbers/hyphens
            fallback_words = re.findall(r'\b[a-zA-Z0-9-]{3,}\b', req.question)

            banned_words = {
                'what', 'how', 'why', 'who', 'the', 'this', 'that', 'and', 'for',
                'protocol', 'agent', 'implement', 'compare', 'difference', 'between', 'with'
            }
            filtered_fallback = [w for w in fallback_words if w.lower() not in banned_words]

            keywords = filtered_fallback[:4] if filtered_fallback else ["a2a"]

        keywords = [str(k).lower().replace("'", "\\'").strip() for k in keywords]
        print(f"🧠 Final Extracted Keywords: {keywords}")

        # ==========================================
        # STAGE 2: DYNAMIC TOPIC SCORING
        # ==========================================
        where_conditions = []
        score_conditions = []

        for kw in keywords:
            where_conditions.append(f"(toLower(t.url) CONTAINS '{kw}' OR toLower(t.content) CONTAINS '{kw}')")
            score_conditions.append(
                f"(CASE WHEN toLower(t.url) CONTAINS '{kw}' THEN 2 ELSE 0 END) + "
                f"(CASE WHEN toLower(t.content) CONTAINS '{kw}' THEN 1 ELSE 0 END)"
            )

        where_clause = " OR ".join(where_conditions)
        score_calculation = " + ".join(score_conditions)

        target_url = req.url.rstrip('/')
        raw_cypher = f"""
        MATCH (t:Topic) 
        WHERE (t.url CONTAINS '{target_url}') 
          AND ({where_clause})

        WITH t, ({score_calculation}) AS match_score
        RETURN t.url, substring(t.content, 0, 35000) AS content 
        ORDER BY match_score DESC, id(t) DESC 
        LIMIT 10
        """

        print(f"🤖 Assembled Cypher:\n{raw_cypher.strip()}")

        db_results = db.execute_read_query(raw_cypher)

        cleaned_results = [r for r in db_results if r.get('content') and len(r['content']) > 50]
        retrieved_context = json.dumps(cleaned_results, indent=2)

        # TEXT SANITIZER
        retrieved_context = re.sub(r'\\u[a-fA-F0-9]{4}', '', retrieved_context)
        retrieved_context = re.sub(r'\[#\]\(#.*?\)', '', retrieved_context)
        retrieved_context = retrieved_context.replace('\\n', '\n').replace('\\"', '"')

        print(f"📊 Neo4j returned {len(db_results)} pages. Cleaned down to {len(cleaned_results)} readable pages.")

        if not cleaned_results:
            return {"answer": "The official documentation does not provide a code implementation for this."}

        # ==========================================
        # STAGE 3: FINAL ANSWER GENERATION
        # ==========================================
        answer_prompt = f"""
        You are an expert Technical Educator. Your goal is to explain complex software documentation.
        You MUST base your answer strictly on the DATABASE CONTEXT below.

        CRITICAL CODE RULE (ANTI-HALLUCINATION):
        You have exactly two options when a user asks about code, implementation, or technical logic:
        OPTION 1: If the DATABASE CONTEXT contains the exact code blocks or JSON schemas, quote them exactly as they appear.
        OPTION 2: If the DATABASE CONTEXT does not contain a specific code example, you MUST output this exact phrase and stop writing: "The official documentation does not provide a code implementation for this."

        GENERAL INSTRUCTIONS:
        1. REQUIRED STRUCTURE: Start with a summary, use bullet points for the mechanics, and end with a conclusion.
        2. STRICT ACCURACY: Base every single claim about security, architecture, or logic ONLY on the provided text.

        DATABASE CONTEXT:
        {retrieved_context}
        """

        final_response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": answer_prompt},
                {"role": "user", "content": req.question}
            ]
        )

        raw_answer = final_response.choices[0].message.content.strip()

        denial_triggers = [
            "FAIL_PHRASE_TRIGGERED",
            "I couldn't find",
            "I cannot find",
            "not explicitly mentioned",
            "no information provided"
        ]

        if any(trigger in raw_answer for trigger in denial_triggers):
            return {"answer": "I couldn't find the exact answer in the database."}

        return {"answer": raw_answer}

    except Exception as e:
        return {"answer": f"Error in AI Pipeline: {str(e)}"}


# ==========================================
# 🚀 THE WEBSOCKET SCRAPER PIPELINE
# ==========================================
@app.websocket("/ws")
async def websocket_scraper(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket connection accepted!")

    async def log_reader():
        try:
            while True:
                msg = await progress_queue.get()
                await websocket.send_text(msg)
                progress_queue.task_done()
        except asyncio.CancelledError:
            pass

    log_task = asyncio.create_task(log_reader())

    try:
        data = await websocket.receive_text()
        payload = json.loads(data)
        url = payload.get("url")

        await websocket.send_text(f"🚀 Initializing ADK Agent Runner for: {url}")

        runner = InMemoryRunner(agent=root_agent, app_name="doc_builder")
        user_id = "local_user"
        session_id = "doc_session"

        await runner.session_service.create_session(
            app_name="doc_builder",
            user_id=user_id,
            session_id=session_id
        )

        message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"Build documentation for {url}")]
        )

        async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message
        ):
            pass

        result_text = state.final_markdown
        if not result_text:
            result_text = "# Error\nNo Markdown was generated. Check backend logs."

        site_name = url.split("://")[-1].split("/")[0]
        download_payload = {
            "type": "download",
            "filename": f"{site_name}_docs.md",
            "content": result_text
        }
        await websocket.send_text(json.dumps(download_payload))
        await websocket.send_text("DONE")

    except WebSocketDisconnect:
        print("⚠️ React Client disconnected mid-scrape.")
    except Exception as e:
        await websocket.send_text(f"❌ Pipeline Error: {str(e)}")
        print(f"Error: {str(e)}")
    finally:
        log_task.cancel()


# ==========================================
# 🕸️ KNOWLEDGE GRAPH ENDPOINT
# ==========================================
@app.get("/api/graph")
async def health_check():
    return {"status": "awake", "message": "A2A Scraper Backend is live!"}
async def get_graph(url: str):
    try:
        graph_data = db.get_graph_data(url)
        return graph_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 🚀 DEPLOYMENT CONFIG (Render)
# ==========================================
if __name__ == "__main__":
    import uvicorn

    # Render assigns a dynamic port via the PORT env variable
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)