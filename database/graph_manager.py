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

    # THE FIX: Added target_url parameter and STARTS WITH filtering
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


db = GraphManager()