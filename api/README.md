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
