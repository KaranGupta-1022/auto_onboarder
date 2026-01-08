# GhostKube Brain API - Project Documentation

## How to deploy

run: python -m uvicorn api.app:app --reload --host 0.0.0.0 --port 8000 

## Overview

**GhostKube Brain API** is a RAG (Retrieval-Augmented Generation) powered Kubernetes contextual onboarding system. It allows users to ingest documentation and GitHub repositories, then intelligently search for relevant contextual information using vector embeddings and cross-encoder reranking.

**Current Status**: Phase 2 Completion (Build the API)

---

## Creating the kind cluster

kind create cluster --name ghostkube --config kind-config.yaml
Confirm context and nodes
kubectl config current-context
kubectl cluster-info --context kind-ghostkube
kubectl get nodes
kubectl get pods -A
Apply the sample app (sample.yaml)
kubectl apply -f sample.yaml
Verify the pod is created and labeled
kubectl get pods -l ghostkube.io/service=auth-service -A
kubectl describe pod $(kubectl get pods -l ghostkube.io/service=auth-service -o jsonpath='{.items[0].metadata.name}')
5 . Check environment variables inside the pod (most containers use sh)
$POD = kubectl get pods -l ghostkube.io/service=auth-service -o jsonpath='{.items[0].metadata.name}'
kubectl exec -it $POD -- sh -c "printenv | grep GHOST_NOTE_ID || echo 'GHOST_NOTE_ID not set'"
(Optional) If you built any local images and need to load into kind (Won't work b/c we have no webhook)
docker build -t my-webhook:dev ./path/to/webhook
kind load docker-image my-webhook:dev --name ghostkube
When finished, delete the cluster
kind delete cluster --name ghostkube

## Completed Work - Phase 1 & Phase 2

### ✅ Phase 1: Planning & Setup
- **Architecture Decision**: Synchronous API (MVP phase)
- **API Contracts Defined**: POST /ingest and POST /ghost-note endpoints documented
- **Environment Variables**: Complete list created (see config.py)
- **Project Structure**: Fully scaffolded with all required directories and files

### ✅ Phase 2: Build the API

#### 1. **Requirements & Dependencies** ✅
File: `requirements.txt`

Core dependencies installed:
- **fastapi** - Modern async web framework
- **uvicorn** - ASGI server for FastAPI
- **chromadb** - Vector database for embeddings
- **sentence-transformers** - Bi-encoder for semantic embeddings
- **cross-encoder** - Cross-encoder for result reranking (production-grade search)
- **crawl4ai** - Web scraping library for URL ingestion
- **pydantic** - Data validation using Python type annotations
- **python-dotenv** - Environment variable management
- **requests** - HTTP library for URL fetching

#### 2. **Configuration Management** ✅
File: `api/config.py`

Implemented centralized configuration with environment variable support:
```python
CHROMA_PATH = "./chroma_db"           # Vector database location
EMBED_MODEL_NAME = "all-MiniLM-L12-v2" # Lightweight embedding model
CHROMA_COLLECTION_NAME = "repo_docs"   # Database collection name
LOG_LEVEL = "INFO"                     # Logging verbosity
API_PORT = 8000                        # API port
```

All values are configurable via `.env` file with sensible defaults.

#### 3. **Data Models (Pydantic Schemas)** ✅
File: `api/models.py`

**Request/Response Models Defined:**

- **IngestRequest**: Accepts URL, source type (repo/PR/slack), and optional metadata
- **IngestResponse**: Returns ingestion status, chunk count, character count, and success/error message
- **GhostNoteRequest**: Accepts search query and number of results (top_k)
- **GhostNoteResult**: Individual search result with text, relevance score, and metadata
- **GhostNoteResponse**: Aggregates query and list of results
- **ErrorResponse**: Standardized error response format

All models include proper type hints and optional fields for flexibility.

#### 4. **Ingestion Pipeline** ✅
File: `api/pipeline.py`

**Key Features:**

1. **URL Fetching**: HTTP GET requests with timeout handling
   - Fetches content from any URL (GitHub repos, documentation, etc.)
   - Handles errors gracefully with try-catch blocks

2. **Smart Chunking**: Intelligent text splitting with overlap
   - Configurable chunk size (default: 500 characters)
   - Overlap handling (50 chars) to preserve context across chunks
   - Prevents duplicate/empty chunks

3. **Embedding Generation**: Bi-encoder semantic embeddings
   - Uses `all-MiniLM-L12-v2` model (fast, efficient)
   - Contextual enrichment: prepends filename to chunks for better relevance
   - Numpy/list format conversion for ChromaDB compatibility

4. **Vector Storage**: Persistent ChromaDB integration
   - Upsert-based storage (prevents duplicates via unique IDs)
   - Automatic metadata flattening for ChromaDB compatibility
   - Deduplication using SHA256 hashing of URL + content

5. **Search Functionality**: Two-stage hybrid retrieval
   - **Stage 1 (Retrieval)**: Vector similarity search via ChromaDB (retrieves 10 candidates)
   - **Stage 2 (Reranking)**: Cross-encoder reranking for production-grade accuracy
     - Uses `cross-encoder/ms-marco-MiniLM-L-6-v2` model
     - Sigmoid normalization of scores (0-1 range)
     - Sorts results by semantic relevance

**Helper Functions:**
- `get_chunk_id()`: Generates unique IDs for deduplication
- `chunk_text()`: Intelligent text splitting with overlap
- `ingest_url()`: Full ingestion pipeline (async-compatible)
- `search_ghost_notes()`: Two-stage hybrid search with reranking

#### 5. **FastAPI Application** ✅
File: `api/app.py`

**Endpoints Implemented:**

1. **GET /health** - Health check endpoint
   - Returns service status and version
   - Used for uptime monitoring

2. **POST /ingest** - Document ingestion endpoint
   - Accepts: `{ url, source_type (optional), metadata (optional) }`
   - Returns: `{ status, chunks_ingested, total_characters, message }`
   - Full error handling with HTTPException (400/500)
   - Logging of all requests

3. **POST /ghost-note** - Semantic search endpoint
   - Accepts: `{ query, top_k (default: 5) }`
   - Returns: `{ query, results: [{ text, relevance_score, metadata }] }`
   - Handles empty database gracefully
   - Comprehensive error handling and logging

4. **GET /** - Root endpoint with API documentation
   - Returns list of available endpoints
   - Links to auto-generated Swagger docs at `/docs`

**Middleware & Features:**
- ✅ **CORS Middleware**: Enables cross-origin requests from all domains
- ✅ **Logging**: Structured logging at INFO level (configurable)
- ✅ **Error Handling**: Centralized exception handler for HTTP errors
- ✅ **Auto-documentation**: Swagger UI at `/docs` and ReDoc at `/redoc`
- ✅ **Async Support**: All endpoints ready for async scaling

**Startup Configuration:**
- Host: 0.0.0.0 (accessible externally)
- Port: Configurable (default: 8000)
- Auto-reload: Enabled for development
- Log level: Configurable via environment

---

## Project Architecture

```
auto_onboarder/
├── api/
│   ├── __init__.py
│   ├── app.py                 # FastAPI application & endpoints
│   ├── config.py              # Configuration management
│   ├── models.py              # Pydantic request/response schemas
│   ├── pipeline.py            # Ingestion & search logic
│   ├── requirements.txt        # API dependencies
│   ├── Dockerfile             # Docker containerization
│   ├── docker-compose.yml      # Multi-container orchestration
│   └── README.md              # This file
├── chroma_db/                 # Persistent vector database
│   └── chroma.sqlite3         # SQLite backend
├── requirements.txt           # Root project dependencies
├── README.md                  # Main project documentation
└── [other project files]
```

---

## Data Flow

### Ingestion Pipeline
```
User Request (POST /ingest)
    ↓
[app.py] Route Handler
    ↓
[pipeline.py] ingest_url()
    ├─ Fetch: HTTP GET to URL
    ├─ Chunk: Split text (500 chars, 50 overlap)
    ├─ Embed: Sentence-Transformers bi-encoder
    ├─ Deduplicate: SHA256 hash of URL + content
    └─ Store: ChromaDB upsert with metadata
    ↓
[models.py] IngestResponse
    ↓
API Response (JSON)
```

### Search Pipeline
```
User Request (POST /ghost-note)
    ↓
[app.py] Route Handler
    ↓
[pipeline.py] search_ghost_notes()
    ├─ Stage 1: Embed query + retrieve top 10 from ChromaDB
    ├─ Stage 2: Cross-encoder reranking (accuracy boost)
    └─ Sort: By relevance score (highest first)
    ↓
[models.py] GhostNoteResponse
    ↓
API Response (JSON)
```

---

## Key Technical Decisions

### 1. **Synchronous API (MVP)**
- Simpler to implement and debug
- Suitable for small-to-medium workloads
- Future: Add async with Redis + RQ if ingestion gets too slow

### 2. **Hybrid Search (Bi-Encoder + Cross-Encoder)**
- **Bi-Encoder** (ChromaDB): Fast retrieval of top candidates
- **Cross-Encoder** (Reranking): Accurate semantic relevance scoring
- Trade-off: Speed vs. Accuracy (retrieves 10, returns top K)
- Production-grade: Better than pure vector similarity

### 3. **Lightweight Embedding Model**
- `all-MiniLM-L12-v2`: 33M parameters
- Fast inference (~10x faster than large models)
- Sufficient for Kubernetes documentation context

### 4. **Contextual Chunking**
- Prepend filename to each chunk before embedding
- Improves relevance for documentation searches
- Example: "FILE: kubernetes-auth.md\n[chunk content]"

### 5. **Deduplication via SHA256**
- Prevents duplicate chunks in database
- Upsert operation: update if exists, insert if new
- Handles repeated ingestions gracefully

### 6. **Metadata Flattening**
- ChromaDB requires flat key-value metadata
- Complex objects converted to JSON strings
- Preserved on retrieval for client use

---

## Configuration (.env File)

Create a `.env` file in the `api/` directory:

```env
# Vector Database
CHROMA_PATH=./chroma_db
CHROMA_COLLECTION_NAME=repo_docs

# Embedding Model
EMBED_MODEL_NAME=all-MiniLM-L12-v2

# API Configuration
API_PORT=8000
LOG_LEVEL=INFO
```

All values have sensible defaults and are optional.

---

## Running the API

### Local Development
```bash
cd api/
pip install -r requirements.txt
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Docker
```bash
docker-compose up -d
```

### Access API
- **REST Endpoints**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Example API Usage

### 1. Ingest a Document
```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://raw.githubusercontent.com/kubernetes/kubernetes/master/README.md",
    "source_type": "repo",
    "metadata": {"org": "kubernetes", "team": "core"}
  }'
```

**Response:**
```json
{
  "status": "success",
  "chunks_ingested": 24,
  "total_characters": 12000,
  "message": "Ingested 24 chunks from https://..."
}
```

### 2. Search for Ghost Notes
```bash
curl -X POST http://localhost:8000/ghost-note \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I authenticate to the API server?",
    "top_k": 3
  }'
```

**Response:**
```json
{
  "query": "How do I authenticate to the API server?",
  "results": [
    {
      "text": "FILE: kubernetes-auth.md\nAuthentication to the Kubernetes API server can be done via...",
      "relevance_score": 0.92,
      "metadata": {
        "source_url": "https://...",
        "chunk_number": 5,
        "total_chunks": 24
      }
    },
    ...
  ]
}
```

---

## Performance Optimizations Implemented

1. ✅ **Contextual Chunking**: Filename context improves search relevance
2. ✅ **Cross-Encoder Reranking**: Production-grade accuracy vs. pure embeddings
3. ✅ **Deduplication**: SHA256 IDs prevent database bloat from repeated ingestions
4. ✅ **Metadata Flattening**: Efficient ChromaDB storage and retrieval
5. ✅ **Staged Retrieval**: Retrieve 10 candidates, rerank to top K (faster than reranking all)
6. ✅ **Persistent Storage**: Chroma.sqlite3 for fast subsequent searches
7. ✅ **Error Handling**: Graceful degradation for empty database, network errors, etc.

---

## What's Next - Phase 3 (Future Work)

- [ ] Add test suite (unit & integration tests)
- [ ] Implement Crawl4AI for advanced web scraping
- [ ] Add GitHub API integration for PR/issue content
- [ ] Implement async processing with Redis + RQ for slow ingestions
- [ ] Add authentication & API key management
- [ ] Implement rate limiting
- [ ] Add request/response caching layer
- [ ] Deploy to Kubernetes cluster
- [ ] Add monitoring & observability (Prometheus, Grafana)
- [ ] Performance benchmarking & optimization

---

## Dependencies Overview

| Package | Purpose | Status |
|---------|---------|--------|
| fastapi | Web framework | ✅ Integrated |
| uvicorn | ASGI server | ✅ Integrated |
| chromadb | Vector database | ✅ Integrated |
| sentence-transformers | Embeddings | ✅ Integrated |
| cross-encoder | Reranking | ✅ Integrated |
| crawl4ai | Web scraping | ✅ Available (not yet used) |
| pydantic | Data validation | ✅ Integrated |
| python-dotenv | Env management | ✅ Integrated |
| requests | HTTP client | ✅ Integrated |

---

## API Status

- **Health**: `/health` ✅
- **Ingest**: `POST /ingest` ✅
- **Search**: `POST /ghost-note` ✅
- **Docs**: `/docs` (Swagger) ✅
- **Error Handling**: Implemented ✅
- **Logging**: Configured ✅
- **CORS**: Enabled ✅

---

## Notes

- **Embedding Model**: `all-MiniLM-L12-v2` is lightweight but sufficient for MVP. Consider upgrading to larger models (e.g., `sentence-transformers/all-mpnet-base-v2`) for higher accuracy if needed.
- **Reranker**: `cross-encoder/ms-marco-MiniLM-L-6-v2` is optimized for document ranking and provides production-grade relevance.
- **Database**: SQLite backend is suitable for development. Consider PostgreSQL with pgvector for production.
- **Async Ready**: All endpoints are async-compatible for future scaling.

---

## Files Summary

| File | Purpose | Status |
|------|---------|--------|
| `app.py` | FastAPI application & endpoints | ✅ Complete |
| `config.py` | Configuration management | ✅ Complete |
| `models.py` | Pydantic request/response schemas | ✅ Complete |
| `pipeline.py` | Ingestion & search logic | ✅ Complete |
| `requirements.txt` | Dependencies | ✅ Complete |
| `Dockerfile` | Docker image definition | ✅ Available |
| `docker-compose.yml` | Multi-container setup | ✅ Available |

---

**Last Updated**: December 30, 2025  
**Phase**: 2 (Build the API) - **COMPLETE** ✅
