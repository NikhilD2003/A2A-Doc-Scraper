from google.adk.agents.llm_agent import Agent
from dotenv import load_dotenv
from pathlib import Path
import os

# Import tools
from .tools import crawl_site, build_documentation


# ---------------------------------------------------
# LOAD ENVIRONMENT VARIABLES FROM PROJECT ROOT
# ---------------------------------------------------

# Determine project root (two levels up from this file)
ROOT_DIR = Path(__file__).resolve().parents[2]

# Load .env from root directory
load_dotenv(ROOT_DIR / ".env")

# Configure OpenRouter as OpenAI-compatible API
os.environ["OPENAI_API_KEY"] = os.getenv("OPENROUTER_API_KEY")
os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"


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
• CRITICAL: DO NOT include any conversational text, internal reasoning, greetings, or explanations (e.g., do not say "The user asked...", "Here is the documentation...", or "I will now..."). 
• Your entire output must begin with the Markdown heading and contain nothing else.
"""


# ---------------------------------------------------
# AGENT DEFINITION
# ---------------------------------------------------

root_agent = Agent(
    name="documentation_builder",
    instruction=SYSTEM_INSTRUCTION,
    tools=[crawl_site, build_documentation],

    # OpenRouter model through OpenAI-compatible API
    model="openai/nvidia/nemotron-3-nano-30b-a3b:free"
)