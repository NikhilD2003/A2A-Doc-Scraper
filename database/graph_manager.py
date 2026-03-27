import os
from neo4j import GraphDatabase
from dotenv import load_dotenv, find_dotenv
from urllib.parse import urlparse

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
        """Generates Virtual Directory Nodes by matching the relative path structure."""
        if not self.driver: return {"nodes": [], "links": []}

        # 1. 🎯 THE PATH ANCHOR
        # If user inputs https://a2a-protocol.org/latest/, we extract "/latest"
        parsed = urlparse(url)
        path_segments = [p for p in parsed.path.split('/') if p]

        # We look for the first folder (e.g., 'latest')
        db_anchor = f"/{path_segments[0]}" if path_segments else "/latest"

        print(f"🚀 Searching DB for paths starting with: {db_anchor}")

        # 2. Query Neo4j for anything starting with that path
        nodes_query = """
        MATCH (t:Topic) 
        WHERE t.url STARTS WITH $db_anchor AND t.content IS NOT NULL 
        RETURN t.url AS id, t.content AS content
        """

        with self.driver.session() as session:
            nodes_result = session.run(nodes_query, db_anchor=db_anchor)
            real_nodes = [{"id": r["id"], "content": r["content"], "isVirtual": False} for r in nodes_result]

            if not real_nodes:
                return {"nodes": [], "links": []}

            final_nodes = {n["id"]: n for n in real_nodes}
            final_links = []

            # The root of our tree is the anchor (e.g., "/latest")
            root_id = db_anchor

            for node_id in list(final_nodes.keys()):
                if node_id == root_id:
                    continue

                # Split path: /latest/sdk/python -> ['', 'latest', 'sdk', 'python']
                parts = node_id.split('/')

                # Logic to link /latest/sdk/python to /latest/sdk
                if len(parts) > 2:
                    parent_id = "/".join(parts[:-1])
                    if not parent_id: parent_id = root_id

                    if parent_id not in final_nodes:
                        folder_name = parts[-2].upper()
                        final_nodes[parent_id] = {
                            "id": parent_id,
                            "content": f"### 📁 Directory: {folder_name}",
                            "isVirtual": True
                        }
                    final_links.append({"source": parent_id, "target": node_id})

            # Ensure the Root exists in the node list
            if root_id not in final_nodes:
                final_nodes[root_id] = {
                    "id": root_id,
                    "content": f"### 🌐 Documentation Root: {db_anchor}",
                    "isVirtual": True
                }

            # Connect any top-level pages directly to root
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