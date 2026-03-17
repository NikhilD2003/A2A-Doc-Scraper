# 🧠 A2A Documentation Scraper: Codebase Deep Dive

This document provides a detailed, section-by-section breakdown of the Python backend powering the Agentic Documentation Scraper. The system is split into five distinct files, each handling a specific layer of the architecture: Database, Scraping, AI Logic, API Gateway, and the Execution Runner.

---

## 1. 💾 `graph_manager.py` (The Memory Layer)

This file is responsible for all interactions with the Neo4j Graph Database. Instead of storing web pages in flat SQL tables, it stores them as **Nodes** and the hyperlinks between them as **Relationships**.

### Breakdown of Functions:

* **`__init__(self)` & `close(self)`:**
  * *What it does:* Uses the `neo4j` Python driver to authenticate and connect to your cloud database using the `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` environment variables.

* **`upsert_topic(self, url, content)`:**
  * *What it does:* Saves a scraped webpage to the database.
  * *Line-by-line logic:* It uses a Cypher `MERGE (t:Topic {url: $url})` command.
  * *Why we did it:* `MERGE` is critical. If we used `CREATE`, scraping a page twice would create duplicate nodes. `MERGE` acts like an "upsert"—if the URL exists, it grabs it; if not, it creates it. Then `SET t.content = $content` updates the markdown, ensuring no duplicate data.

* **`link_topics_batch(self, source, targets)`:**
  * *What it does:* Draws the arrows (relationships) between a parent page and all the links found on that page.
  * *Line-by-line logic:* It takes a list of URLs (`targets`). It uses `UNWIND $targets AS target` to loop through the list *inside* the database engine, and creates a `[:REFERENCES]` arrow from the source to each target.
  * *Why we did it:* Looping through database inserts in Python over a network is very slow. Sending one large batch array to Neo4j and letting it `UNWIND` the data natively is exponentially faster.

* **`get_all_topics(self, target_url)`:**
  * *What it does:* Retrieves all scraped Markdown text for the RAG Chatbot.
  * *Line-by-line logic:* It executes `MATCH (t:Topic) WHERE t.url STARTS WITH $target_url RETURN t.content`.
  * *Why we did it:* This is the **Anti-Leak Filter**. If you scrape `fastapi.com` and then chat with it, this `STARTS WITH` clause ensures the AI doesn't accidentally read older data you scraped from `a2a-protocol.org`.

* **`get_graph_data(self, target_url)`:**
  * *What it does:* Formats data specifically for the React Frontend's Knowledge Graph.
  * *Line-by-line logic:* It finds all nodes and relationships connected to the target URL. It loops through the Neo4j `Result` object and packages it into a strict JSON format: `{"nodes": [{"id": "url"}], "links": [{"source": "url1", "target": "url2"}]}`.

---

## 2. 🕷️ `tools.py` (The Scraper Engine)

This file contains the "Tools" that the AI Agent is allowed to use. It handles the raw HTTP networking and HTML parsing.

### Breakdown of Functions:

* **`normalize_url(url)`:**
  * *What it does:* Cleans up messy URLs.
  * *Line-by-line logic:* It uses `urllib.parse` to strip out `#fragments` (anchor links) and trailing slashes (`/`).
  * *Why we did it:* A crawler can get stuck in an infinite loop if it thinks `site.com/docs` and `site.com/docs/` are two different pages. Normalization ensures they are treated as the exact same string.

* **`extract_content(html)`:**
  * *What it does:* Converts messy HTML websites into clean, token-efficient Markdown for the AI.
  * *Line-by-line logic:* It uses `BeautifulSoup` to parse the HTML. It searches for `<main>` or `<article>` tags to find the core content. Crucially, it finds all `<nav>`, `<footer>`, `<script>`, and `<style>` tags and calls `.decompose()` to instantly delete them from the memory tree. Finally, it uses `markdownify` to convert the remaining HTML into text.
  * *Why we did it:* If you feed an AI raw HTML with navbars, it will hallucinate and give you terrible answers. Removing the "noise" before generating Markdown is the absolute secret to high-quality RAG.

* **`extract_links(base_url, html)`:**
  * *What it does:* Finds all the clickable links on a page.
  * *Line-by-line logic:* It finds all `<a>` tags. It uses `urljoin(base_url, href)` to convert relative links (like `/setup`) into absolute links (like `https://site.com/setup`).

* **`is_in_scope(start_url, new_url)`:**
  * *What it does:* The Security Guardrail.
  * *Line-by-line logic:* It checks if `new_url.startswith(start_url)`.
  * *Why we did it:* If a documentation page links to `twitter.com`, we don't want the crawler to leave the docs and start scraping all of Twitter!

* **`crawl_site(...)`:**
  * *What it does:* The main asynchronous loop that orchestrates the scraping.
  * *Line-by-line logic:* It creates an `asyncio.Queue()`. It puts the starting URL in the queue. A `while` loop pulls URLs out of the queue, fetches the HTML, calls `extract_content`, saves it to Neo4j via `graph_manager`, extracts new links, and puts those new links back into the queue. It stops when the `limit` is reached.

---

## 3. 🤖 `agents.py` (The Brain)

This file defines the Google ADK Agent. It replaces a traditional hard-coded script with an autonomous decision-maker.

### Breakdown of Configuration:

* **`root_agent` definition:**
  * *What it does:* Initializes a Gemini-powered agent and "binds" the `crawl_site` function to it as a usable tool.

* **System Instructions:**
  * *What it does:* We provide a plaintext prompt to the agent: *"Your goal is to build documentation. First, use crawl_site to gather data. Respect the limit. Once done, compile it."*
  * *Why we did it:* Instead of writing complex Python `if/else` state machines to figure out what to do if a page fails, we just give the AI the tools and the goal. The AI dynamically reads the URL, decides to execute the `crawl_site` tool, waits for the result, and then decides to stop and output the final text.

---

## 4. 🌐 `api.py` (The Gateway)

This is the FastAPI server. It is the bridge between the Python backend on Render and the React frontend on Vercel.

### Breakdown of Endpoints:

* **`@app.websocket("/ws")`:**
  * *What it does:* Handles the long-running scraping job and streams live logs to the UI.
  * *Line-by-line logic:* 1. It `accept()`s the connection and reads the JSON containing the `url` and `limit`.
    2. It creates an asynchronous background task (`queue_reader`). This task runs in a constant loop, reading messages from `tools.progress_queue` and sending them to React via `websocket.send_text()`.
    3. It initializes the Agent Runner and triggers the AI to start working.
    4. When the agent finishes, it grabs the final Markdown string, wraps it in a JSON payload (`{"type": "download", "content": "..."}`), and sends it to the frontend to trigger the browser's file download feature.

* **`@app.get("/api/graph")`:**
  * *What it does:* A standard REST endpoint that React calls to get the Neo4j visualization data.

* **`@app.post("/api/chat")`:**
  * *What it does:* The **Retrieval-Augmented Generation (RAG)** engine.
  * *Line-by-line logic:* 1. It receives a `question` and a `url`.
    2. It asks `db.get_all_topics(url)` for the scraped Markdown.
    3. It filters out empty pages: `[p["content"] for p in pages if p.get("content")]`. This prevents `NoneType` string-joining crashes.
    4. It initializes the `AsyncOpenAI` client pointing to OpenRouter.
    5. It constructs a highly specific System Prompt, merging the scraped Markdown context with the user's question, strictly instructing the AI not to hallucinate.
    6. It calls the `hunter-alpha` (or `gpt-4o-mini`) model and returns the text answer to React.

---

## 5. 🔌 `main_client.py` (The Connector)

This is a required boilerplate file that connects the Google ADK framework to your FastAPI application.

### Breakdown of Logic:

* **`InMemoryRunner` & Sessions:**
  * *What it does:* It creates a secure, isolated "Session ID" for the AI Agent.
  * *Why we did it:* The AI Agent needs memory to function autonomously. It needs to remember "I already called the crawl tool 5 minutes ago, now I need to return the answer." By assigning a `session_id`, the `InMemoryRunner` keeps the agent's memory perfectly isolated. If two users use your web app at the exact same time, their agents won't overwrite each other's memories.

* **Execution Bridging:**
  * *Why we did it:* FastAPI relies on an asynchronous event loop (`asyncio`). The ADK agent also relies on an event loop. This file ensures the Agent's `.run()` command is executed safely within FastAPI's loop without blocking the server from handling other web requests.

---

## 6. 🛠️ Core Technologies Used

### 🕸️ Neo4j Graph Database


* **What it is:** Neo4j is a native graph database designed to store, manage, and query highly connected data. 
* **How it works:** Instead of rigid tables, rows, and columns (like SQL), Neo4j uses a **Property Graph Model**. It stores entities as **Nodes** (e.g., our scraped documentation pages) and the connections between them as **Relationships** (e.g., the hyperlinks routing from one page to another). 
* **Why we used it:** Web documentation is naturally a graph—a web of linked pages. Querying "Which pages link to the 'Installation' guide?" requires complex and expensive `JOIN` operations in a standard SQL database. In Neo4j, traversing these relationships is instantaneous. For our RAG pipeline, this allows us to pull perfectly structured, highly relevant, and interconnected context for the AI, completely avoiding hallucination-prone disconnected data.

### 🦅 OpenRouter & Hunter-Alpha Model


* **What it is:** OpenRouter is an AI model aggregator and API gateway. It provides a single, unified interface (identical to OpenAI's SDK) to access hundreds of different Large Language Models (LLMs) from providers like Meta, Anthropic, Google, and independent researchers.
* **The Model (Hunter-Alpha):** We specifically configured the `/api/chat` endpoint to route requests to the `openai/openrouter/hunter-alpha` model.
* **Why we used it:**
  * **OpenRouter** gave us the flexibility to instantly swap models without having to rewrite our backend API logic or install new provider-specific SDKs.
  * **Hunter-Alpha** is an advanced reasoning model that excels at strict instruction following. In our RAG setup, we heavily command the AI to *"Answer strictly using only this documentation context."* Hunter-Alpha is exceptionally good at reading the dense Neo4j context, extracting the exact technical answer, and gracefully admitting "I don't know" if the answer isn't in the scraped docs, making it perfect for enterprise-grade documentation chatbots.