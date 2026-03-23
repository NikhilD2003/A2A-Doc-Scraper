import os
from pathlib import Path
from dotenv import load_dotenv
from google.adk.agents.llm_agent import Agent

# ---------------------------------------------------
# THE "LOUD" SECURE LOADER
# ---------------------------------------------------
# 1. Get the absolute directory of where agent.py lives
CURRENT_DIR = Path(__file__).resolve().parent

# 2. Go up to the root folder (Assuming agent.py is in remote_a2a/fastapi_scraper/)
ROOT_DIR = CURRENT_DIR.parent.parent
ENV_PATH = ROOT_DIR / ".env"

# 3. Print the exact path to the terminal so we can see it!
print(f"🔍 DEBUG: Searching for .env file at -> {ENV_PATH}")

# 4. Force load that exact file
load_dotenv(dotenv_path=ENV_PATH)

# 5. Verify it worked before the ADK even tries to boot up
if not os.getenv("GEMINI_API_KEY"):
    print("❌ CRITICAL ERROR: API Key is STILL empty. The .env file is not at the path above!")
else:
    print("✅ SUCCESS: API Key loaded securely into agent.py!")

# ---------------------------------------------------
# IMPORT TOOLS (MUST HAPPEN AFTER ENV IS LOADED)
# ---------------------------------------------------
from .tools import crawl_site, build_documentation

# ---------------------------------------------------
# SYSTEM INSTRUCTION
# ---------------------------------------------------
SYSTEM_INSTRUCTION = """
You are a Documentation Reconstruction Agent.

Your task is to build a complete documentation file for any website.

WORKFLOW
1. The user provides a documentation website URL.
2. Call the tool: `crawl_site(url)`
3. After crawling completes call: `build_documentation(url)`

RULES
• ONLY use content extracted from the website.
• Do not hallucinate documentation that does not exist.
• Preserve headings, code examples, and structure.
• Output ONLY the exact Markdown returned by the `build_documentation` tool.
• CRITICAL: DO NOT include any conversational text, internal reasoning, greetings, or explanations. 
• Your entire output must begin with the Markdown heading and contain nothing else.
"""

# ---------------------------------------------------
# AGENT DEFINITION
# ---------------------------------------------------
root_agent = Agent(
    name="documentation_builder",
    instruction=SYSTEM_INSTRUCTION,
    tools=[crawl_site, build_documentation],
    model="gemini-2.0-flash"
)