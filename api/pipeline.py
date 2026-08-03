import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone

import chromadb
import requests
from chromadb.errors import NotFoundError
from sentence_transformers import SentenceTransformer

from . import pr_ingest
from .chunking import (
    ALLOWED_EXTENSIONS, FILE_HEADER, SCHEMA_VERSION, chunk_repo_document, is_ignored,
)
from .config import Config

logger = logging.getLogger(__name__)

# 1. Initialize Clients & Models
# CHROMA_HOST set (in-cluster, Phase 9) -> talk to the ghostkube-chroma
# StatefulSet over HTTP. Unset (local/compose) -> PersistentClient on disk.
if Config.CHROMA_HOST:
    client = chromadb.HttpClient(host=Config.CHROMA_HOST, port=Config.CHROMA_PORT)
else:
    client = chromadb.PersistentClient(path=Config.CHROMA_PATH)
collection = client.get_or_create_collection(name=Config.CHROMA_COLLECTION_NAME)


def _call_collection(method_name: str, *args, **kwargs):
    """Call a method on the cached collection handle, transparently refreshing
    it once on a 404 and retrying.

    The `collection` object is bound to a specific server-side collection ID
    at the time it was fetched. If the Chroma server loses that collection
    (e.g. the ghostkube-chroma StatefulSet pod restarts against an empty or
    reset store) the cached handle starts raising NotFoundError on every call
    even though a fresh get_or_create_collection() would succeed - without
    this, the API process would need a manual restart to recover.
    """
    global collection
    try:
        return getattr(collection, method_name)(*args, **kwargs)
    except NotFoundError:
        logger.warning(
            "Cached Chroma collection handle is stale (server-side collection "
            "gone, likely a Chroma restart) - refreshing and retrying '%s'",
            method_name,
        )
        collection = client.get_or_create_collection(name=Config.CHROMA_COLLECTION_NAME)
        return getattr(collection, method_name)(*args, **kwargs)

# Embedding model (Bi-Encoder)
embedding_model = SentenceTransformer(Config.EMBED_MODEL_NAME)

# Cross-encoder reranking is off by default - it was measured to LOWER accuracy
# on this domain (see Config.RERANK_ENABLED). Loaded lazily so the ~90MB model is
# never downloaded or held in memory unless someone deliberately enables it.
_reranker = None


def get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        logger.warning(
            "RERANK_ENABLED is on. This reranker measured WORSE than plain vector "
            "search on both evaluation repos (100%%->83%%, 70%%->60%% hit@1)."
        )
        _reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    return _reranker


def get_chunk_id(content: str):
    """Content-addressed chunk ID.

    Must stay byte-identical to embed_and_store.py's get_hash(): the two
    ingestion paths write into one collection, so if they derive IDs differently
    the same file ingested twice lands as two copies instead of upserting over
    itself. The chunk text already embeds its own file path, so identical IDs
    really do mean identical chunks.
    """
    return hashlib.sha256(content.encode()).hexdigest()


def _github_repo_parts(url: str):
    """Return (owner, repo) if this is a GitHub repo URL, else None."""
    cleaned = url.strip().rstrip('/').split('/tree')[0]
    if "github.com/" not in cleaned:
        return None
    tail = cleaned.split("github.com/", 1)[1].split("/")
    if len(tail) < 2 or not tail[0] or not tail[1]:
        return None
    return tail[0], tail[1]


async def _fetch_repo_document(owner: str, repo: str) -> str:
    """Walk a GitHub repo recursively and return a repo_content.md-style document.

    Reuses the extension allowlist, ignore patterns, auth headers and rate-limit
    handling from the CLI scraper so both ingestion paths behave identically. The
    import is deliberately lazy: scrape_repo imports crawl4ai, which pulls in
    Playwright and costs ~25s, and the API must not pay that at startup.
    """
    import scrape_repo

    headers = dict(scrape_repo.HEADERS)
    if Config.GITHUB_TOKEN and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {Config.GITHUB_TOKEN}"

    files = []

    async def walk(path=""):
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        response = await asyncio.to_thread(
            requests.get, api_url, headers=headers, timeout=30
        )
        if response.status_code == 403:
            raise scrape_repo.RateLimitError(scrape_repo.rate_limit_message(response))
        if response.status_code != 200:
            logger.warning(
                "Skipping '%s' - GitHub returned %s %s",
                path or "/", response.status_code, response.reason,
            )
            return

        items = response.json()
        if isinstance(items, dict):
            items = [items]

        subdirs = []
        for item in items:
            full_path = item['path']
            if is_ignored(full_path):
                continue
            if item['type'] == 'file':
                if item['name'].endswith(ALLOWED_EXTENSIONS):
                    files.append((item['download_url'], full_path))
            elif item['type'] == 'dir':
                subdirs.append(full_path)

        for subdir in subdirs:
            await walk(subdir)

    await walk()
    logger.info("Found %d files in %s/%s", len(files), owner, repo)

    semaphore = asyncio.Semaphore(scrape_repo.MAX_CONCURRENT_FETCHES)
    results = [None] * len(files)

    async def fetch_one(index, file_url, full_path):
        async with semaphore:
            try:
                r = await asyncio.to_thread(requests.get, file_url, timeout=30)
                r.raise_for_status()
                results[index] = (full_path, r.text)
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", full_path, e)

    await asyncio.gather(*(
        fetch_one(i, u, p) for i, (u, p) in enumerate(files)
    ))

    document = f"# Repository: {owner}/{repo}\n\n"
    for entry in results:
        if entry is None:
            continue
        full_path, text = entry
        document += f"\n{FILE_HEADER}{full_path}\n{text}\n\n"
    return document


def _store(chunks, metadatas, extra_metadata: dict | None):
    """Embed a batch of chunks in one pass and upsert them."""
    if not chunks:
        return 0

    if extra_metadata:
        for meta in metadatas:
            for key, value in extra_metadata.items():
                # Chroma only accepts flat scalars, and the reserved keys below
                # are what search depends on - never let a caller overwrite them.
                # "service" is the notable non-reserved key: pass
                # IngestRequest.metadata={"service": "auth-service"} at ingest
                # time and search_ghost_notes() can later scope a query to it
                # via GhostNoteRequest.ghost_note_id="svc:auth-service".
                if key in ("path", "extension", "is_code", "schema"):
                    continue
                if isinstance(value, (str, int, float, bool)):
                    meta[key] = value
                elif value is not None:
                    meta[key] = str(value)

    batch_size = 50
    stored = 0
    for i in range(0, len(chunks), batch_size):
        batch_text = chunks[i:i + batch_size]
        batch_meta = metadatas[i:i + batch_size]
        # Batch the encode: one call for the whole batch rather than one call
        # per chunk inside a loop.
        embeddings = embedding_model.encode(batch_text).tolist()
        _call_collection(
            "upsert",
            ids=[get_chunk_id(t) for t in batch_text],
            embeddings=embeddings,
            documents=batch_text,
            metadatas=batch_meta,
        )
        stored += len(batch_text)
        logger.info("Stored %d/%d chunks", stored, len(chunks))
    return stored


async def ingest_url(url: str, source_type: str = "repo", metadata: dict | None = None) -> dict:
    """Ingest a GitHub repository (recursively), its PR/issue history, or a
    single document URL.

    Produces the exact same chunk text and metadata schema as the CLI pipeline,
    so both write compatible records into one collection.

    POST /ingest {"url": "<repo>", "source_type": "pr"} routes to
    pr_ingest.build_pr_document() instead of the file walk: closed-and-merged
    PRs from the last Config.PR_LOOKBACK_MONTHS months, chunked through the
    same chunk_repo_document() via the synthetic `pull/{n}` path.
    """
    try:
        logger.info("Starting ingestion for URL: %s (source_type=%s)", url, source_type)

        parts = _github_repo_parts(url)
        pr_metadata_by_path: dict = {}

        if source_type == "pr":
            if not parts:
                return {
                    "status": "error",
                    "chunks_ingested": 0,
                    "total_characters": 0,
                    "message": f"source_type='pr' requires a GitHub repo URL, got: {url}",
                }
            owner, repo = parts
            document, pr_metadata_by_path = await pr_ingest.build_pr_document(owner, repo)
        elif parts:
            owner, repo = parts
            document = await _fetch_repo_document(owner, repo)
        else:
            # Single document: wrap it in the same header format so it flows
            # through the identical chunker instead of a parallel code path.
            response = await asyncio.to_thread(requests.get, url, timeout=30)
            response.raise_for_status()
            filename = url.rstrip('/').split("/")[-1] or url
            document = f"\n{FILE_HEADER}{filename}\n{response.text}\n\n"

        chunks, metadatas, skipped = chunk_repo_document(document)
        if skipped:
            logger.info("Skipped %d ignored/near-empty path(s)", len(skipped))

        if not chunks:
            return {
                "status": "error",
                "chunks_ingested": 0,
                "total_characters": len(document),
                "message": f"No indexable content found at {url}",
            }

        for meta in metadatas:
            meta["source_url"] = url
            meta["source_type"] = source_type
            pr_meta = pr_metadata_by_path.get(meta["path"])
            if pr_meta:
                meta.update(pr_meta)

        stored = _store(chunks, metadatas, metadata)
        files_seen = len({m["path"] for m in metadatas})
        logger.info("Successfully stored %d chunks", stored)

        return {
            "status": "success",
            "chunks_ingested": stored,
            "total_characters": len(document),
            "message": f"Ingested {stored} chunks from {files_seen} file(s)/PR(s) at {url}",
        }

    except Exception as e:
        logger.error("Error during ingestion: %s", e)
        return {
            "status": "error",
            "chunks_ingested": 0,
            "total_characters": 0,
            "message": f"Error: {str(e)}",
        }


def search_ghost_notes(query: str, top_results: int = 5, ghost_note_id: str | None = None) -> dict:
    """Search for relevant chunks, optionally scoped to a webhook-resolved note ID.

    `ghost_note_id` is the raw GHOST_NOTE_ID env var the webhook injected,
    e.g. "svc:auth-service". Only the "svc:" form is understood: the suffix
    is used as a `where={"service": ...}` filter against chunk metadata, so
    a pod labeled ghostkube.io/service=auth-service only sees notes ingested
    with metadata={"service": "auth-service"} (see ingest_url's `metadata`
    param). Any other prefix, or no match at all, falls back to an
    unfiltered search rather than failing the request - a stale or
    unrecognized note ID should degrade to "search everything," not 500.
    """
    try:
        logger.info("Searching for query: %s", query)

        if _call_collection("count") == 0:
            return {"query": query, "results": []}

        service = None
        if ghost_note_id and ghost_note_id.startswith("svc:"):
            service = ghost_note_id[len("svc:"):] or None

        query_embedding = embedding_model.encode(query).tolist()

        # Retrieve a wide pool so the file-level pooling below has something to
        # collapse.
        search_results = _call_collection(
            "query",
            query_embeddings=[query_embedding],
            n_results=Config.RETRIEVAL_POOL_SIZE,
            include=['documents', 'metadatas', 'distances'],
            where={"service": service} if service else None,
        )

        if service and not (search_results["documents"] and search_results["documents"][0]):
            logger.warning(
                "No chunks matched service=%r for ghost_note_id=%r; falling back to unfiltered search",
                service, ghost_note_id,
            )
            search_results = _call_collection(
                "query",
                query_embeddings=[query_embedding],
                n_results=Config.RETRIEVAL_POOL_SIZE,
                include=['documents', 'metadatas', 'distances'],
            )

        if not (search_results["documents"] and search_results["documents"][0]):
            return {"query": query, "results": []}

        docs = search_results["documents"][0]
        metas = search_results["metadatas"][0]
        dists = search_results["distances"][0]

        # File-level max-score pooling: keep only each path's single best chunk.
        # Without this one file can occupy several of the top slots while the
        # correct file sits just below the cut.
        best = {}
        for doc, meta, dist in zip(docs, metas, dists):
            path = meta.get("path") or meta.get("source_url") or "unknown"
            if path not in best or dist < best[path][2]:
                best[path] = (doc, meta, dist)

        pooled = sorted(best.values(), key=lambda x: x[2])[:top_results]

        if Config.RERANK_ENABLED:
            reranker = get_reranker()
            scores = reranker.predict([[query, doc] for doc, _, _ in pooled])
            scored = [
                (doc, meta, 1 / (1 + pow(2.718281828459045, -float(s))))
                for (doc, meta, _), s in zip(pooled, scores)
            ]
            scored.sort(key=lambda x: x[2], reverse=True)
        else:
            # Derive relevance from vector distance so the response contract is
            # unchanged whether or not reranking is on. Lower distance -> higher
            # score, bounded to (0, 1].
            scored = [(doc, meta, 1 / (1 + float(dist))) for doc, meta, dist in pooled]

        results = [
            {
                # Hash the FULL chunk, not the truncated preview - this must
                # match the ID the chunk was stored under so feedback can be
                # tied back to it.
                "chunk_id": get_chunk_id(doc),
                "text": doc[:300] + "..." if len(doc) > 300 else doc,
                "relevance_score": float(score),
                "metadata": meta,
            }
            for doc, meta, score in scored
        ]

        return {"query": query, "results": results}

    except Exception as e:
        logger.error("Error during search: %s", e)
        return {"query": query, "results": []}


def _read_feedback():
    """Yield every recorded feedback event. Tolerates a missing or partial file."""
    path = Config.FEEDBACK_PATH
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A torn final line from an interrupted write shouldn't take the
                # whole summary down.
                logger.warning("Skipping malformed feedback line")


def feedback_summary() -> dict:
    up = down = 0
    for event in _read_feedback():
        if event.get("rating") == "up":
            up += 1
        elif event.get("rating") == "down":
            down += 1
    return {"total_up": up, "total_down": down}


def record_feedback(chunk_id: str, query: str, rating: str) -> dict:
    """Append one feedback event as JSONL.

    Append-only event data, kept out of Chroma on purpose: writing it into the
    vector store would put non-repository records in the retrieval path.
    """
    event = {
        "chunk_id": chunk_id,
        "query": query,
        "rating": rating,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(Config.FEEDBACK_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        recorded = True
    except OSError as e:
        logger.error("Could not write feedback: %s", e)
        recorded = False

    return {"recorded": recorded, **feedback_summary()}


def health_snapshot() -> dict:
    """Real health: actually touch Chroma so a broken store fails the check."""
    try:
        count = _call_collection("count")
        return {"status": "ok", "chroma_connected": True, "chunk_count": count}
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return {"status": "error", "chroma_connected": False, "chunk_count": 0}
