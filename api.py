import os
import json
import asyncio
from urllib.parse import urlparse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

os.environ['LITELLM_LOG'] = 'DEBUG'

from google.adk.runners import InMemoryRunner
from google.genai import types

from remote_a2a.fastapi_scraper.agent import root_agent
from remote_a2a.fastapi_scraper.tools import progress_queue, state

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

        await websocket.send_text(f"🚀 Starting A2A pipeline for: {url}")

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
            parts=[types.Part.from_text(text=f"Build documentation for {url}")]
        )

        # Clear out any old memory from previous runs
        state.final_markdown = ""

        await progress_queue.put("🧠 Agent initialized, planning workflow...")

        # Run the AI
        async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message
        ):
            pass

            # Grab pristine text directly from the Tool's secure memory
        await progress_queue.put("💾 Packaging file for download...")

        parsed = urlparse(url)
        parts = parsed.netloc.split(".")
        if len(parts) > 1 and parts[0] in ["www", "docs"]:
            site = parts[1]
        else:
            site = parts[0]

        # Get the perfect markdown file!
        result_text = state.final_markdown

        # Failsafe if the scrape was entirely empty
        if not result_text:
            result_text = "# Error\nNo text was found."

        # NEW: Send the file data back to React to trigger the Save popup
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