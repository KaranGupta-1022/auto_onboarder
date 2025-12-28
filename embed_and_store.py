import chromadb 
from sentence_transformers import SentenceTransformer
import os 
import hashlib

def get_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()

def main():
    if not os.path.exists("repo_content.md"):
        print("Run scraper first.")
        return                               
    
    with open("repo_content.md", "r", encoding="utf-8") as f:
        content = f.read()

    # Split by the new "File Path" header
    raw_blocks = content.split("## File Path: ")
    useful_chunks = []
    chunk_metadatas = []
    
    ignore_list = ["package-lock.json", "yarn.lock", "node_modules", ".next", "dist", "bin"]

    for block in raw_blocks:
        if not block.strip() or "\n" not in block: continue
            
        full_path = block.split('\n')[0].strip()
        extension = os.path.splitext(full_path)[1]
        
        if any(trash in full_path.lower() for trash in ignore_list):
            continue

        # Sub-chunking strategy: Inject context into every single chunk
        sub_size = 1000
        for i in range(0, len(block), sub_size):
            text_segment = block[i:i+sub_size]
            # Optimization: Prepend file context so the AI always knows which file this code belongs to
            contextual_text = f"FILE PATH: {full_path}\nEXTENSION: {extension}\nCODE:\n{text_segment}"
            
            useful_chunks.append(contextual_text)
            chunk_metadatas.append({
                "path": full_path,
                "extension": extension,
                "is_code": extension not in ['.md', '.txt']
            })

    model = SentenceTransformer('all-MiniLM-L12-v2')
    client = chromadb.PersistentClient(path="./chroma_db")
    
    # We don't delete the collection anymore; we let Hashing handle updates
    collection = client.get_or_create_collection(name="repo_docs")

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