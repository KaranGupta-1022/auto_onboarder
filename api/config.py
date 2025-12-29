# api/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db") 
    EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L12-v2")
    CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "repo_docs")
    LOG_LEVEL  =os.getenv("LOG_LEVEL", "INFO")
    # For Crawl4AI / GitHub
    # GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "") 
    API_PORT = int(os.getenv("API_PORT", 8000))
    
config = Config()
    