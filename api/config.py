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

    # Phase 13: Groq note synthesis. Formatting on retrieved facts, not a
    # chatbot - see api/synthesis.py. Fails soft: missing key, rate limit, or
    # network error all fall back to the raw top chunk (synthesized=False),
    # never a 500.
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    SYNTHESIS_ENABLED = _flag("SYNTHESIS_ENABLED", True)

    # JSON map of chunk_id -> synthesized result. Keyed by chunk_id because the
    # same pod/chunk gets inspected repeatedly and re-generating an identical
    # summary burns both latency budget and Groq's free-tier quota.
    SYNTHESIS_CACHE_PATH = os.getenv("SYNTHESIS_CACHE_PATH", "./synthesis_cache.json")

        # Phase 13.2: optional Groq LLM reranker, MEASURED (not assumed) against
    # the bi-encoder-only baseline - see api/rerank_groq.py and the Phase 13.2
    # notes in GhostKube_Guide.md. Default OFF: the bi-encoder already hits
    # 100% hit@1 on the seeded eval queries, so an LLM reranker can only tie
    # or lose here - it only earns its place on a harder corpus. Same lesson
    # as the cross-encoder in RERANK_ENABLED above; don't repeat that mistake.
    GROQ_RERANK_ENABLED = _flag("GROQ_RERANK_ENABLED", False)
    GROQ_RERANK_TIMEOUT_S = float(os.getenv("GROQ_RERANK_TIMEOUT_S", "0.3"))

    # Phase 13.3 intent classifier: directory a fine-tuned DistilBERT
    # checkpoint is loaded from (scripts/train_intent.py writes here, once it
    # exists). Missing directory - the default until training happens - falls
    # back to the rule baseline in api/intent.py, the same
    # "baseline-is-the-automatic-fallback" pattern as the Groq reranker.
    INTENT_MODEL_DIR = os.getenv("INTENT_MODEL_DIR", "./models/intent")

    # Default OFF: measured against the rule baseline on a family-holdout
    # split (see GhostKube_Guide.md Phase 13.3 notes) and the fine-tuned
    # DistilBERT checkpoint lost decisively (31-42% vs 65% accuracy) under
    # both full fine-tuning and a frozen-backbone linear probe. A checkpoint
    # existing under INTENT_MODEL_DIR is not evidence it should be served -
    # same "measure before adopt" lesson as GROQ_RERANK_ENABLED and the
    # cross-encoder RERANK_ENABLED above. Flip this on only after a checkpoint
    # actually beats the rule baseline on held-out families.
    INTENT_MODEL_ENABLED = _flag("INTENT_MODEL_ENABLED", False)


config = Config()
    