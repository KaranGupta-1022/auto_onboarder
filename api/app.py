# api/app.py
import logging
from fastapi import FastAPI, HTTPException, Query 
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio

from .config import config
from .models import (
    IngestRequest, IngestResponse, GhostNoteRequest, GhostNoteResponse,
    FeedbackRequest, FeedbackResponse, ErrorResponse,
)
from .pipeline import (
    ingest_url, search_ghost_notes, health_snapshot,
    record_feedback, feedback_summary,
)
from starlette.responses import JSONResponse


# Setup logging
logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="GhostKube Brain API",
    description="RAG-powered Kubernetes contextual onboarding",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health Check Endpoint
@app.get("/health")
def health_check():
    """Health check that can actually fail.

    Touches ChromaDB rather than returning a hardcoded 'ok' - Phase 9's readiness
    probe is worthless if this cannot report a broken vector store.
    """
    snapshot = health_snapshot()
    return {
        "service": "GhostKube Brain API",
        "version": "1.0.0",
        **snapshot,
    }
    
# Ingest Endpoint
# Ingest a GitHub/documentation URL into the vector database.
    # **url**: URL to scrape (e.g., https://github.com/owner/repo)
    # **source_type**: Type of source ("repo", "pr", "slack", etc.)
    # **metadata**: Optional metadata to attach to ingested chunks
#
@app.post("/ingest", response_model=IngestResponse)
async def ingest_endpoint(request: IngestRequest):
    logger.info(f"Received ingest request for URL: {request.url}")
    
    try:
        result = await ingest_url(
            url=request.url,
            source_type=request.source_type,
            metadata=request.metadata
        )
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        
        return IngestResponse(**result)
    except Exception as e:
        logger.error(f"Error in ingest endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Ghost Note Search Endpoint
# Search for relevant ghost notes.    
    # **q**: Search query (required)
    # **top_k**: Number of top results to return (default: 5)


@app.post("/ghost-note", response_model=GhostNoteResponse)
def ghost_note_endpoint(request: GhostNoteRequest):
    """
    Search for relevant ghost notes.

    - **query**: Search query (e.g., 'Auth service error')
    - **top_results**: Number of results to return (default: 5)

    Deliberately a plain `def`, not `async def`: search_ghost_notes() is
    synchronous and CPU-bound (embedding inference), so as a coroutine it would
    block the event loop for the duration of every search and destroy the
    sub-800ms latency target under any concurrency. Starlette runs plain `def`
    handlers in a threadpool.
    """
    logger.info(f"Received search query: {request.query}")
    
    try:
        result = search_ghost_notes(query=request.query, top_results=request.top_results)
        return GhostNoteResponse(**result)
    
    except Exception as e:
        logger.error(f"Error in ghost-note endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Feedback Endpoints
# Plain `def` for the same reason as ghost_note_endpoint above: these do
# blocking file I/O, so Starlette should pool them rather than run them on the
# event loop.
@app.post("/feedback", response_model=FeedbackResponse)
def feedback_endpoint(request: FeedbackRequest):
    """Record a 👍/👎 on a Ghost Note.

    - **chunk_id**: the `chunk_id` from the /ghost-note result being rated
    - **query**: the query that surfaced it, so relevance can be judged in context
    - **rating**: "up" or "down"
    """
    logger.info(f"Feedback {request.rating} for chunk {request.chunk_id[:12]}")

    try:
        result = record_feedback(
            chunk_id=request.chunk_id,
            query=request.query,
            rating=request.rating,
        )
        return FeedbackResponse(**result)
    except Exception as e:
        logger.error(f"Error in feedback endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/feedback/summary", response_model=FeedbackResponse)
def feedback_summary_endpoint():
    """Aggregate 👍/👎 counts - the PRD's relevance metric."""
    try:
        return FeedbackResponse(recorded=True, **feedback_summary())
    except Exception as e:
        logger.error(f"Error in feedback summary endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Root Endpoint
@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "message": "Welcome to GhostKube Brain API",
        "endpoints": {
            "health": "GET /health",
            "ingest": "POST /ingest",
            "search": "POST /ghost-note",
            "feedback": "POST /feedback",
            "feedback_summary": "GET /feedback/summary"
        },
        "docs": "/docs"
    }
    
# Error Handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )
    
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=config.API_PORT,
        reload=True,
        log_level=config.LOG_LEVEL.lower()
    )