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
        """Generates Virtual Directory Nodes for the structured hierarchy."""
        if not self.driver: return {"nodes": [], "links": []}

        # 🚀 THE BULLETPROOF FIX: Strip the protocol and trailing slashes
        clean_url = url.replace("https://", "").replace("http://", "").rstrip('/')

        # Now we just check if the URL *contains* the core domain/path
        nodes_query = "MATCH (t:Topic) WHERE t.url CONTAINS $clean_url AND t.content IS NOT NULL RETURN t.url AS id, t.content AS content"

        with self.driver.session() as session:
            nodes_result = session.run(nodes_query, clean_url=clean_url)
            real_nodes = [{"id": r["id"], "content": r["content"], "isVirtual": False} for r in nodes_result]

            final_nodes = {n["id"]: n for n in real_nodes}
            final_links = []

            for node_id in list(final_nodes.keys()):
                # Split URL into segments to find logical folders
                node_clean = node_id.rstrip('/')
                parts = node_clean.replace("https://", "").replace("http://", "").split('/')

                if len(parts) > 1:
                    parent_path = "/".join(node_id.split('/')[:-1])
                    # Ensure we don't create virtual nodes outside our target domain
                    if parent_path and clean_url in parent_path:
                        virtual_id = parent_path
                        if virtual_id not in final_nodes:
                            folder_name = parts[-2] if len(parts) > 1 else "Root"
                            final_nodes[virtual_id] = {
                                "id": virtual_id,
                                "content": f"### 📁 Directory: {folder_name}",
                                "isVirtual": True
                            }
                        final_links.append({"source": virtual_id, "target": node_id})

            # Connect orphaned folders/nodes to a central Root node
            for nid, node in final_nodes.items():
                if nid != url and not any(l["target"] == nid for l in final_links):
                    final_links.append({"source": url, "target": nid})

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