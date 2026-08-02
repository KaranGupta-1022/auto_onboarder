import chromadb
from sentence_transformers import SentenceTransformer
import os
import hashlib

# Chunking lives in api/chunking.py so there is exactly one implementation.
# `api/` has no __init__.py and relies on namespace packages, so this resolves
# only when the script is run from the repo root - which is how it is documented
# and how pipeline.py invokes it.
from api.chunking import SCHEMA_VERSION, chunk_repo_document

def get_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()

def check_schema(collection):
    """Refuse to write into a collection built by an older chunker."""
    if collection.count() == 0:
        return
    existing = collection.peek(limit=1)
    metadatas = existing.get("metadatas") or []
    found = metadatas[0].get("schema") if metadatas else None
    if found != SCHEMA_VERSION:
        raise SystemExit(
            f"\nERROR: collection 'repo_docs' holds records with schema={found!r}, "
            f"but this script writes schema={SCHEMA_VERSION}.\n"
            "Upsert only overwrites matching IDs, so re-running would leave the old "
            "records in place and mix two incompatible shapes in one collection.\n\n"
            "Delete the collection first, then re-run this script:\n"
            "  python -c \"import chromadb; "
            "chromadb.PersistentClient(path='./chroma_db').delete_collection('repo_docs')\"\n"
        )

def main():
    if not os.path.exists("repo_content.md"):
        print("Run scraper first.")
        return                               
    
    with open("repo_content.md", "r", encoding="utf-8") as f:
        content = f.read()

    useful_chunks, chunk_metadatas, skipped = chunk_repo_document(content)

    model = SentenceTransformer('all-MiniLM-L12-v2')
    client = chromadb.PersistentClient(path="./chroma_db")
    
    # We don't delete the collection anymore; we let Hashing handle updates
    collection = client.get_or_create_collection(name="repo_docs")
    check_schema(collection)

    if skipped:
        print(f"Skipped {len(skipped)} ignored/near-empty path(s): {', '.join(skipped)}")

    batch_size = 50
    for i in range(0, len(useful_chunks), batch_size):
        batch_text = useful_chunks[i:i+batch_size]
        batch_meta = chunk_metadatas[i:i+batch_size]
        
        embeddings = model.encode(batch_text).tolist()
        
        # Optimization: Use SHA-256 Hashes as IDs to prevent duplicates if you run this twice
        collection.upsert(
            ids=[get_hash(t) for t in batch_text],
            embeddings=embeddings,
            documents=batch_text,
            metadatas=batch_meta
        )
        print(f"Stored {i + len(batch_text)}/{len(useful_chunks)}")

    print("\nDatabase updated with hashed IDs and Metadata!")

if __name__ == "__main__":
    main()