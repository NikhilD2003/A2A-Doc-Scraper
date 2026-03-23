import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


class GraphManager:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )

    def close(self):
        if self.driver:
            self.driver.close()

    def upsert_topic(self, url, content):
        query = """
        MERGE (t:Topic {url: $url})
        SET t.content = $content
        """
        with self.driver.session() as session:
            session.run(query, url=url, content=content)

    def link_topics(self, source, target):
        query = """
        MERGE (a:Topic {url: $source})
        MERGE (b:Topic {url: $target})
        MERGE (a)-[:REFERENCES]->(b)
        """
        with self.driver.session() as session:
            session.run(query, source=source, target=target)

    def link_topics_batch(self, source, targets):
        if not targets:
            return
        query = """
        MERGE (a:Topic {url: $source})
        WITH a
        UNWIND $targets AS target
        MERGE (b:Topic {url: target})
        MERGE (a)-[:REFERENCES]->(b)
        """
        with self.driver.session() as session:
            session.run(query, source=source, targets=targets)

    def get_all_topics(self, target_url=None):
        if target_url:
            query = """
            MATCH (t:Topic)
            WHERE t.url STARTS WITH $target_url
            RETURN t.url AS url, t.content AS content
            """
            with self.driver.session() as session:
                result = session.run(query, target_url=target_url)
                return [{"url": r["url"], "content": r["content"]} for r in result]
        else:
            query = """
            MATCH (t:Topic)
            RETURN t.url AS url, t.content AS content
            """
            with self.driver.session() as session:
                result = session.run(query)
                return [{"url": r["url"], "content": r["content"]} for r in result]

    # --- THE FIX: CONTEXTUAL URL HIERARCHY ---
    def get_graph_data(self, target_url: str):
        # 1. Fetch all scraped nodes
        nodes_query = """
        MATCH (n:Topic)
        WHERE n.url STARTS WITH $target_url
        RETURN n.url AS id, n.content AS content
        """

        with self.driver.session() as session:
            nodes_result = session.run(nodes_query, target_url=target_url)
            nodes = []
            urls = []

            for record in nodes_result:
                n_id = record["id"]
                content = record["content"]

                # Clean up the label for the frontend boxes
                label = n_id.rstrip('/').split('/')[-1]
                label = label.replace('.html', '').replace('.md', '')
                if not label or n_id == target_url:
                    label = "Documentation Home"

                nodes.append({
                    "id": n_id,
                    "label": label,
                    "content": content
                })
                urls.append(n_id)

            # 2. Build Contextual Links based on Folder Structure (Ignoring Hyperlinks)
            links = []

            def normalize(u):
                return u.rstrip('/')

            normalized_urls = {normalize(u): u for u in urls}
            root_norm = normalize(target_url)

            # Ensure the root node exists in our visual map
            if root_norm not in normalized_urls:
                normalized_urls[root_norm] = target_url
                if not any(n["id"] == target_url for n in nodes):
                    nodes.append({"id": target_url, "label": "Documentation Home", "content": "Root directory."})

            # Calculate the exact logical parent for every single URL
            for norm_url, original_url in normalized_urls.items():
                if norm_url == root_norm:
                    continue  # The root has no parent

                # Chop off the end of the URL to find its parent folder
                parent_path = norm_url.rsplit('/', 1)[0]

                found_parent = None
                # Keep chopping the URL down until we find a parent that actually exists in our scraped data
                while len(parent_path) >= len(root_norm):
                    if parent_path in normalized_urls:
                        found_parent = normalized_urls[parent_path]
                        break
                    if '/' not in parent_path:
                        break
                    parent_path = parent_path.rsplit('/', 1)[0]

                # Link to the calculated parent, or default to the root Home page
                if found_parent and found_parent != original_url:
                    links.append({"source": found_parent, "target": original_url})
                elif original_url != target_url:
                    links.append({"source": target_url, "target": original_url})

            return {"nodes": nodes, "links": links}


db = GraphManager()