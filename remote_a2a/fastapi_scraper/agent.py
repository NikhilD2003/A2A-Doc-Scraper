import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from google.adk.agents.llm_agent import Agent

# 1. Securely load the .env file
load_dotenv(find_dotenv())

# 2. The OpenRouter Trojan Horse
api_key = os.getenv("OPENROUTER_API_KEY")
if api_key:
    # We trick the system into thinking it's using OpenAI, but route it to OpenRouter!
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
    print("✅ SUCCESS: OpenRouter API Key loaded and routed!")
else:
    print("❌ CRITICAL ERROR: OPENROUTER_API_KEY missing from .env!")

# 3. Import tools
from .tools import crawl_site, build_documentation

# 4. Agent Instructions
SYSTEM_INSTRUCTION = """
You are a Documentation Reconstruction Agent.
Your task is to build a complete documentation file for any website.

WORKFLOW
1. Call the tool: `crawl_site(url)`
2. After crawling completes call: `build_documentation(url)`

RULES
• ONLY use content extracted from the website.
• Output ONLY the exact Markdown returned by the `build_documentation` tool.
"""

# 5. Agent Definition
root_agent = Agent(
    name="documentation_builder",
    instruction=SYSTEM_INSTRUCTION,
    tools=[crawl_site, build_documentation],
    # MUST have the openai/ prefix for the litellm workaround!
    model="openai/nvidia/nemotron-3-nano-30b-a3b:free"
)