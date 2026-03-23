from google.adk.agents.llm_agent import Agent
from dotenv import load_dotenv
from pathlib import Path
import os
from dotenv import load_dotenv, find_dotenv
# Import tools
load_dotenv(find_dotenv())

# Import tools (Must happen after environment is loaded)
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
    # 100% Native Google Model. No litellm required!
    model="gemini-2.0-flash"
)