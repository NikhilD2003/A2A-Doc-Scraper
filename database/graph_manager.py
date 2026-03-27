import os
from neo4j import GraphDatabase
from dotenv import load_dotenv, find_dotenv

# 🚨 Hunt for the .env file
load_dotenv(find_dotenv())


class GraphManager:
    def __init__(self, uri, user, password):
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            self.driver.verify_connectivity()
            print("✅ Successfully connected to Neo4j Database.")
        except Exception as e:
            print(f"❌ Failed to connect to Neo4j: {e}")
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()

    def clear_database(self):
        """Wipes the entire database clean."""
        if not self.driver: return
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def upsert_topic(self, url, content):
        """Creates or updates a real Topic node."""
        if not self.driver: return
        name = url.split('/')[-1] or url.split('/')[-2] or "Home"
        query = """
        MERGE (t:Topic {url: $url})
        SET t.content = $content, t.name = $name, t.isVirtual = false
        """
        with self.driver.session() as session:
            session.run(query, url=url, content=content, name=name)

    def link_topics_batch(self, source_url, target_urls):
        """Standard linking for scraper reference."""
        if not self.driver: return
        query = """
        MATCH (source:Topic {url: $source_url})
        UNWIND $target_urls AS target_url
        MERGE (target:Topic {url: target_url})
        MERGE (source)-[:LINKS_TO]->(target)
        """
        with self.driver.session() as session:
            session.run(query, source_url=source_url, target_urls=target_urls)

    def get_all_topics(self, root_url=None):
        """RESTORED: Fetches all topics for the Markdown builder."""
        if not self.driver: return []
        if root_url:
            query = "MATCH (t:Topic) WHERE t.url STARTS WITH $root_url AND t.content IS NOT NULL RETURN t.url AS url, t.content AS content"
            params = {"root_url": root_url}
        else:
            query = "MATCH (t:Topic) WHERE t.content IS NOT NULL RETURN t.url AS url, t.content AS content"
            params = {}

        with self.driver.session() as session:
            result = session.run(query, params)
            return [{"url": record["url"], "content": record["content"]} for record in result]

    def get_graph_data(self, url):
        """Generates Virtual Directory Nodes for the structured hierarchy with X-Ray Diagnostics."""
        if not self.driver:
            print("❌ GraphManager: No driver connected!")
            return {"nodes": [], "links": []}

        print(f"\n--- 🌐 FETCHING GRAPH DATA FOR: {url} ---")

        # 1. 🚀 THE X-RAY GRAB: Fetch everything just to see what's actually in the database!
        # (We only grab a tiny snippet of content here to avoid crashing memory)
        nodes_query = "MATCH (t:Topic) RETURN t.url AS id, substring(t.content, 0, 10) AS snippet"

        with self.driver.session() as session:
            nodes_result = session.run(nodes_query)
            all_nodes = [{"id": r["id"]} for r in nodes_result]

            print(f"📊 Total Topics in Cloud Database: {len(all_nodes)}")
            if len(all_nodes) == 0:
                print("⚠️ THE DATABASE IS COMPLETELY EMPTY! You must run the scraper first.")
                return {"nodes": [], "links": []}

            print(f"🔍 Sample URL physically stored in DB: '{all_nodes[0]['id']}'")

            # 2. Super Forgiving Python Filter (Ignores slashes, http, and subdomains)
            clean_search = url.replace("https://", "").replace("http://", "").replace("www.", "").strip('/')
            fallback_search = clean_search.split('.')[0] if '.' in clean_search else clean_search

            matched_urls = []
            for n in all_nodes:
                # If "a2a-protocol" is ANYWHERE in the database ID, we keep it.
                if clean_search in n["id"] or fallback_search in n["id"]:
                    matched_urls.append(n["id"])

            print(f"🎯 Nodes successfully matched for graph: {len(matched_urls)}")

            if not matched_urls:
                return {"nodes": [], "links": []}

            # 3. Now fetch the full content ONLY for the matched nodes
            full_content_query = "MATCH (t:Topic) WHERE t.url IN $urls RETURN t.url AS id, t.content AS content"
            full_result = session.run(full_content_query, urls=matched_urls)

            final_nodes = {r["id"]: {"id": r["id"], "content": r["content"], "isVirtual": False} for r in full_result}
            final_links = []

            root_id = url.rstrip('/')

            # 4. Build the Folder Tree
            for node_id in list(final_nodes.keys()):
                if node_id == root_id:
                    continue

                parts = node_id.replace("https://", "").replace("http://", "").rstrip('/').split('/')

                if len(parts) > 1:
                    # Group by the parent directory
                    parent_id = "/".join(node_id.split('/')[:-1])

                    if parent_id not in final_nodes:
                        folder_name = parts[-2].upper() if len(parts) > 1 else "FOLDER"
                        final_nodes[parent_id] = {
                            "id": parent_id,
                            "content": f"### 📁 Directory: {folder_name}",
                            "isVirtual": True
                        }
                    final_links.append({"source": parent_id, "target": node_id})

            # Ensure Root exists
            if root_id not in final_nodes:
                final_nodes[root_id] = {
                    "id": root_id,
                    "content": f"### 🌐 Root: {url}",
                    "isVirtual": True
                }

            # Connect orphans
            for nid in final_nodes.keys():
                if nid != root_id and not any(l["target"] == nid for l in final_links):
                    final_links.append({"source": root_id, "target": nid})

        return {
            "nodes": list(final_nodes.values()),
            "links": final_links
        }

    def execute_read_query(self, query):
        if not self.driver: return []
        with self.driver.session() as session:
            result = session.run(query)
            return [dict(record) for record in result]

    def get_graph_summary(self, root_url):
        """Fetches a high-level map of the graph for the AI's keyword extraction phase."""
        if not self.driver: return ""
        # 🚀 INCREASED LIMIT: Changed from 50 to 500 to feed the 120B model's massive context window
        query = "MATCH (t:Topic) WHERE t.url STARTS WITH $root_url RETURN t.url AS url LIMIT 500"
        with self.driver.session() as session:
            result = session.run(query, root_url=root_url)
            return ", ".join([r["url"] for r in result])


# ==========================================
# 🚀 INITIALIZATION
# ==========================================
_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
_user = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER", "neo4j")
_pwd = os.getenv("NEO4J_PASSWORD")

db = GraphManager(uri=_uri, user=_user, password=_pwd)