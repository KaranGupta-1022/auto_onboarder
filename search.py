import chromadb 
from sentence_transformers import SentenceTransformer 

def main():
    model = SentenceTransformer('all-MiniLM-L12-v2')
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="repo_docs")
    
    while True:
        user_input = input("\nWhat do you want to find in the code? (or 'exit'): ")
        if user_input.lower() == 'exit': break
        
        # Optimization: Query Expansion
        # If the user asks "which file", we implicitly prioritize code files
        search_query = user_input
        if "file" in user_input.lower() or "code" in user_input.lower():
            search_query = f"definition of {user_input} in source code"

        query_embedding = model.encode(search_query).tolist()
        
        results = collection.query( 
            query_embeddings=[query_embedding],
            n_results=5,
            # Option: You could add a filter here like: where={"is_code": True}
        )
        
        if results['documents'] and results['documents'][0]:
            print(f"\nFound relevant snippets:")
            for i, (doc, score, meta) in enumerate(zip(results['documents'][0], results['distances'][0], results['metadatas'][0]), 1):
                
                # Filter out "Garbage" matches
                if score > 1.3:
                    continue
                
                print(f"{i}. [Score: {score:.4f}] PATH: {meta['path']}") 
                # Print the middle of the chunk to avoid just seeing headers
                print(f"{doc[:600]}...") 
                print("-" * 40)
        else: 
            print("No high-confidence matches found.")

if __name__ == "__main__":
    main()