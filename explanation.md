# 🧠 A2A Documentation Scraper: Codebase Deep Dive

This document provides a detailed, section-by-section breakdown of the Python backend powering the Agent-to-Agent (A2A) Documentation Scraper. The system is split into five distinct files, each handling a specific layer of the architecture: Database, Scraping, AI Logic, API Gateway, and the Execution Runner.

---

## 1. 💾 `graph_manager.py` (The Memory Layer)

This file is responsible for all interactions with the Neo4j Graph Database. Instead of storing web pages in flat SQL tables, it stores them as **Nodes** and the hyperlinks between them as **Relationships**.

### Breakdown of Functions:

* **`__init__(self, uri, user, password)` & `close(self)`:**
  * *What it does:* Uses the `neo4j` Python driver to authenticate and connect using environment variables loaded via `find_dotenv()`.
  * *Line-by-line logic:* It wraps the connection in a `try/except` block, calls `verify_connectivity()`, and stores the driver on success (or sets it to `None` on failure).
  * *Why we did it:* Keeping the connection stateful inside a class prevents us from having to open and close a database connection every single time we save a page, which would drastically slow down the scraper.

* **`clear_database(self)`:**
  * *What it does:* Wipes the entire database clean for a fresh scrape.
  * *Line-by-line logic:* Opens a session and runs `MATCH (n) DETACH DELETE n`.
  * *Why we did it:* Without this, subsequent pipeline runs on the same domain would create messy, overlapping, or orphaned nodes from older documentation versions.

* **`upsert_topic(self, url, content)`:**
  * *What it does:* Saves a scraped webpage and its parsed Markdown to the database.
  * *Line-by-line logic:* It uses a Cypher `MERGE (t:Topic {url: $url})` command, sets `t.content`, derives a short `name` from the URL, and marks `isVirtual = false`.
  * *Why we did it:* `MERGE` is critical. If we used `CREATE`, scraping a page twice would create duplicate nodes. `MERGE` acts like an "upsert"—if the URL exists, it grabs it; if not, it creates it. This ensures absolute data uniqueness.

* **`link_topics_batch(self, source_url, target_urls)`:**
  * *What it does:* Draws the arrows (relationships) between a parent page and all the links found on that page.
  * *Line-by-line logic:* It takes a list of URLs (`target_urls`), `UNWIND`s them inside Neo4j, `MERGE`s missing target nodes, and creates a `[:LINKS_TO]` arrow from the source to each target.
  * *Why we did it:* Looping through database inserts in Python over a network is very slow. Sending one large batch array to Neo4j and letting it `UNWIND` the data natively is exponentially faster.

* **`get_all_topics(self, root_url)`:**
  * *What it does:* Retrieves all scraped Markdown text for the final document compilation (optionally scoped to a root URL).
  * *Line-by-line logic:* When `root_url` is provided, it runs `MATCH (t:Topic) WHERE t.url CONTAINS $root_url AND t.content IS NOT NULL`. Otherwise, it returns all topics with content.
  * *Why we did it:* This is the **Anti-Leak Filter**. If you scrape two different frameworks into the same database, the `CONTAINS` clause ensures the compiler only stitches together pages that belong to the current target URL.

* **`get_graph_data(self, url)`:**
  * *What it does:* Formats data specifically for the React Frontend's interactive Knowledge Graph.
  * *Line-by-line logic:* It retrieves nodes whose URLs `CONTAINS` the target, then splits paths to generate "Virtual Folder" nodes (`isVirtual = True`), links them to their children, and ensures a root node exists.
  * *Why we did it:* Neo4j only stores flat URL strings. To give the user a hierarchical tree layout in the UI, the backend builds a directory structure on the fly before sending it to ReactFlow.

Additional helpers in this file include `execute_read_query()` for ad-hoc read Cypher and `get_graph_summary()` which returns a compact URL map used during the chat keyword extraction stage.

---

## 2. 🕷️ `tools.py` (The Scraper Engine)

This file contains the core tools the AI Agent uses. It handles the raw HTTP networking, asynchronous looping, and HTML parsing.

### Breakdown of Functions:

* **`get_content_hash(text)` & The Memory Backpack:**
  * *What it does:* Prevents duplicate processing by storing state.
  * *Line-by-line logic:* Uses `hashlib.md5(text.encode('utf-8')).hexdigest()` to create a fingerprint and tracks it in `seen_content_hashes`, alongside a `visited` URL set.
  * *Why we did it:* Websites often have URLs with different query parameters (e.g., `?theme=dark`) that point to the exact same text. Fingerprinting ensures we only save unique textual content, saving database space and LLM tokens.

* **`fetch(session, url)`:**
  * *What it does:* The HTTP downloader.
  * *Line-by-line logic:* Uses `aiohttp.ClientSession.get()` with a browser-like `User-Agent`. It treats `text/plain`, `.txt`, and `.rst` as raw text; everything else is processed as HTML.
  * *Why we did it:* `aiohttp` is non-blocking. It allows the spider to theoretically download multiple pages concurrently without freezing the main application loop.

* **`extract_content(content_obj)`:**
  * *What it does:* Converts messy HTML websites into clean, token-efficient Markdown.
  * *Line-by-line logic:* Uses `BeautifulSoup` to parse HTML, selects the most relevant container (`article`, `main`, `div.md-content`, or `body`), and removes noise tags (nav/header/footer/script/style/svg/etc.) plus common sidebar classes. It also deletes "skip to content" links, images, and stray XML strings, then uses `markdownify` and final regex cleanups to normalize the output.
  * *Why we did it:* If you feed an AI raw HTML with navbars and JavaScript snippets, it will hallucinate and give terrible answers. Removing the "noise" before generating Markdown is the absolute secret to high-quality RAG.

* **`is_in_scope(link, root_url)` & GitHub Maze Filters:**
  * *What it does:* The Security Guardrail and loop preventer.
  * *Line-by-line logic:* Enforces the same domain and root path, and blocks non-target language paths (e.g., `/fr/`, `/ja/`) unless the root URL already targets that locale. GitHub noise filters then drop commits, issues, branches, raw views, and 40-character hashes.
  * *Why we did it:* A crawler can get stuck in an infinite loop inside GitHub's commit history or accidentally leave the documentation domain to scrape Wikipedia. These strict filters trap the spider safely inside the target repository.

* **`crawl_site(root_url, limit)` & `build_documentation(root_url)`:**
  * *What it does:* The orchestration loops.
  * *Line-by-line logic:* `crawl_site` pops URLs from a queue, logs progress to `progress_queue`, fetches and cleans pages, de-duplicates by hash, and stores nodes/edges in Neo4j. It applies extension, language, and path filters, adds GitHub-specific noise blockers, and throttles requests with a short sleep. `build_documentation` pulls content from Neo4j (with a fallback if the scoped query is empty), writes a master Markdown file with source sections, fixes in-page anchors, and stores the final text in `state.final_markdown`. The `run_full_pipeline()` wrapper clears the graph, resets state, and runs both steps in sequence.

---

## 3. 🤖 `agent.py` (The Brain)

This file defines the AI Agent. It replaces a traditional hard-coded script with an autonomous decision-maker using Google ADK and OpenRouter.

### Breakdown of Configuration:

* **The Bait and Switch (Environment Variables):**
  * *What it does:* Reroutes standard AI requests to the OpenRouter gateway.
  * *Line-by-line logic:* Reassigns `os.environ["OPENAI_API_KEY"]` to your OpenRouter key, and changes the `OPENAI_API_BASE` to `https://openrouter.ai/api/v1`.
  * *Why we did it:* Many AI frameworks hardcode their logic to hit OpenAI's paid servers. This overrides that default, allowing us to leverage the Nemotron 120B model hosted on OpenRouter without rewriting the core ADK library.

* **`SYSTEM_INSTRUCTION`:**
  * *What it does:* We provide a strict plaintext prompt to the agent: *"You have exactly one tool. Call it. When finished, reply ONLY with 'Process Complete'."*
  * *Why we did it:* AI models are naturally chatty. If we don't constrain it, it might try to summarize the entire 500-page scrape in the chat window, causing a fatal token-limit crash. This script forces the AI to act strictly as an orchestrator, not a conversationalist.

* **`root_agent` instantiation:**
  * *What it does:* Initializes the Agent object, binds the `run_full_pipeline` tool to it, and assigns the `openai/nvidia/nemotron-3-super-120b-a12b:free` model.

---

## 4. 🌐 `api.py` (The Gateway)

This is the FastAPI server. It is the bridge between the Python backend and the React frontend (local or deployed).

### Breakdown of Endpoints:

* **`@app.websocket("/ws")` (The Pipeline Stream):**
  * *What it does:* Handles the long-running scraping job and streams live logs to the UI.
  * *Line-by-line logic:* 1. It `accept()`s the connection.
    2. It creates an `asyncio.create_task` loop to constantly read messages from `progress_queue` and send them to React.
    3. **Crucial:** It launches an `asyncio.sleep(20)` keep-alive loop. This pings the connection every 20 seconds to prevent aggressive cloud load balancers (like Render's) from dropping the connection during heavy scraping.
    4. It triggers the `InMemoryRunner` with the ADK agent and waits for the tool-driven pipeline to finish.
    5. Upon completion, it grabs the compiled text from `state.final_markdown` (or falls back to `db.get_all_topics()` if needed), packages it as a JSON download payload, and sends it to the UI before emitting `DONE`.

* **`@app.post("/api/chat")` (The RAG Engine):**
  * *What it does:* Empowers the user to converse with their scraped documentation.
  * *Line-by-line logic:* 1. **Keyword Extraction:** Uses OpenRouter to parse the question into a JSON list of technical keywords, with a regex fallback for acronyms.
    2. **Dynamic Cypher Scoring:** Builds a `CONTAINS`-based query that scores URLs and content, returning the top 10 pages.
    3. **Context Injection:** Slices keyword-relevant snippets, sanitizes them, and feeds them into a strict System Prompt that forces either an exact code quote or a specific "no implementation" response.
    4. **Post-Processing:** Fixes Markdown code block spacing and rejects vague denial phrases.
  * *Why we did it:* This multi-stage pipeline guarantees the AI has the most relevant factual data possible, and the strict prompt rules enforce a zero-hallucination policy.

Additional endpoints include `/api/graph` (returns node/edge data for ReactFlow) and `/` (a simple health check).

---

## 5. 🔌 `main_client.py` (The Local Remote Control)

This is a standalone execution file. It allows developers to test the full ADK agent and scraping pipeline locally from a terminal without spinning up the FastAPI server or React frontend.

### Breakdown of Logic:

* **`InMemoryRunner` & Sessions:**
  * *What it does:* It creates a secure, isolated "Session ID" for the AI Agent and enables LiteLLM debug logging before startup.
  * *Line-by-line logic:* Sets `LITELLM_LOG=DEBUG`, instantiates `InMemoryRunner(agent=root_agent)`, and calls `create_session(user_id, session_id)`.
  * *Why we did it:* The AI Agent needs memory to function autonomously. By assigning a `session_id`, the runner keeps the agent's memory perfectly isolated. 

* **The Silent Execution Hack (`pass`):**
  * *What it does:* Executes the AI loop but ignores conversational output.
  * *Line-by-line logic:* Uses `async for event in runner.run_async(): pass`.
  * *Why we did it:* As mentioned, if you ask an AI to output a massive scraped book into a chat window, it will crash due to token limits. By using `pass`, we tell the script: *"Let the AI trigger the database tools, but ignore whatever it tries to say in the terminal."*

* **Direct State Extraction:**
  * *What it does:* Since we ignored the AI's chat output, we extract the payload directly from Python memory via `result_text = state.final_markdown`, derive a site name with `urlparse`, and write the output to `generated_docs/<site>.md`.
