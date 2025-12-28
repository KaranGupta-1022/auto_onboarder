# api/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
    MODEL_NAME = os.getenv("MODEL_NAME", "all-MiniLM-L12-v2")
    COLLECTION_NAME = os.getenv("COLLECTION_NAME", "repo_docs")
    # For Crawl4AI / GitHub
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")