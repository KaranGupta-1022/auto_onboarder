import chromadb 
from sentence_transformers import SentenceTransformer
import os 

def main():
    # 1. Validation
    if not os.path.exists("repo_content.md"):
        print("repo_content.md doesn't exist. Please run the scraper first.")
        return 
    
    # 2. Load the content
    with open("repo_content.md", "r", encoding="utf-8") as f:
        content = f.read()

    # 3. Smart Splitting
    # Instead of every 500 chars, we split by the file headers your scraper made
    raw_blocks = content.split("## File: ")
    
    useful_chunks = []
    # Files that usually contain "garbage" metadata that ruins search results
    ignore_list = ["package-lock.json", "yarn.lock", "node_modules", ".next", "dist", "bin"]

    for block in raw_blocks:
        if not block.strip():
            continue
            
        # Extract filename (the first line of the block)
        filename = block.split('\n')[0].strip()
        
        # Check if this file should be ignored
        if any(trash in filename.lower() for trash in ignore_list):
            print(f"Skipping metadata file: {filename}")
            continue

        # If the file is huge (like a long CSS or JSON file), we still sub-chunk it
        # but we keep the filename context inside every chunk!
        if len(block) > 800:
            sub_size = 800
            for i in range(0, len(block), sub_size):
                sub_chunk = block[i:i+sub_size]
                useful_chunks.append(f"File: {filename}\nContent: {sub_chunk}")
        else:
            useful_chunks.append(f"File: {filename}\nContent: {block}")

    print(f"\nCreated {len(useful_chunks)} useful code chunks (Ignored lockfiles/dist).")

    # 4. Initialize AI Model
    model = SentenceTransformer('all-MiniLM-L12-v2')
    
    # 5. Setup Persistent Database
    # This saves to a folder so the data doesn't disappear
    client = chromadb.PersistentClient(path="./chroma_db")
    
    # Delete old collection if it exists to start fresh
    try:
        client.delete_collection(name="repo_docs")
    except:
        pass
        
    collection = client.get_or_create_collection(name="repo_docs")

    # 6. Store in Batches (Much faster than a loop)
    print("Embedding and storing chunks...")
    
    # We process in batches of 100 to avoid memory issues
    batch_size = 100
    for i in range(0, len(useful_chunks), batch_size):
        batch = useful_chunks[i:i+batch_size]
        
        # Generate embeddings for the whole batch at once
        embeddings = model.encode(batch).tolist()
        
        collection.add(
            ids=[f"chunk_{j}" for j in range(i, i + len(batch))],
            embeddings=embeddings,
            documents=batch,
            metadatas=[{"source": "github_repo"} for _ in range(len(batch))]
        )
        print(f"Progress: {i + len(batch)}/{len(useful_chunks)}")

    print("\n✅ Success! Database is ready. Now run your search.py")

if __name__ == "__main__":
    main()