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

        # 1. Parse the URL
        parsed = urlparse(url)
        domain = parsed.netloc if parsed.netloc else url.replace('https://', '').replace('http://', '').split('/')[0]

        # 2. Extract the first primary folder (e.g., "latest" from "https://a2a.com/latest/")
        path_parts = [p for p in parsed.path.split('/') if p]
        primary_folder = f"/{path_parts[0]}" if path_parts else domain.split('.')[0]

        # 3. 🚀 THE FIX: Match the Domain OR the Relative Path Folder
        nodes_query = """
        MATCH (t:Topic) 
        WHERE (t.url CONTAINS $domain OR t.url STARTS WITH $primary_folder OR t.url CONTAINS $primary_folder) 
          AND t.content IS NOT NULL 
        RETURN t.url AS id, t.content AS content
        """

        with self.driver.session() as session:
            nodes_result = session.run(nodes_query, domain=domain, primary_folder=primary_folder)
            real_nodes = [{"id": r["id"], "content": r["content"], "isVirtual": False} for r in nodes_result]

            final_nodes = {n["id"]: n for n in real_nodes}
            final_links = []

            # The root ID should be the base path (e.g., "/latest") so it matches the DB format
            root_id = primary_folder if primary_folder.startswith('/') else f"/{primary_folder}"

            for node_id in list(final_nodes.keys()):
                if node_id == root_id:
                    continue

                # Split URL by '/' to find logical parent directory
                parts = node_id.rstrip('/').split('/')

                # Create tree structure if the URL has paths (e.g., /latest/sdk/python)
                if len(parts) > 2:
                    parent_id = "/".join(parts[:-1])
                    if not parent_id: parent_id = root_id

                    # Create a virtual folder node if it doesn't exist
                    if parent_id not in final_nodes:
                        folder_name = parts[-2].upper() if len(parts) > 2 else "ROOT"
                        final_nodes[parent_id] = {
                            "id": parent_id,
                            "content": f"### 📁 Directory: {folder_name}",
                            "isVirtual": True
                        }

                    final_links.append({"source": parent_id, "target": node_id})

            # Ensure the root node exists so everything connects
            if root_id not in final_nodes:
                final_nodes[root_id] = {
                    "id": root_id,
                    "content": f"### 🌐 Root: {domain}",
                    "isVirtual": True
                }

            # Connect any floating pages or folders back to the root
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