# api/app.py
from fastapi import FastAPI, HTTPException
from .models import IngestRequest, GhostNoteRequest
from .pipeline import GhostPipeline

app = FastAPI(title="GhostKube API")
pipeline = GhostPipeline()

@app.post("/ingest")
async def ingest_repo(data: IngestRequest):
    try:
        result = pipeline.ingest(data.repo_url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ghost-note")
async def get_note(query: str):
    # This matches the logic from your search.py
    return pipeline.search(query)