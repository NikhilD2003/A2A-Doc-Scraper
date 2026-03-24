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
            keep_alive=True,
            max_connection_lifetime=30 * 60,
            max_connection_pool_size=50
        )

    def close(self):
        if self.driver:
            self.driver.close()

    # --- NEW: AUTOMATIC CLEAN SLATE PROTOCOL ---
    def clear_database(self):
        query = "MATCH (n) DETACH DELETE n"
        with self.driver.session() as session:
            session.run(query)

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

    def execute_read_query(self, query: str):
        with self.driver.session() as session:
            try:
                result = session.run(query)
                return [record.data() for record in result]
            except Exception as e:
                return [{"error": f"Invalid Cypher Query generated: {str(e)}"}]

    def get_graph_data(self, target_url: str):
        nodes_query = """
        MATCH (n:Topic)
        WHERE n.url STARTS WITH $target_url
        RETURN n.url AS id, n.content AS content
        """

        with self.driver.session() as session:
            nodes_result = session.run(nodes_query, target_url=target_url)
            base_url = target_url.rstrip('/')

            all_nodes = {}
            links = set()

            def create_label(url_string):
                label = url_string.split('/')[-1]
                label = label.replace('.html', '').replace('.md', '').replace('.rst', '').replace('.txt', '')
                if not label or url_string == base_url:
                    return "Home"
                return label.replace('-', ' ').title()

            def add_node(url_string, is_scraped=True, content=""):
                if url_string not in all_nodes:
                    all_nodes[url_string] = {
                        "id": url_string,
                        "label": create_label(url_string),
                        "content": content if is_scraped else "📁 **Folder Directory**\n\nNo direct content was scraped for this folder, but it contains the child pages linked below."
                    }

            # Load all physically scraped nodes with the 15-character ghost page filter
            for record in nodes_result:
                url = record["id"].rstrip('/')
                content = record.get("content") or ""

                if len(content.strip()) > 15:
                    add_node(url, is_scraped=True, content=content)

            if base_url not in all_nodes:
                add_node(base_url, is_scraped=False)

            # Build the hierarchy mathematically
            for url in list(all_nodes.keys()):
                if url == base_url:
                    continue

                current_url = url
                while current_url != base_url and len(current_url) > len(base_url):
                    parent_url = current_url.rsplit('/', 1)[0]

                    if not parent_url.startswith(base_url):
                        links.add((base_url, url))
                        break

                    if parent_url not in all_nodes:
                        add_node(parent_url, is_scraped=False)

                    links.add((parent_url, current_url))
                    current_url = parent_url

            formatted_links = [{"source": src, "target": tgt} for src, tgt in links]

            return {
                "nodes": list(all_nodes.values()),
                "links": formatted_links
            }


db = GraphManager()