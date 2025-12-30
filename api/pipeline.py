import asyncio 
import logging 
import hashlib
import requests
import json
from sentence_transformers import SentenceTransformer, CrossEncoder
import chromadb
from crawl4ai import *

from .config import Config

logger = logging.getLogger(__name__)

# 1. Initialize Clients & Models
client = chromadb.PersistentClient(path=Config.CHROMA_PATH)
collection = client.get_or_create_collection(name=Config.CHROMA_COLLECTION_NAME)

# Embedding model (Bi-Encoder)
embedding_model = SentenceTransformer(Config.EMBED_MODEL_NAME)

# Optimization: Cross-Encoder for Reranking (Production Grade Search)
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

def get_chunk_id(url: str, content: str):
    """Generates a unique ID to prevent duplicates."""
    return hashlib.sha256(f"{url}_{content}".encode()).hexdigest()

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]: 
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i : i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    return chunks

async def ingest_url(url: str, source_type: str = "repo", metadata: dict[str, any] = None) -> dict[str, any]:
    """
    Scrape a URL, chunk it, embed it, and store in ChromaDB.
    """
    try:
        logger.info(f"Starting ingestion for URL: {url}")
        
        # Step 1: Fetch
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        markdown_content = response.text[:10000] # Increased limit slightly
        filename = url.split("/")[-1]
        
        # Step 2: Chunk
        chunks = chunk_text(markdown_content)
        logger.info(f"Created {len(chunks)} chunks")
        
        # Step 3: Embed and Store
        for i, chunk in enumerate(chunks, 1):
            # Optimization: Contextual Chunking (prepend filename)
            contextual_content = f"FILE: {filename}\n{chunk}"
            embedding = embedding_model.encode(contextual_content)
            
            # Metadata flattening (to avoid ChromaDB dict errors)
            chunk_metadata = {
                "source_url": url,
                "source_type": source_type,
                "chunk_number": i,
                "total_chunks": len(chunks),
            }
            
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, (str, int, float, bool, type(None))):
                        chunk_metadata[key] = value
                    else:
                        chunk_metadata[key] = json.dumps(value)
            
            # Optimization: Upsert with unique IDs to prevent DB bloat
            collection.upsert(
                ids=[get_chunk_id(url, chunk)],
                embeddings=[embedding.tolist()],
                documents=[contextual_content],
                metadatas=[chunk_metadata]
            )
        
        logger.info(f"Successfully stored {len(chunks)} chunks")
        
        # FIXED: Returning all fields required by your Pydantic IngestResponse model
        return {
            "status": "success",
            "chunks_ingested": len(chunks),
            "total_characters": len(markdown_content),
            "message": f"Ingested {len(chunks)} chunks from {url}"
        }
    
    except Exception as e:
        logger.error(f"Error during ingestion: {str(e)}")
        return {
            "status": "error",
            "chunks_ingested": 0,
            "total_characters": 0,
            "message": f"Error: {str(e)}"
        }

def search_ghost_notes(query: str, top_results: int = 5) -> dict[str, any]:
    try: 
        logger.info(f"Searching for query: {query}")
        
        if collection.count() == 0:
            return {"query": query, "results": []}
            
        query_embedding = embedding_model.encode(query).tolist()
        
        # Stage 1: Retrieval (Get 10 candidates)
        search_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=10,
            include=['documents', 'metadatas', 'distances']
        )

        results = []
        if search_results["documents"] and search_results["documents"][0]:
            docs = search_results["documents"][0]
            metas = search_results["metadatas"][0]

            # Stage 2: Reranking (Cross-Encoder)
            # This makes the "relevance_score" much more accurate than simple vector distance
            pairs = [[query, doc] for doc in docs]
            scores = reranker.predict(pairs)

            for i in range(len(docs)):
                # Normalize score to 0-1
                import numpy as np
                norm_score = 1 / (1 + np.exp(-scores[i])) 

                results.append({
                    "text": docs[i][:300] + "..." if len(docs[i]) > 300 else docs[i],
                    "relevance_score": float(norm_score),
                    "metadata": metas[i]
                })
            
            # Sort by reranked score
            results.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        return {
            "query": query,
            "results": results[:top_results]
        }        
        
    except Exception as e:
        logger.error(f"Error during search: {str(e)}")
        return {"query": query, "results": []}