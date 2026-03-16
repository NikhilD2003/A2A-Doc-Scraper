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

    # --- NEW FEATURE: INTERACTIVE GRAPH DATA ---
    def get_graph_data(self, target_url: str):
        query = """
        MATCH (a:Topic)-[r:REFERENCES]->(b:Topic)
        WHERE a.url STARTS WITH $target_url AND b.url STARTS WITH $target_url
        RETURN a.url AS source, b.url AS target
        """
        with self.driver.session() as session:
            result = session.run(query, target_url=target_url)
            nodes = set()
            links = []

            for record in result:
                source = record["source"]
                target = record["target"]
                nodes.add(source)
                nodes.add(target)
                links.append({"source": source, "target": target})

            return {
                "nodes": [{"id": n, "label": n.split('/')[-1] or n} for n in nodes],
                "links": links
            }


db = GraphManager()