import os
import asyncio
from urllib.parse import urlparse

# Set LiteLLM debug environment variable before other imports
os.environ['LITELLM_LOG'] = 'DEBUG'

from google.adk.runners import InMemoryRunner
from google.genai import types

from remote_a2a.fastapi_scraper.agent import root_agent


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

    result_text = ""

    async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message
    ):

        if event.is_final_response() and event.content and event.content.parts:
            result_text = event.content.parts[0].text

    parsed = urlparse(url)

    # Match the get_site_name logic from tools.py to ensure the heading text matches exactly
    parts = parsed.netloc.split(".")
    if parts[0] in ["www", "docs"]:
        site_name_for_heading = parts[1]
    else:
        site_name_for_heading = parts[0]

    site = parts[0]  # Keeping your original file naming logic unchanged

    # --- START OF NEW CLEANUP LOGIC ---
    expected_heading = f"# {site_name_for_heading.capitalize()} Documentation"

    # Use rfind() to find the LAST occurrence of the heading,
    # skipping over any internal monologue where the LLM quotes it.
    start_index = result_text.rfind(expected_heading)

    if start_index != -1:
        result_text = result_text[start_index:]

    # Remove markdown code block wrappers if the LLM wrapped the whole response
    if result_text.startswith("```markdown\n"):
        result_text = result_text[12:]
    elif result_text.startswith("```\n"):
        result_text = result_text[4:]

    if result_text.endswith("\n```"):
        result_text = result_text[:-4]
    # --- END OF NEW CLEANUP LOGIC ---

    os.makedirs("generated_docs", exist_ok=True)

    path = f"generated_docs/{site}.md"

    with open(path, "w", encoding="utf-8") as f:
        f.write(result_text)

    print("Documentation saved to:", path)


if __name__ == "__main__":
    asyncio.run(main())