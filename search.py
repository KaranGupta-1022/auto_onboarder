import chromadb 
from sentence_transformers import SentenceTransformer 

def main():
    model = SentenceTransformer('all-MiniLM-L12-v2')
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="repo_docs")
    
    while True:
        query = input("\nWhat do you want to find in the code? (or 'exit'): ")
        if query.lower() == 'exit': 
            break
        
        query_embedding = [model.encode(query).tolist()]
        results = collection.query( 
            query_embeddings=query_embedding,
            n_results=5,
        )
        
        if results['documents'] and results['documents'][0]:
            print(f"\nFound {len(results['documents'][0])} relevant snippets:")
            for i, (doc, score) in enumerate(zip(results['documents'][0], results['distances'][0]), 1):
                # Cosine distance is returned; smaller is better.
                # If score is > 1.2, it's probably not a good match.
                print(f"{i}. [Distance Score: {score:.4f}]") 
                print(f"{doc[:500]}...") # Print more context
                print("-" * 40)
        else: 
            print("No relevant code found.")

if __name__ == "__main__":
    main()