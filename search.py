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

        # Retrieve a wide pool of chunks so the file-level pooling below has
        # something to work with. At ~20ms a query the extra width is free.
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=30,
        )

        if results['documents'] and results['documents'][0]:
            # File-level max-score pooling: group the pool by path and keep only
            # each file's single best chunk. Without this one file can occupy
            # several of the top slots while the correct file sits just below the
            # cut - a real source file usually has several decent chunks, while a
            # doc that happens to describe the same thing has one lucky paragraph.
            best = {}
            for doc, score, meta in zip(results['documents'][0],
                                        results['distances'][0],
                                        results['metadatas'][0]):
                # Filter out "Garbage" matches
                if score > 1.3:
                    continue
                path = meta['path']
                if path not in best or score < best[path][1]:
                    best[path] = (doc, score)

            ranked = sorted(best.items(), key=lambda kv: kv[1][1])[:5]

            if ranked:
                print(f"\nFound relevant snippets:")
                for i, (path, (doc, score)) in enumerate(ranked, 1):
                    print(f"{i}. [Score: {score:.4f}] PATH: {path}")
                    # Print the middle of the chunk to avoid just seeing headers
                    print(f"{doc[:600]}...")
                    print("-" * 40)
            else:
                print("No high-confidence matches found.")
        else:
            print("No high-confidence matches found.")

if __name__ == "__main__":
    main()