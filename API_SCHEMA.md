# GhostKube API Schema

This document describes the **implemented** contract. It is the interface the Phase 11
`kubectl-ghost` Go plugin is written against — if the code and this file ever disagree again,
fix both in the same commit.

Request and response shapes are defined in `api/models.py`.

---

## POST /ingest
Ingest a GitHub repository (walked recursively) or a single document URL into the vector database.

### Request Body
```json
{
  "url": "https://github.com/owner/repo",
  "source_type": "repo",
  "metadata": {
    "project": "my-project",
    "team": "backend"
  }
}
```

**Parameters:**
- `url` (string, required): GitHub repository URL, or any single document URL
- `source_type` (string, optional): Type of source — `"repo"`, `"pr"`, `"slack"` (default: `"repo"`)
- `metadata` (object, optional): Extra flat key/values stored on every chunk. The reserved keys
  `path`, `extension`, `is_code` and `schema` cannot be overwritten by a caller.

When `url` is a GitHub repo, the API walks the repository recursively via the Contents API,
honouring the same extension allowlist and ignore patterns as the CLI scraper, and chunks the
result with the shared chunker in `api/chunking.py`. Chunks written by this endpoint are
schema-compatible with those written by `embed_and_store.py`.

### Response (Success — 200)
```json
{
  "status": "success",
  "chunks_ingested": 125,
  "total_characters": 108114,
  "message": "Ingested 125 chunks from 35 file(s) at https://github.com/owner/repo"
}
```

### Response (Error — 400)
```json
{
  "error": "No indexable content found at https://...",
  "status_code": 400
}
```

---

## POST /ghost-note
Search for relevant "ghost notes" from ingested content.

> **Note:** this is a **POST with a JSON body**, not a GET with query parameters. Earlier
> revisions of this document described `GET /ghost-note?q=&top_k=`; that endpoint never existed.

### Request Body
```json
{
  "query": "auth-service",
  "top_results": 5
}
```

**Parameters:**
- `query` (string, required): Search term or question
- `top_results` (integer, optional): Number of results to return (default: `5`)

### Response (Success — 200)
```json
{
  "query": "auth-service",
  "results": [
    {
      "chunk_id": "6a1f9c...e2",
      "text": "FILE PATH: app/supabase/server.js\nEXTENSION: .js\nCODE:\n...",
      "relevance_score": 0.4715,
      "metadata": {
        "path": "app/supabase/server.js",
        "extension": ".js",
        "is_code": true,
        "schema": 2,
        "source_url": "https://github.com/owner/repo",
        "source_type": "repo"
      }
    }
  ]
}
```

**Response fields:**
- `query`: The search term that was queried
- `results`: Array of matching chunks, at most `top_results` entries
  - `chunk_id`: `sha256` of the full chunk text — the ID it is stored under. Stable across
    re-ingests, and the handle you pass to `POST /feedback`
  - `text`: The chunk content, truncated to 300 characters
  - `relevance_score`: 0.0–1.0, higher is better
  - `metadata`: Chunk provenance — `path` is the field consumers should key on

**Ranking behaviour:** results are pooled at the **file** level. A wide pool of candidate chunks
is retrieved, grouped by `metadata.path`, and only each file's single best-scoring chunk is
returned — so one large file cannot occupy several of the top slots.

By default `relevance_score` is derived from vector distance as `1 / (1 + distance)`.
Cross-encoder reranking is **disabled by default** (`RERANK_ENABLED=false`) because it measured
*worse* than plain vector search on this domain — hit@1 fell from 100% to 83% on one repo and
from 70% to 60% on another. Enabling it changes how `relevance_score` is computed but not the
response shape.

### Response (Error — 422)
A missing or malformed `query` is rejected by FastAPI's request validation with a 422.

---

## POST /feedback
Record a 👍/👎 on a Ghost Note. This is what makes the PRD's relevance-score metric measurable;
Phase 11 (terminal) and Phase 12 (Console) are both consumers.

### Request Body
```json
{
  "chunk_id": "6a1f9c...e2",
  "query": "how does supabase authentication work",
  "rating": "up"
}
```

**Parameters:**
- `chunk_id` (string, required): the `chunk_id` from the `/ghost-note` result being rated
- `query` (string, required): the query that surfaced it, so relevance can be judged in context
- `rating` (string, required): `"up"` or `"down"` — anything else is rejected with a 422

### Response (Success — 200)
```json
{
  "recorded": true,
  "total_up": 1,
  "total_down": 0
}
```

Events are appended one JSON object per line to `FEEDBACK_PATH` (default `./feedback.jsonl`,
gitignored). Each line carries `chunk_id`, `query`, `rating` and a UTC `recorded_at`. This is
deliberately **not** a Chroma collection — it is append-only event data, and writing it into the
vector store would put non-repository records in the retrieval path.

`recorded` is `false` if the append failed (e.g. a read-only filesystem); the request still
returns 200 with the current totals rather than erroring.

---

## GET /feedback/summary
Aggregate feedback counts.

### Response (Success — 200)
```json
{
  "recorded": true,
  "total_up": 12,
  "total_down": 3
}
```

`recorded` is always `true` here — the field is shared with `POST /feedback`, where it is
meaningful.

---

## GET /health
Health check. Actually queries ChromaDB, so it can fail — Phase 9's readiness probe depends on that.

### Response (Healthy — 200)
```json
{
  "service": "GhostKube Brain API",
  "version": "1.0.0",
  "status": "ok",
  "chroma_connected": true,
  "chunk_count": 125
}
```

### Response (Vector store unreachable — 200)
```json
{
  "service": "GhostKube Brain API",
  "version": "1.0.0",
  "status": "error",
  "chroma_connected": false,
  "chunk_count": 0
}
```

**Response fields:**
- `status`: `"ok"` if ChromaDB responded, `"error"` otherwise
- `chroma_connected`: whether the collection could be queried
- `chunk_count`: number of chunks currently indexed (`0` when disconnected)

> Returns HTTP 200 in both cases; probes should key on the `status` / `chroma_connected` fields.

---

## GET /
Endpoint index plus a link to the auto-generated Swagger docs at `/docs`.
