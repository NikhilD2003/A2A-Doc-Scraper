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

    # --- THE FIX: BFS SPANNING TREE ---
    def get_graph_data(self, target_url: str):
        # 1. Fetch all Nodes
        nodes_query = """
        MATCH (n:Topic)
        WHERE n.url STARTS WITH $target_url
        RETURN n.url AS id, n.content AS content
        """

        # 2. Fetch all raw Hyperlinks
        links_query = """
        MATCH (a:Topic)-[:REFERENCES]->(b:Topic)
        WHERE a.url STARTS WITH $target_url AND b.url STARTS WITH $target_url
        RETURN a.url AS source, b.url AS target
        """

        with self.driver.session() as session:
            # Process Nodes
            nodes_result = session.run(nodes_query, target_url=target_url)
            nodes = []
            valid_urls = set()

            for record in nodes_result:
                n_id = record["id"]

                # Format a clean, readable label
                label = n_id.rstrip('/').split('/')[-1]
                label = label.replace('.html', '').replace('.md', '')
                if not label or n_id == target_url:
                    label = "Documentation Home"

                nodes.append({"id": n_id, "label": label, "content": record["content"]})
                valid_urls.add(n_id)

            # Ensure the root target URL exists in the dataset
            root_url = target_url.rstrip('/') + '/'
            if root_url not in valid_urls and target_url in valid_urls:
                root_url = target_url
            elif root_url not in valid_urls:
                nodes.append({"id": root_url, "label": "Documentation Home", "content": "Root Node"})
                valid_urls.add(root_url)

            # Process Links into an Adjacency List
            links_result = session.run(links_query, target_url=target_url)
            adj = {u: [] for u in valid_urls}

            for record in links_result:
                src = record["source"]
                tgt = record["target"]
                if src in adj and tgt in valid_urls:
                    adj[src].append(tgt)

            # 3. Build the clean Spanning Tree (Breadth-First Search)
            tree_links = []
            visited = set([root_url])
            queue = [root_url]

            while queue:
                current = queue.pop(0)
                for neighbor in adj[current]:
                    # If we haven't seen this page yet, link it to the current page!
                    # This naturally destroys the circular "Next Steps" links.
                    if neighbor not in visited:
                        visited.add(neighbor)
                        tree_links.append({"source": current, "target": neighbor})
                        queue.append(neighbor)

            # 4. Fallback: Attach any isolated/orphan pages directly to the root
            for u in valid_urls:
                if u not in visited:
                    tree_links.append({"source": root_url, "target": u})

            return {"nodes": nodes, "links": tree_links}


db = GraphManager()