import asyncio
import aiohttp
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from markdownify import markdownify as md
from urllib.parse import urljoin, urlparse
import warnings
import sys
import os
import re

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, ROOT_DIR)

try:
    from database.graph_manager import db
except ModuleNotFoundError:
    from graph_manager import db

visited = set()

# --- Real-time Progress Queue & Pipeline State ---
progress_queue = asyncio.Queue()


class PipelineState:
    final_markdown = ""


state = PipelineState()


async def send_progress(msg: str):
    await progress_queue.put(msg)


# ------------------------------------------------------

def normalize_url(url):
    parsed = urlparse(url)
    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if clean.endswith("/") and parsed.path != "/":
        clean = clean[:-1]
    return clean


def get_site_name(url):
    netloc = urlparse(url).netloc
    parts = netloc.split(".")
    if parts[0] in ["www", "docs"]:
        parts = parts[1:]
    return parts[0]


async def fetch(session, url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.text()
    except:
        pass
    return None


def extract_content(html):
    soup = BeautifulSoup(html, "html.parser")
    main = (soup.select_one("article") or soup.select_one("main") or soup.select_one("div.md-content") or soup.body)
    if not main:
        return ""

    # Strip out noisy website elements (menus, headers, footers, sidebars)
    for tag in main(["nav", "header", "footer", "script", "style", "svg", "noscript", "iframe"]):
        tag.decompose()

    # Strip common classes used for sidebars and tables of contents
    for menu in main.find_all(class_=["menu", "sidebar", "navigation", "toc"]):
        menu.decompose()

    for img in main.find_all("img"):
        img.decompose()
    for xml in main.find_all(string=lambda t: t and "<?xml" in t):
        xml.extract()

    text = md(str(main), heading_style="ATX")
    text = text.replace("```xml", "```")

    # Clean up massive blocks of empty lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def extract_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#"): continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        clean = normalize_url(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")
        links.append(clean)
    return links


# Strict Scope Checking
def is_in_scope(link, root_url):
    parsed_link = urlparse(link)
    parsed_root = urlparse(root_url)

    if parsed_link.netloc != parsed_root.netloc:
        return False

    root_path = parsed_root.path.rstrip('/')
    if not root_path:
        return True

    return parsed_link.path.startswith(root_path)


# ---------------------------------------------------
# MAIN CRAWLER
# ---------------------------------------------------

async def crawl_site(root_url: str, limit: int = 500):
    limit = int(limit)
    root_url = normalize_url(root_url)
    queue = [root_url]

    async with aiohttp.ClientSession() as session:
        while queue and len(visited) < limit:
            url = normalize_url(queue.pop(0))
            if url in visited: continue

            visited.add(url)
            await send_progress(f"🔍 SCRAPING: {url}")

            html = await fetch(session, url)
            if not html: continue

            content = extract_content(html)
            db.upsert_topic(url, content)

            links = extract_links(html, url)
            valid_targets = []

            for link in links:
                link = normalize_url(link)

                if not is_in_scope(link, root_url): continue

                parsed_link = urlparse(link)
                parsed_path = parsed_link.path.lower()

                # 1. Block massive data files and ALL requested extensions
                BAD_EXTENSIONS = [
                    ".png","/newsletter", "/blog", "/sponsors", "/fastapi-people", "/apps", "/branding",
                    "/marketplace", "/admin", "/playground", "/editor", "/stats",
                    "/newsletter", "/blog", "/sponsors", "/apps", "/essays", ".jpg",
                    ".jpeg", ".gif", ".svg", ".pdf", ".zip", ".ico",
                    ".csv", ".tar", ".gz", ".exe", ".npy", ".iml", ".xml", ".ps1",
                    ".dll", ".bin", ".pkl", ".h5", ".pt", ".pth", ".tsv"
                ]
                if any(parsed_path.endswith(ext) for ext in BAD_EXTENSIONS): continue

                LANG_PREFIXES = ["/de/", "/es/", "/fr/", "/ja/", "/ko/", "/pt/", "/zh/", "/ru/", "/tr/", "/uk/"]
                if any(parsed_path.startswith(prefix) for prefix in LANG_PREFIXES): continue

                # ALL requested blocked paths (deduplicated)
                BLOCKED_PATHS = [
                    "/newsletter", "/blog", "/sponsors", "/fastapi-people", "/apps",
                    "/branding", "/marketplace", "/admin", "/playground", "/editor",
                    "/stats", "/essays"
                ]
                if any(parsed_path.startswith(p) for p in BLOCKED_PATHS): continue

                # 2. THE GITHUB MAZE FIX!
                if "github.com" in parsed_link.netloc:
                    # A. Block commit hashes (40 character hex strings) to prevent reading history loops
                    if re.search(r'/[a-f0-9]{40}(?:/|$)', parsed_path):
                        continue

                    # B. Block redundant GitHub UI tabs
                    gh_noise = [
                        "commits", "commit", "compare", "branches", "tags",
                        "pulls", "issues", "network", "stargazers", "watchers",
                        "forks", "releases", "graphs", "pulse", "security",
                        "community", "labels", "milestones", "search", "raw", "blame"
                    ]
                    # Check if any of the noise words exist as a folder in the path
                    path_parts = parsed_path.split('/')
                    if any(noise in path_parts for noise in gh_noise):
                        continue

                valid_targets.append(link)
                if link not in visited: queue.append(link)

            if valid_targets:
                db.link_topics_batch(url, valid_targets)


# ---------------------------------------------------
# DOCUMENTATION BUILDER
# ---------------------------------------------------

async def build_documentation(root_url):
    await send_progress("✨ Scrape limit reached! Fetching context from Neo4j...")
    pages = db.get_all_topics()

    site_name = get_site_name(root_url)
    domain = urlparse(root_url).netloc
    doc = []

    doc.append(f"# {site_name.capitalize()} Master Documentation\n")
    doc.append(f"**Generated from:** [{root_url}]({root_url})\n\n---\n")

    for p in pages:
        url = p.get("url", "")
        content = p.get("content") or ""
        content = content.strip()

        if not content:
            continue

        page_path = urlparse(url).path
        if not page_path or page_path == "/":
            page_path = "Home"

        doc.append(f"\n## 📄 Source: {page_path}\n")
        doc.append(content)
        doc.append("\n---\n")

    final_text = "\n".join(doc)

    def fix_anchors(match):
        link_text = match.group(1)
        full_link = match.group(2)
        if "#" in full_link:
            if full_link.startswith("/") or domain in full_link:
                anchor = full_link[full_link.find("#"):]
                return f"[{link_text}]({anchor})"
        return match.group(0)

    final_text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', fix_anchors, final_text)

    # SECURE MEMORY HANDOFF
    state.final_markdown = final_text

    await send_progress("📝 Raw Markdown securely saved to backend memory.")

    return "SUCCESS: The document has been saved directly to the system. Reply exactly and only with: 'Process Complete'."