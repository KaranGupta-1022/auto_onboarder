# api/rerank_groq.py
import logging

from groq import Groq

from .config import Config

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=Config.GROQ_API_KEY)
    return _client


def _build_prompt(query: str, candidates: list) -> str:
    listing = "\n\n".join(
        f"PATH: {meta.get('path', 'unknown')}\n{doc[:200]}"
        for doc, meta, _dist in candidates
    )
    return (
        f"Query: {query}\n\nCandidates:\n\n{listing}\n\n"
        "Which single candidate's PATH best answers the query? Reply with only "
        "that exact path, nothing else."
    )


def rerank(query: str, candidates: list) -> list:
    """Reorder up to 10 (doc, meta, dist) candidates by asking Groq which single
    one best answers the query, moving its pick to the front. Everything else
    keeps its original (bi-encoder) relative order.

    Never raises and never drops a candidate: a missing key, rate limit,
    timeout, network error, or a reply that doesn't match any candidate path
    all fall back to returning `candidates` unchanged - a reranker outage
    degrades to the bi-encoder's own order rather than breaking the search.
    """
    if not Config.GROQ_RERANK_ENABLED or not Config.GROQ_API_KEY or len(candidates) < 2:
        return candidates

    try:
        response = _get_client().chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[{"role": "user", "content": _build_prompt(query, candidates)}],
            max_tokens=30,
            temperature=0,
            timeout=Config.GROQ_RERANK_TIMEOUT_S,
        )
        reply = response.choices[0].message.content.strip().lower()
        for i, (doc, meta, dist) in enumerate(candidates):
            path = (meta.get("path") or "").lower()
            if path and path in reply:
                return [candidates[i]] + candidates[:i] + candidates[i + 1:]
    except Exception as e:
        logger.warning("Groq rerank failed, falling back to bi-encoder order: %s", e)

    return candidates
