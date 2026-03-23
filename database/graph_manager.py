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
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            keep_alive = True,  # Sends TCP keep-alive pings
            max_connection_lifetime = 30 * 60,  # Recycles connections after 30 mins
            max_connection_pool_size = 50
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

    # --- THE FIX: STRICT URL FOLDER PARSER WITH SYNTHETIC NODES ---
    def get_graph_data(self, target_url: str):
        nodes_query = """
        MATCH (n:Topic)
        WHERE n.url STARTS WITH $target_url
        RETURN n.url AS id, n.content AS content
        """

        with self.driver.session() as session:
            nodes_result = session.run(nodes_query, target_url=target_url)

            # Normalize target URL (remove trailing slash)
            base_url = target_url.rstrip('/')

            all_nodes = {}
            links = set()

            # Helper function to create clean labels
            def create_label(url_string):
                label = url_string.split('/')[-1]
                label = label.replace('.html', '').replace('.md', '').replace('.rst', '').replace('.txt', '')
                if not label or url_string == base_url:
                    return "Home"
                # Make it pretty (e.g. "a2a-and-mcp" -> "A2a And Mcp")
                return label.replace('-', ' ').title()

            # Helper function to add a node to our dictionary
            def add_node(url_string, is_scraped=True, content=""):
                if url_string not in all_nodes:
                    all_nodes[url_string] = {
                        "id": url_string,
                        "label": create_label(url_string),
                        "content": content if is_scraped else "📁 **Folder Directory**\n\nNo direct content was scraped for this folder, but it contains the child pages linked below."
                    }

            # 1. Load all physically scraped nodes
            for record in nodes_result:
                url = record["id"].rstrip('/')
                add_node(url, is_scraped=True, content=record["content"])

            # Ensure the root node exists
            if base_url not in all_nodes:
                add_node(base_url, is_scraped=False)

            # 2. Build the hierarchy mathematically based on URL slashes
            for url in list(all_nodes.keys()):
                if url == base_url:
                    continue

                current_url = url
                # Work our way backwards up the folder tree until we hit the base URL
                while current_url != base_url and len(current_url) > len(base_url):
                    # Chop off the last segment to find the parent folder
                    # e.g., site.com/latest/topics/a2a -> site.com/latest/topics
                    parent_url = current_url.rsplit('/', 1)[0]

                    # Safety check: don't go higher than the target URL
                    if not parent_url.startswith(base_url):
                        links.add((base_url, url))
                        break

                    # If this folder doesn't exist as a node yet, synthesize it!
                    if parent_url not in all_nodes:
                        add_node(parent_url, is_scraped=False)

                    # Draw the line from the folder to the file
                    links.add((parent_url, current_url))

                    # Move up to the next folder level for the loop
                    current_url = parent_url

            formatted_links = [{"source": src, "target": tgt} for src, tgt in links]

            return {
                "nodes": list(all_nodes.values()),
                "links": formatted_links
            }


db = GraphManager()