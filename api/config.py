# api/config.py
import os
from dotenv import load_dotenv

load_dotenv()

def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
    # In-cluster (Phase 9): CHROMA_HOST points at the ghostkube-chroma StatefulSet
    # and pipeline.py uses HttpClient. Local/compose: CHROMA_HOST is unset and
    # pipeline.py falls back to PersistentClient(path=CHROMA_PATH) as before.
    CHROMA_HOST = os.getenv("CHROMA_HOST", "")
    CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
    EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L12-v2")
    CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "repo_docs")
    LOG_LEVEL  =os.getenv("LOG_LEVEL", "INFO")
    # For Crawl4AI / GitHub
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    API_PORT = int(os.getenv("API_PORT", 8000))

    # Cross-encoder reranking is OFF by default because it was measured to make
    # retrieval WORSE on this domain: hit@1 fell 100% -> 83% on one repo and
    # 70% -> 60% on another. ms-marco is trained on natural-language web
    # passages and has no training signal for source code, so it reads a code
    # chunk as poor prose and demotes it. Do not flip this back on without
    # re-running the eval set; a code-aware reranker (BAAI/bge-reranker-base) or
    # the Groq reranker in Phase 13 are the candidates worth measuring.
    RERANK_ENABLED = _flag("RERANK_ENABLED", False)

    # Chunks pulled from Chroma before file-level pooling collapses them. Wide
    # enough that pooling has something to work with; at ~20ms a query it's free.
    RETRIEVAL_POOL_SIZE = int(os.getenv("RETRIEVAL_POOL_SIZE", 30))

    # Ghost Note feedback lands here as JSONL - one append-only event per line.
    # Deliberately NOT a Chroma collection: this is event data, and writing it
    # into the vector store would pollute retrieval with records that are not
    # repository content.
    FEEDBACK_PATH = os.getenv("FEEDBACK_PATH", "./feedback.jsonl")

    # Shadow Sidecar heartbeats (PRD 4B) land here as JSONL, same append-only
    # pattern as feedback. Pod liveness/state, not retrieval content - never
    # written to Chroma.
    POD_STATE_PATH = os.getenv("POD_STATE_PATH", "./pod_state.jsonl")

    # Phase 8.5 PR ingestion: closed-and-merged PRs older than this are not
    # walked. All PRs is too much for a rate-limited walk on an active repo,
    # so this is a deliberate knob rather than a hardcoded constant - see
    # api/pr_ingest.py::list_merged_prs and api/README.md.
    PR_LOOKBACK_MONTHS = int(os.getenv("PR_LOOKBACK_MONTHS", 6))

config = Config()
    