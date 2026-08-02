"""Retrieval evaluation harness.

Every retrieval number quoted in GhostKube_Guide.md came from a throwaway script
that no longer exists, which made none of them reproducible. This is the
permanent version.

It measures exactly what search.py does: same embedding model, same pool size,
same file-level max-score pooling, same distance cutoff - `pool_by_file` is
imported from search.py rather than reimplemented, so the harness cannot drift
away from the thing it is supposed to be measuring.

Run from the repo root:
    python eval/run_eval.py eval/queries_meetme.json

The query sets are incomplete (see the _comment entry in each JSON file); the
published figures need the full 12 / 20 queries to reproduce.

Note that a query set only makes sense against the corpus it was written for -
chroma_db holds one repo at a time, so running queries_f1.json against a MeetMe
index will correctly report near-zero.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from sentence_transformers import SentenceTransformer

from search import MAX_DISTANCE, POOL_SIZE, expand_query, pool_by_file

CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
COLLECTION = os.getenv("CHROMA_COLLECTION_NAME", "repo_docs")
EMBED_MODEL = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L12-v2")


def load_queries(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    # Entries carrying only a _comment (query: null) are documentation, not cases.
    return [q for q in raw if q.get("query")]


def rank_of(expected_path, ranked):
    """1-based rank of the first result whose path matches, else None.

    Substring match: the seeded expectations are a mix of full paths
    ("app/supabase/server.js") and bare filenames ("WorkflowBox.jsx").
    """
    for i, (path, _doc, _score) in enumerate(ranked, 1):
        if expected_path.lower() in path.lower():
            return i
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python eval/run_eval.py eval/queries_meetme.json")
        return 1
    query_file = sys.argv[1]

    cases = load_queries(query_file)
    if not cases:
        print(f"No usable queries in {query_file}")
        return 1

    model = SentenceTransformer(EMBED_MODEL)
    collection = chromadb.PersistentClient(path=CHROMA_PATH).get_or_create_collection(
        name=COLLECTION
    )
    total_chunks = collection.count()

    print(f"\nEval set : {query_file} ({len(cases)} queries)")
    print(f"Index    : {COLLECTION} at {CHROMA_PATH} ({total_chunks} chunks)")
    print(f"Model    : {EMBED_MODEL}   pool={POOL_SIZE}  max_distance={MAX_DISTANCE}\n")

    rows = []
    hits = {1: 0, 3: 0, 5: 0}
    for case in cases:
        query, expected = case["query"], case["expected_path"]
        results = collection.query(
            query_embeddings=[model.encode(expand_query(query)).tolist()],
            n_results=POOL_SIZE,
        )
        ranked = []
        if results["documents"] and results["documents"][0]:
            ranked = pool_by_file(results["documents"][0],
                                  results["distances"][0],
                                  results["metadatas"][0],
                                  top_k=5)
        rank = rank_of(expected, ranked)
        for k in (1, 3, 5):
            if rank is not None and rank <= k:
                hits[k] += 1
        rows.append((query, expected, rank, ranked[0][0] if ranked else "(no result)"))

    width = max(len(r[0]) for r in rows)
    print(f"{'rank':>4}  {'query':{width}}  {'expected':28}  returned at rank 1")
    print("-" * (width + 62))
    for query, expected, rank, top in rows:
        marker = str(rank) if rank else "-"
        print(f"{marker:>4}  {query:{width}}  {expected[:28]:28}  {top}")

    n = len(cases)
    print()
    for k in (1, 3, 5):
        print(f"hit@{k}  {hits[k]}/{n} ({hits[k] / n:.0%})")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
