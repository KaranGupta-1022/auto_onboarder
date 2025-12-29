# api/models.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# Ingest Endpoint Request
class IngestRequest(BaseModel):
    url: str
    source_type: Optional[str] = "repo" 
    metadata: Optional[Dict[str, Any]] = None

class IngestResponse(BaseModel):
    status: str
    chunks_ingested: int
    total_characters: int
    message: str
    
# Ghost Note Endpoint

class GhostNoteRequest(BaseModel):
    query: str
    top_results: int = 5
    
class GhostNoteResult(BaseModel):
    text: str
    relevance_score: float
    metadata: Dict[str, Any]
    
class GhostNoteResponse(BaseModel):
    query: str
    results: List[GhostNoteResult]
    
# Error Response 
    
class ErrorResponse(BaseModel):
    error: str
    status_code: int