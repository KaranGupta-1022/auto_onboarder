# api/synthesis.py
import json
import logging
import os

from groq import Groq

from .config import Config

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=Config.GROQ_API_KEY)
    return _client


def _load_cache() -> dict:
    if not os.path.exists(Config.SYNTHESIS_CACHE_PATH):
        return {}
    try:
        with open(Config.SYNTHESIS_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("Synthesis cache at %s is unreadable; starting empty", Config.SYNTHESIS_CACHE_PATH)
        return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(Config.SYNTHESIS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except OSError:
        logger.warning("Could not write synthesis cache to %s", Config.SYNTHESIS_CACHE_PATH)


_SYSTEM_PROMPT = (
    "You write terse developer notes, not conversation. Reply with exactly one or "
    "two sentences and nothing else: no preamble, no \"based on the context\" "
    "framing, no bullet points, no hedging about what you can't be sure of. If the "
    "context doesn't explain the behavior, say so in one short sentence instead of "
    "guessing."
)


def _build_prompt(chunks: list[dict], service_name: str | None) -> str:
    context = "\n\n".join(
        f"# {c['metadata'].get('path', 'unknown')}\n{c['text']}" for c in chunks
    )
    subject = f" for the {service_name} service" if service_name else ""
    return (
        f"What does this code do{subject}, and is there a known gotcha? Use only "
        f"the context below.\n\n{context}"
    )


def synthesize(chunks: list[dict], service_name: str | None = None) -> dict:
    """Turn the top retrieved chunks into a short, cited summary.

    `chunks` is the same shape search_ghost_notes() already returns: a list of
    dicts with "chunk_id", "text", and "metadata" (metadata["path"] is the
    citation), pre-sorted by relevance. The top chunk decides the cache key
    and the fallback/citation path.
    """
    if not chunks:
        return {"summary": "", "source_path": None, "synthesized": False}

    top = chunks[0]
    source_path = top["metadata"].get("path") or top["metadata"].get("source_url") or "unknown"
    fallback_summary = top["text"][:300] + "..." if len(top["text"]) > 300 else top["text"]

    if not Config.SYNTHESIS_ENABLED or not Config.GROQ_API_KEY:
        return {"summary": fallback_summary, "source_path": source_path, "synthesized": False}

    cache_key = top["chunk_id"]
    cache = _load_cache()
    if cache_key in cache:
        return cache[cache_key]

    try:
        response = _get_client().chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(chunks, service_name)},
            ],
            max_tokens=80,
            temperature=0.2,
        )
        result = {
            "summary": response.choices[0].message.content.strip(),
            "source_path": source_path,
            "synthesized": True,
        }
    except Exception as e:
        logger.warning("Groq synthesis failed, falling back to raw chunk: %s", e)
        return {"summary": fallback_summary, "source_path": source_path, "synthesized": False}

    cache[cache_key] = result
    _save_cache(cache)
    return result
