# api/pipeline.py
from sentence_transformers import SentenceTransformer
import chromadb
from .config import Config

class GhostPipeline:
    def __init__(self):
        self.model = SentenceTransformer(Config.MODEL_NAME)
        self.client = chromadb.PersistentClient(path=Config.CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(Config.COLLECTION_NAME)

    def ingest(self, repo_url: str):
        # 1. Call your Crawl4AI logic here
        # 2. Call your Embedding logic here
        return {"status": "success", "repo": repo_url}

    def search(self, query: str):
        query_embedding = self.model.encode(query).tolist()
        results = self.collection.query(query_embeddings=[query_embedding], n_results=3)
        # Format results into a list of GhostNoteResponse models
        return results