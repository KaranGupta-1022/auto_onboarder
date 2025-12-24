import chromadb 
import hashlib 
from datetime import datetime 
import re
from sentence_transformers import SentenceTransformer
import os 

def chunk_text_with_overlap(text, chunk_size=500, overlap=50):
    """Split text into chunks by paragraph boundaries with overlap for context continuity."""
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        # Check if adding the paragraph exceeds chunk size
        if len(current_chunk) + len(paragraph) > chunk_size and current_chunk:
            chunks.append(current_chunk)
            # Add overlap from end of current chunk to beginning of next
            if len(current_chunk) > overlap:
                overlap_text = current_chunk[-overlap:]
            else:
                overlap_text = current_chunk
            current_chunk = overlap_text + "\n\n" + paragraph
        else:
            # Add paragraph to current chunk
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph
    
    if current_chunk.strip():
        chunks.append(current_chunk)
    
    return chunks

def generate_chunk_id(filename, chunk_content, index):
    # Sanitize filename: replace non-alphanumeric chars with underscore
    # Make chunk ID unique with a hash of the content and a timestamp
    sanitized_filename = re.sub(r'[^a-zA-Z0-9_]', '_', filename)
    context_hash = hashlib.md5(chunk_content.encode('utf-8')).hexdigest()[:8]
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{sanitized_filename}_chunk{index}_{context_hash}_{timestamp}"

def is_valid_chunk(chunk):
    cleaned = re.sub(r'```.*?```|[ \n\t]+', '', chunk, flags=re.DOTALL)
    return len(cleaned) >= 20

def main():
  
    if not os.path.exists("repo_content.md"):
        print("repo_content.md doesn't exist. Please run the scraper first.")
        return 
    with open("repo_content.md", "r", encoding="utf-8") as f:
        content = f.read()
        
    raw_blocks = content.split("## File: ")
    useful_chunks = []
    chunk_ids = []
    global_chunk_index = 0
    ignore_list = ["package-lock.json", "yarn.lock", "node_modules", ".next", "dist", "bin"]

    for block in raw_blocks:
        if not block.strip():
            continue   
        filename = block.split('\n')[0].strip()
        if any(trash in filename.lower() for trash in ignore_list):
            print(f"Skipping metadata file: {filename}")
            continue

        # Use semantic chunking with overlap
        file_chunks = chunk_text_with_overlap(block, chunk_size=800, overlap=100)
        
        # Process each chunk in the file
        for index, chunk in enumerate(file_chunks):
            # Validate chunk before adding
            if not is_valid_chunk(chunk):
                print(f"Skipping trivial chunk from {filename}, index {index}")
                continue
            
            chunk_id = generate_chunk_id(filename, chunk, index)
            useful_chunks.append(f"File: {filename}\nContent: {chunk}")
            chunk_ids.append(chunk_id)
            global_chunk_index += 1
        
        

    print(f"\nCreated {len(useful_chunks)} valid code chunks (Ignored lockfiles/dist).")
    model = SentenceTransformer('all-MiniLM-L12-v2')
    client = chromadb.PersistentClient(path="./chroma_db")
    
    
    try:
        client.delete_collection(name="repo_docs")
    except:
        pass
        
    collection = client.get_or_create_collection(name="repo_docs")
    print("Embedding and storing chunks...")
    
    
    # Validate lengths match before batching
    assert len(useful_chunks) == len(chunk_ids), f"Mismatch: {len(useful_chunks)} chunks but {len(chunk_ids)} IDs"
    
    batch_size = 100
    # Process in batches to avoid memory issues
    for i in range(0, len(useful_chunks), batch_size): 
        batch = useful_chunks[i:i+batch_size]
        batch_ids = chunk_ids[i:i+batch_size]
        embeddings = model.encode(batch).tolist()
        
        collection.add(
            ids=batch_ids, # unique chunk IDs
            embeddings=embeddings, # embedding vectors
            documents=batch, # original text chunks
            metadatas=[
                {
                    "ingested_at": datetime.now().isoformat(),
                    "chunk_index": j
                }
                for j in range(len(batch))
            ]
        )
        print(f"Progress: {i + len(batch)}/{len(useful_chunks)}")
    print("\n Success! Database is ready. Now run your search.py")

if __name__ == "__main__":
    main()