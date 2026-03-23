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
progress_queue = asyncio.Queue()


class PipelineState:
    final_markdown = ""


state = PipelineState()


async def send_progress(msg: str):
    await progress_queue.put(msg)


# --- THE FIX 1: Bulletproof URL Normalizer ---
def normalize_url(url):
    if not url.startswith("http"):
        url = "https://" + url
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
                content_type = resp.headers.get('Content-Type', '')
                text_data = await resp.text()
                if 'text/plain' in content_type or url.endswith('.txt') or url.endswith('.rst'):
                    return {"type": "text", "body": text_data}
                return {"type": "html", "body": text_data}
    except:
        pass
    return None


def extract_content(content_obj):
    if not content_obj: return ""
    if content_obj["type"] == "text":
        text = content_obj["body"]
        text = text.replace("\\_", "_").replace("¶", "")
        return f"```text\n{text.strip()}\n```"

    html = content_obj["body"]
    soup = BeautifulSoup(html, "html.parser")
    main = (soup.select_one("article") or soup.select_one("main") or soup.select_one("div.md-content") or soup.body)
    if not main:
        return ""

    for tag in main(["nav", "header", "footer", "script", "style", "svg", "noscript", "iframe", "aside", "form"]):
        tag.decompose()
    for menu in main.find_all(class_=["menu", "sidebar", "navigation", "toc"]):
        menu.decompose()
    for img in main.find_all("img"):
        img.decompose()
    for xml in main.find_all(string=lambda t: t and "<?xml" in t):
        xml.extract()

    text = md(str(main), heading_style="ATX")
    text = text.replace("```xml", "```")
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.replace("\\_", "_")
    text = text.replace("¶", "")
    text = re.sub(r'\[\s*\]\([^)]+\)', '', text)

    return text.strip()


def extract_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    main = (soup.select_one("article") or soup.select_one("main") or soup.select_one("div.md-content") or soup.body)

    if main:
        for tag in main(["nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        for menu in main.find_all(class_=["menu", "sidebar", "navigation", "toc"]):
            menu.decompose()
        search_area = main
    else:
        search_area = soup

    links = []
    if not base_url.endswith('/') and not '.' in base_url.split('/')[-1]:
        base_url += '/'

    for a in search_area.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            continue
        full = urljoin(base_url, href)
        full = full.split('#')[0]
        parsed = urlparse(full)
        clean = normalize_url(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")
        links.append(clean)

    return list(set(links))


def is_in_scope(link, root_url):
    parsed_link = urlparse(link)
    parsed_root = urlparse(root_url)
    if parsed_link.netloc != parsed_root.netloc:
        return False
    root_path = parsed_root.path.rstrip('/')
    if root_path and not parsed_link.path.startswith(root_path):
        return False
    blocked_langs = ['/zh/', '/ko/', '/ja/', '/ru/', '/de/', '/fr/', '/es/', '/pt/', '/tr/', '/vi/', '/ar/',
                     '/zh-hans/']
    for lang in blocked_langs:
        if lang in link and lang not in root_url:
            return False
    return True


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

            fetched_data = await fetch(session, url)
            if not fetched_data: continue

            content = extract_content(fetched_data)
            db.upsert_topic(url, content)

            await asyncio.sleep(4)

            if fetched_data["type"] == "html":
                links = extract_links(fetched_data["body"], url)
                valid_targets = []

                for link in links:
                    link = normalize_url(link)
                    if not is_in_scope(link, root_url): continue

                    parsed_link = urlparse(link)
                    parsed_path = parsed_link.path.lower()

                    BAD_EXTENSIONS = [
                        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".zip", ".ico",
                        ".csv", ".tar", ".gz", ".exe", ".npy", ".iml", ".xml", ".ps1",
                        ".dll", ".bin", ".pkl", ".h5", ".pt", ".pth", ".tsv"
                    ]
                    if any(parsed_path.endswith(ext) for ext in BAD_EXTENSIONS): continue

                    LANG_PREFIXES = ["/de/", "/es/", "/fr/", "/ja/", "/ko/", "/pt/", "/zh/", "/ru/", "/tr/", "/uk/"]
                    if any(parsed_path.startswith(prefix) for prefix in LANG_PREFIXES): continue

                    BLOCKED_PATHS = [
                        "/newsletter", "/blog", "/sponsors", "/fastapi-people", "/apps",
                        "/branding", "/marketplace", "/admin", "/playground", "/editor",
                        "/stats", "/essays"
                    ]
                    if any(parsed_path.startswith(p) for p in BLOCKED_PATHS): continue

                    if "github.com" in parsed_link.netloc:
                        if re.search(r'/[a-f0-9]{40}(?:/|$)', parsed_path):
                            continue
                        gh_noise = [
                            "commits", "commit", "compare", "branches", "tags",
                            "pulls", "issues", "network", "stargazers", "watchers",
                            "forks", "releases", "graphs", "pulse", "security",
                            "community", "labels", "milestones", "search", "raw", "blame"
                        ]
                        path_parts = parsed_path.split('/')
                        if any(noise in path_parts for noise in gh_noise):
                            continue

                    valid_targets.append(link)
                    if link not in visited: queue.append(link)

                if valid_targets:
                    db.link_topics_batch(url, valid_targets)


async def build_documentation(root_url):
    root_url = normalize_url(root_url)
    await send_progress("✨ Scrape limit reached! Fetching context from Neo4j...")
    pages = db.get_all_topics(root_url)

    # --- THE FIX 2: LLM Hallucination Safeguard ---
    # If the LLM passed a bad URL and Neo4j found nothing, just grab EVERYTHING in the DB.
    if not pages:
        await send_progress("⚠️ Attempting fallback data extraction...")
        pages = db.get_all_topics()
        if pages:
            # Use the most prominent URL from the DB as the new root
            root_url = pages[0].get("url", root_url)

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
    state.final_markdown = final_text
    await send_progress("📝 Raw Markdown securely saved to backend memory.")
    return "SUCCESS: The document has been saved directly to the system. Reply exactly and only with: 'Process Complete'."