import chromeadb 
from setence_transformers import SentenceTransformer
import os 

def main():
    # Initialize the embedding model
    if not os.path.exists("repo_content.md"):
        print("repo_content.md doesn't exist. Please runt the scraper first.")
        return 
    
    # Load the content from the markdown file
    with open("repo_content.md", "r", encoding="utf-8") as f:
        content = f.read()

    #Split content into smaller chunks 
    chunk_size = 500
    chunks = []
    for i in range (0, len(content), chunk_size):
        chunk = content[i:i+chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    print(f"Total chunks created: {len(chunks)}")

    # Initialize the embedding model
    model = SentenceTransformer('all-MiniLM-L6-v2')
    # Create CHromeDB client
    client = chromeadb.Client()
    # Getting (or creating) a collection
    collection = client.get_or_create_collection(name="repo_docs")

    # Store each chunk with its embedding
    for i, chunk in enumerate(chunks, 1):
        embedding = model.encode(chunk).tolist()
        collection.add(
            ids=[f"chunk_{i}"], # unique ID for each chunk
            embeddings=embedding, # embedding vector
            documents=[chunk], # original text chunk
            metadatas=[{"chunk_index": i}]
        )
    
        if i % 10 == 0 or i == len(chunks):
            print(f"Stored {i}/{len(chunks)} chunks")
        
if __name__ == "__main__":
    main()