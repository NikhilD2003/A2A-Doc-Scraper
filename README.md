# 🕸️ A2A Autonomous Documentation Scraper

Welcome to the **A2A Documentation Scraper**, an enterprise-grade, fully autonomous Agent-to-Agent (A2A) web scraping pipeline designed to transform sprawling websites and complex GitHub repositories into clean, unified Markdown documentation, explore them via an interactive Knowledge Graph, and chat with them using an AI-powered RAG engine.

## 🛑 The Problem

When developers or AI researchers need to feed documentation into a RAG (Retrieval-Augmented Generation) system or simply read a project's manual offline, traditional web scrapers fail. They pull in massive amounts of noisy HTML—navigation bars, footers, redundant UI tabs, and binary files.

Conversely, asking an LLM to read a 50-page website and re-type it invariably leads to hallucinations, conversational filler, and severe output token limits. Massive repositories (like GitHub) also create a "Maze" of redundant links (commit hashes, raw files, blame views) that trap standard crawlers in infinite loops.

## 💡 The Solution & Core Features

This project introduces a robust A2A architecture where the Large Language Model acts as the *Manager*, not the *Typist*.

* 🎯 **Strict Path-Scoping:** Automatically traps the scraper inside the specified repository or subfolder. If you target `github.com/user/repo`, it will never accidentally wander into `github.com/pricing`.

* 🛡️ **The "GitHub Maze" Resolver:** Intelligently ignores commit hashes, repetitive UI tabs (`/issues`, `/pulls`), and large binary/data files (`.npy`, `.exe`, `.pdf`), ensuring only live, relevant code and documentation are processed.

* 🕸️ **Graph Database Mapping:** Uses **Neo4j** to map the website's structure as nodes and edges. This prevents duplicate content indexing and keeps track of how pages reference each other.

* 🚀 **Zero Token-Limit Failures:** Instead of forcing the AI to output massive blocks of compiled text, the Python backend securely hands off the pristine Markdown directly to system memory.

* ⚡ **Real-Time WebSocket UI:** A sleek React dashboard streams live terminal progress. Once compiled, it utilizes the modern File System Access API to trigger a native "Save As" browser popup, delivering the file directly to your local machine.

* 🧠 **Interactive RAG Chat:** Talk directly to your scraped documentation using OpenRouter (Nemotron 120B). Features strict anti-hallucination guardrails to ensure high accuracy.

* 📊 **Visual Knowledge Graph:** Automatically generates an interactive, top-to-bottom directory tree using ReactFlow and Dagre to visualize the hierarchy of the scraped documentation.

## 🌐 Live Demo & Deployment

The application is fully deployed and can be accessed at the following link:

🚀 Live App: https://a2-a-doc-scraper.vercel.app

System Dashboard Preview

Architecture showing the real-time WebSocket connection between the React Frontend and the FastAPI Backend.

![img.png](img.png)

## 🏗️ System Architecture

The project is split into a decoupled Client-Server architecture:

1. **The Client (React):** Connects to the server via WebSockets, sends the target URL, and listens for real-time scraping logs.

2. **The Server (FastAPI):** Initializes an AI Agent (via Google GenAI/ADK) which strategizes the scraping process.

3. **The Tools (Python/BeautifulSoup):** The agent triggers asynchronous scraping tools that traverse the web, clean the HTML, convert it to Markdown, and filter out noise.

4. **The Database (Neo4j):** Scraped content and relational links are `MERGE`d into the graph database to maintain state and prevent duplicates.

5. **The Handoff:** The tools compile the graph data into a master Markdown string, bypass the AI's output generation, and send the payload directly back over the WebSocket to the React client for download.

6. **The AI Chat Engine:** Uses a multi-stage RAG pipeline (Graph summary loading -> Keyword extraction -> Dynamic Cypher scoring -> Answer generation).

## 📂 Project Anatomy (File Structure)

Here is a breakdown of the core files that make this pipeline work:

### Backend (Python)

* `api.py`: The FastAPI server. It handles CORS, opens the WebSocket endpoint (`/ws`) with keep-alive pings, initializes the AI agent, hosts the graph/chat API endpoints, and packages the final Markdown into a JSON payload to trigger the user's download prompt.

* `tools.py`: The workhorse of the scraper. It contains the async `aiohttp` crawler, the `BeautifulSoup` HTML cleaner (which strips navbars and footers), the strict URL scope checker, and the GitHub Maze filters. It compiles the final document.

* `graph_manager.py`: The Neo4j database connector. It securely loads `.env` credentials and executes optimized Cypher queries (like `upsert_topic` and `link_topics_batch`) to map the website into a mathematical graph.

* `agent.py`: *(Internal)* Configures the ADK/LiteLLM agent that orchestrates the tool calling.

* `requirements.txt`: Contains all necessary Python dependencies (`fastapi`, `neo4j`, `beautifulsoup4`, etc.) for easy cloud deployment.

### Frontend (React)

* `App.jsx`: The main user interface. It features a modern, dark-mode multi-tab UI built with Tailwind CSS and Lucide icons. It manages the WebSocket connection, auto-scrolls live logs, renders the interactive Knowledge Graph, hosts the Chat interface, and uniquely utilizes browser Blob APIs to handle massive file downloads natively.

## 💻 Tech Stack

* **Frontend:** React, Vite, Tailwind CSS, Lucide React, ReactFlow, Dagre

* **Backend:** FastAPI, Python, WebSockets, Uvicorn, aiohttp

* **Database:** Neo4j (AuraDB Cloud / Desktop)

* **Data Processing:** BeautifulSoup4, Markdownify

* **AI Orchestration:** Google GenAI, ADK, LiteLLM, OpenRouter (Nemotron 120B)

## 🚀 Getting Started (Local Development)

### 1. Prerequisites

* Python 3.10+

* Node.js & npm

* A local Neo4j Desktop instance OR a free Neo4j AuraDB cloud account.

### 2. Backend Setup

Clone the repository

```bash
git clone [https://github.com/NikhilD2003/A2A-Doc-Scraper.git](https://github.com/NikhilD2003/A2A-Doc-Scraper.git)
cd A2A-Doc-Scraper
```

Install dependencies

```bash
pip install -r requirements.txt
```

Create a `.env` file in the root directory and add your credentials:

```env
NEO4J_URI=bolt://localhost:7687  # (or your AuraDB URI)
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
OPENROUTER_API_KEY=your_openrouter_key
```

Start the FastAPI server

```bash
uvicorn api:app --reload --port 8000
```

### 3. Frontend Setup

Navigate to your React frontend directory (assuming it is set up via Vite)

```bash
npm install
npm run dev
```

### 4. Usage

Open the React frontend in your browser, enter a target URL (e.g., a GitHub repository path), and click **Start Pipeline**. Watch the terminal stream live actions. Switch to the **Knowledge Graph** to explore the site structure, or use the **Chat with Docs** tab to query your scraped data!