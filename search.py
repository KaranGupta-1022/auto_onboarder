import chromadb 
from sentence_transformers import SentenceTransformer 

def main():
    # Initialize the embedding model
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Create CHromaDB client
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="repo_docs")
    
    # Error handling for non-existent collection
    if collection is None:
        print("Collection 'repo_docs' does not exist.")
        return
    
    while True:
        query = input("Enter your query (or 'exit' to quit): ")
        query = query.strip()
        if query.lower() == 'exit':
            break
        if not query:
            print("Please enter a valid query.")
            continue
        # Create a embedding for the query
        query_embedding = model.encode(query).tolist()
        #Look for similiar chuncks in repo_docs 
        results = collection.query( 
            query_embeddings=query_embedding,
            n_results=5, # number of similar results to retrieve
        )
        
        # Printing the results 
        print(f"Top {len(results['ids'])} results for query: '{query}'")
        if results['documents'] and results['documents'][0]:
            for i, (doc, scores) in enumerate(zip(results['documents'][0], results   ['distances'][0]), 1):
                similarity = 1 - scores # Convert distance to similarity
                print(f"{i}. [Similarity: {similarity:.2%}]")
                print(f" {doc[:200]}")  
                print("-" * 40)
        else: 
            print("No results found.")
            
if __name__ == "__main__":
    main()
        