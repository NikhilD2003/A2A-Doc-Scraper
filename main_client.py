import os
import asyncio
from urllib.parse import urlparse

# Set LiteLLM debug environment variable before other imports
os.environ['LITELLM_LOG'] = 'DEBUG'

from google.adk.runners import InMemoryRunner
from google.genai import types

from remote_a2a.fastapi_scraper.agent import root_agent
# --- FIX: Import the state so we can grab the markdown directly! ---
from remote_a2a.fastapi_scraper.tools import state

async def main():
    url = input("Enter documentation website: ")

    runner = InMemoryRunner(
        agent=root_agent,
        app_name="doc_builder"
    )

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

    # Run the agent (we ignore its text output now to prevent hallucination issues)
    async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message
    ):
        pass

    parsed = urlparse(url)
    parts = parsed.netloc.split(".")
    if parts[0] in ["www", "docs"]:
        site = parts[1]
    else:
        site = parts[0]

    # --- FIX: Pull the markdown from memory, NOT the LLM's hallucinated chat output ---
    result_text = state.final_markdown
    if not result_text:
        result_text = "# Error\nNo Markdown was generated. Please check the crawler logs."

    os.makedirs("generated_docs", exist_ok=True)

    path = f"generated_docs/{site}.md"

    with open(path, "w", encoding="utf-8") as f:
        f.write(result_text)

    print("Documentation saved to:", path)


if __name__ == "__main__":
    asyncio.run(main())