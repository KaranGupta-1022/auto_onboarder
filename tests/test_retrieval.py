"""Retrieval regression suite against the hermetic fixture corpus.

Floors (documented here, not tuned silently elsewhere):
- hit@1 >= 0.6 and hit@3 >= 0.8 on the 20 positive queries in
  eval/queries_fixture.json. Picked to fail on genuinely broken retrieval
  (wrong file entirely, a chunking regression, a pooling bug) while
  tolerating the odd close call between semantically adjacent fixture files
  (e.g. the Stripe charge backend vs. the Stripe Elements checkout form).
- At least half of the 10 negative queries return no candidate within
  search.MAX_DISTANCE. Negatives are on topics the fixture corpus does not
  cover at all (2FA, GraphQL, ...); the floor is loose because a bi-encoder
  will still surface its single closest available match for some of them -
  this only catches "negatives systematically return confident matches."
"""
import json
import os

import chromadb
import pytest

from api.chunking import chunk_repo_document
from api.pipeline import embedding_model, get_chunk_id
from search import POOL_SIZE, pool_by_file

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
QUERIES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "eval", "queries_fixture.json"
)


@pytest.fixture(scope="module")
def fixture_collection(tmp_path_factory):
    with open(os.path.join(FIXTURES_DIR, "repo_content.md"), encoding="utf-8") as f:
        content = f.read()
    chunks, metadatas, skipped = chunk_repo_document(content)
    # The "# Repository: ..." preamble before the first FILE_HEADER is expected
    # to skip - it has no real file body. Any other skip is a genuine problem.
    unexpected_skips = [p for p in skipped if p != "# Repository: ghostkube-fixtures/storefront"]
    assert not unexpected_skips, f"fixture corpus produced skipped paths: {unexpected_skips}"


    tmp_path = tmp_path_factory.mktemp("retrieval-fixture-chroma")
    client = chromadb.PersistentClient(path=str(tmp_path))
    collection = client.get_or_create_collection(name="fixture_docs")

    embeddings = embedding_model.encode(chunks).tolist()
    collection.upsert(
        ids=[get_chunk_id(c) for c in chunks],
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )
    return collection


def _search(collection, query, top_k=5):
    query_embedding = embedding_model.encode(query).tolist()
    results = collection.query(query_embeddings=[query_embedding], n_results=POOL_SIZE)
    if not (results["documents"] and results["documents"][0]):
        return []
    return pool_by_file(
        results["documents"][0], results["distances"][0], results["metadatas"][0], top_k=top_k
    )


def _load_cases():
    with open(QUERIES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return [c for c in raw if c.get("query")]


def test_retrieval_floors_on_fixture_corpus(fixture_collection):
    cases = _load_cases()
    positives = [c for c in cases if c["expected_path"]]
    negatives = [c for c in cases if not c["expected_path"]]
    assert len(positives) == 20
    assert len(negatives) == 10

    hits_at_1 = hits_at_3 = 0
    for case in positives:
        ranked_paths = [path for path, _doc, _score in _search(fixture_collection, case["query"])]
        if ranked_paths[:1] == [case["expected_path"]]:
            hits_at_1 += 1
        if case["expected_path"] in ranked_paths[:3]:
            hits_at_3 += 1

    hit_at_1_rate = hits_at_1 / len(positives)
    hit_at_3_rate = hits_at_3 / len(positives)
    assert hit_at_1_rate >= 0.6, f"hit@1 {hit_at_1_rate:.0%} below floor (0.6)"
    assert hit_at_3_rate >= 0.8, f"hit@3 {hit_at_3_rate:.0%} below floor (0.8)"

    no_match = sum(1 for c in negatives if not _search(fixture_collection, c["query"]))
    no_match_rate = no_match / len(negatives)
    assert no_match_rate >= 0.5, f"only {no_match_rate:.0%} of negatives had no confident match"
