# GhostKube Brain API — run notes

Service-specific notes only. See the root [`README.md`](../README.md) for what GhostKube is,
the architecture, and the cluster setup.

## Run locally

From the **repo root** (not from `api/`) — `api/app.py` uses package-relative imports, so the
app has to be loaded as `api.app`:

```bash
pip install -r api/requirements.txt
python -m uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

- REST: http://localhost:8000
- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Run in Docker

The build context is the **repo root** so that `api/` is importable as a package:

```bash
docker build -f api/Dockerfile -t ghostkube/api:dev .
docker run --rm -p 8000:8000 -v ghostkube_chroma:/app/chroma_db ghostkube/api:dev
```

Or with Compose (from `api/`):

```bash
docker compose up --build
```

Compose mounts the repo at `/app` for live reload and keeps the Chroma index in the
`chroma_data` named volume, so the index survives `docker compose down`.

## Environment variables

All are optional and have defaults in `api/config.py`; override via `.env` at the repo root
or via the environment.

| Variable                 | Default              | Purpose                               |
| ------------------------ | -------------------- | ------------------------------------- |
| `CHROMA_PATH`            | `./chroma_db`        | On-disk location of the vector store  |
| `CHROMA_COLLECTION_NAME` | `repo_docs`          | Chroma collection name                |
| `EMBED_MODEL_NAME`       | `all-MiniLM-L12-v2`  | sentence-transformers embedding model |
| `API_PORT`               | `8000`               | Port uvicorn binds                    |
| `LOG_LEVEL`              | `INFO`               | Logging verbosity                     |
| `PR_LOOKBACK_MONTHS`     | `6`                  | PR ingestion scope - see below        |

ChromaDB runs in-process via `PersistentClient` — there is no separate Chroma container to
point at, so there are no `CHROMA_HOST` / `CHROMA_PORT` settings.

## Endpoints

| Method | Path          | Purpose                               |
| ------ | ------------- | ------------------------------------- |
| GET    | `/health`     | Health check                          |
| POST   | `/ingest`     | Ingest a URL into the vector store    |
| POST   | `/ghost-note` | Semantic search over ingested content |
| GET    | `/`           | Endpoint index + link to `/docs`      |

Request/response shapes live in `api/models.py`. Note that `API_SCHEMA.md` at the repo root
currently documents `/ghost-note` as a GET with different field names — the code above is what
actually runs.

## PR & issue ingestion (Phase 8.5)

`POST /ingest {"url": "https://github.com/<owner>/<repo>", "source_type": "pr"}` indexes the
*why* instead of just the code: closed-and-merged PRs from the last `PR_LOOKBACK_MONTHS` months
(default 6), each PR's title/body, `/pulls/{n}/comments` (review comments) and
`/issues/{n}/comments` (discussion). All PRs is too much for a rate-limited walk on an active
repo, so the lookback is a deliberate, env-overridable knob rather than a hardcoded constant —
see `api/pr_ingest.py::list_merged_prs`.

Chunks land in the same Chroma collection as code, through the same `api/chunking.py`, keyed to a
stable synthetic path `pull/{n}` instead of a file path. Each chunk carries
`metadata.source_type == "pr"` plus `pr_number` / `pr_title` / `pr_url`, so a Ghost Note can cite
the thread it came from. API JSON comments are the primary indexable text; Crawl4AI (kept around
from Phase 2 specifically for JS-rendered content) is available as an opt-in second pass —
`pr_ingest.build_pr_document(..., enrich_with_crawl4ai=True)` — for PR threads where the rendered
page has substance the API comments miss, off by default so ingestion never depends on a working
headless browser.

`eval/queries_pr_tribal.json` seeds a few tribal-knowledge queries ("why was X changed", "known
issues with Y") against a real smoke-ingested repo — see its `_comment` for how it was seeded.
