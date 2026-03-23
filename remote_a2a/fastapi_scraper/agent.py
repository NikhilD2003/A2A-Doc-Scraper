import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from google.adk.agents.llm_agent import Agent

load_dotenv(find_dotenv())

api_key = os.getenv("OPENROUTER_API_KEY")
if api_key:
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
    print("✅ SUCCESS: OpenRouter API Key loaded and routed!")
else:
    print("❌ CRITICAL ERROR: OPENROUTER_API_KEY missing from .env!")

from .tools import crawl_site, build_documentation

SYSTEM_INSTRUCTION = """
You are a Documentation Reconstruction Agent.

WORKFLOW
1. Call the tool: `crawl_site(url)`
2. After crawling completes, call the tool: `build_documentation(url)` using the EXACT same URL.

RULES
• Do NOT attempt to write or output the Markdown text yourself. 
• The system saves the file automatically in the background.
• When the tools finish, reply ONLY with the exact phrase: "Process Complete."
"""

root_agent = Agent(
    name="documentation_builder",
    instruction=SYSTEM_INSTRUCTION,
    tools=[crawl_site, build_documentation],
    model="openai/nvidia/nemotron-3-nano-30b-a3b:free"
)