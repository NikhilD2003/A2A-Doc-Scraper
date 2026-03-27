import os
from dotenv import load_dotenv, find_dotenv
from google.adk.agents.llm_agent import Agent

load_dotenv(find_dotenv())

# 🔌 Reroute everything to OpenRouter Cloud
os.environ["OPENAI_API_KEY"] = os.getenv("OPENROUTER_API_KEY")
os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"

# Import our new combined tool!
from .tools import run_full_pipeline

SYSTEM_INSTRUCTION = """
You are a Documentation Reconstruction Agent.

WORKFLOW:
1. You have exactly one tool: `run_full_pipeline(url)`.
2. Call it using the URL provided by the user.
3. When the tool finishes, reply ONLY with: "Process Complete."
"""

root_agent = Agent(
    name="documentation_builder",
    instruction=SYSTEM_INSTRUCTION,
    tools=[run_full_pipeline],
    # 👇 Changed prefix to 'openai/' to bypass the LiteLLM requirement
    model="openai/nvidia/nemotron-3-super-120b-a12b:free"
)