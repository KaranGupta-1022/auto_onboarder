import chromadb
from sentence_transformers import SentenceTransformer

# Chunks pulled before pooling collapses them to one entry per file.
POOL_SIZE = 30
# Anything past this Chroma distance is treated as noise. Showing a bad match is
# worse than showing nothing - it teaches the user to stop trusting the tool.
MAX_DISTANCE = 1.3


def expand_query(user_input: str) -> str:
    """If the user asks about a 'file' or 'code', bias toward source files."""
    if "file" in user_input.lower() or "code" in user_input.lower():
        return f"definition of {user_input} in source code"
    return user_input


def pool_by_file(documents, distances, metadatas, top_k=5, max_distance=MAX_DISTANCE):
    """File-level max-score pooling.

    Group the candidate pool by path and keep only each file's single best chunk.
    Without this one file can occupy several of the top slots while the correct
    file sits just below the cut - a real source file usually has several decent
    chunks, while a doc that happens to describe the same thing has one lucky
    paragraph.

    Returns [(path, doc, distance)] sorted best-first. Shared with eval/run_eval.py
    so the harness measures exactly what the CLI does.
    """
    best = {}
    for doc, score, meta in zip(documents, distances, metadatas):
        if max_distance is not None and score > max_distance:
            continue
        path = meta['path']
        if path not in best or score < best[path][1]:
            best[path] = (doc, score)
    ranked = sorted(best.items(), key=lambda kv: kv[1][1])[:top_k]
    return [(path, doc, score) for path, (doc, score) in ranked]


def main():
    model = SentenceTransformer('all-MiniLM-L12-v2')
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(name="repo_docs")
    
    while True:
        user_input = input("\nWhat do you want to find in the code? (or 'exit'): ")
        if user_input.lower() == 'exit': break
        
        query_embedding = model.encode(expand_query(user_input)).tolist()

        # Retrieve a wide pool of chunks so the file-level pooling below has
        # something to work with. At ~20ms a query the extra width is free.
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=POOL_SIZE,
        )

        ranked = []
        if results['documents'] and results['documents'][0]:
            ranked = pool_by_file(results['documents'][0],
                                  results['distances'][0],
                                  results['metadatas'][0],
                                  top_k=5)

        if ranked:
            print(f"\nFound relevant snippets:")
            for i, (path, doc, score) in enumerate(ranked, 1):
                print(f"{i}. [Score: {score:.4f}] PATH: {path}")
                # Print the middle of the chunk to avoid just seeing headers
                print(f"{doc[:600]}...")
                print("-" * 40)
        else:
            print("No high-confidence matches found.")

if __name__ == "__main__":
    main()