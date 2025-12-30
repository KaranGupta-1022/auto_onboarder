import asyncio 
import logging 
from sentence_transformers import SentenceTransformer
import chromadb
from crawl4ai import *

from .config import Config

logger = logging.getLogger(__name__)

# Initialize ChromaDB client and collection
client = chromadb.PersistentClient(path=Config.CHROMA_PATH)
collection = client.get_or_create_collection(name=Config.CHROMA_COLLECTION_NAME)

# Initialize embedding model
embedding_model = SentenceTransformer(Config.EMBED_MODEL_NAME)

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]: 
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i : i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    return chunks

# Scrape a URL, chunk its content, embed, and store in ChromaDB
async def ingest_url(url: str, source_type: str = "repo", metadata: dict[str, any] = None) -> dict[str, any]:
    """
    Scrape a URL, chunk it, embed it, and store in ChromaDB.
    """
    try:
        logger.info(f"Starting ingestion for URL: {url}")
        
        # Step 1: Fetch the page using requests (simpler, Windows-friendly)
        import requests
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        markdown_content = response.text[:5000]  # Limit to first 5000 chars for testing
        
        logger.info(f"Fetched {len(markdown_content)} characters from {url}")
        
        # Step 2: Chunk the content
        chunks = chunk_text(markdown_content)
        logger.info(f"Created {len(chunks)} chunks")
        
        # Step 3: Embed and store each chunk
        for i, chunk in enumerate(chunks, 1):
            # Create embedding
            embedding = embedding_model.encode(chunk)
            
            # Prepare metadata - FLAT ONLY (no nested dicts)
            chunk_metadata = {
                "source_url": url,
                "source_type": source_type,
                "chunk_number": i,
                "total_chunks": len(chunks),
            }
            
            # Add user metadata if provided, but flatten it
            if metadata:
                for key, value in metadata.items():
                    # Convert complex types to strings
                    if isinstance(value, (str, int, float, bool, type(None))):
                        chunk_metadata[key] = value
                    else:
                        # Convert dicts, lists, etc. to JSON strings
                        import json
                        chunk_metadata[key] = json.dumps(value)
            
            # Store in ChromaDB
            collection.add(
                ids=[f"{url}_{i}"],
                embeddings=[embedding.tolist()],
                documents=[chunk],
                metadatas=[chunk_metadata]
            )
        
        logger.info(f"Successfully stored {len(chunks)} chunks")
        
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
        
# Search for relevent chunks given a query
def search_ghost_notes(query: str, top_results: int = 5) -> dict[str, any]:
    try: 
        logger.info(f"Searching for query: {query}")
        
        # Check if collection is empty
        if collection.count() == 0:
            logger.warning("Repo Notes are empty")
            return {
                "query": query,
                "results": []
            }
            
        # Generate embedding for the query
        query_embedding = embedding_model.encode(query).tolist()
        # Perform the search
        search_results = collection.query (
            query_embeddings=[query_embedding],
            n_results=top_results,
            include=['documents', 'metadatas', 'distances']
        )
        # Format results
        results = []
        if search_results["documents"] and search_results["documents"][0]:
            for doc, metadata, distance in zip(
                search_results["documents"][0],
                search_results["metadatas"][0],
                search_results["distances"][0]
            ):
                # Convert distance to similarity 
                relevance_score = 1 - (distance / 2) # Assuming distances are in [0, 2]
                relevance_score = max(0.0, min(1.0, relevance_score)) # Clamp between 0 and 1
                
                results.append({
                    "text": doc[:300] + "..." if len(doc) > 300 else doc, # Truncate long texts
                    "relevance_score": relevance_score,
                    "metadata": metadata
                })
        
        logger.info(f"Found {len(results)} results for query: {query}")
        return {
            "query": query,
            "results": results
        }        
        
    except Exception as e:
        logger.error(f"Error during search: {str(e)}")
        return {
            "query": query,
            "results": []
        }
