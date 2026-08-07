# api/models.py
from pydantic import BaseModel
from typing import List, Literal, Optional, Dict, Any

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
    # From the webhook-injected GHOST_NOTE_ID env var, e.g. "svc:auth-service".
    # Only the "svc:" form is understood today; anything else is ignored.
    ghost_note_id: Optional[str] = None
    
class GhostNoteResult(BaseModel):
    # sha256 of the full chunk text - the same ID the chunk is stored under.
    # Stable across re-ingests, so feedback survives reindexing.
    chunk_id: str
    text: str
    relevance_score: float
    metadata: Dict[str, Any]

class GhostNoteResponse(BaseModel):
    query: str
    results: List[GhostNoteResult]
    # Phase 13: synthesized summary for the TOP result only, not per-result -
    # one Groq call per search instead of N. None/False when synthesis is
    # disabled, there were no results, or the Groq call failed.
    summary: Optional[str] = None
    summary_path: Optional[str] = None
    synthesized: bool = False


# Chunk Lookup Endpoint (Note Detail direct-link support)

class ChunkResponse(BaseModel):
    # No relevance_score here - unlike GhostNoteResult, a direct by-ID lookup
    # has no query to score relevance against.
    chunk_id: str
    text: str
    metadata: Dict[str, Any]

# Feedback Endpoint

class FeedbackRequest(BaseModel):
    chunk_id: str
    query: str
    rating: Literal["up", "down"]

class FeedbackResponse(BaseModel):
    recorded: bool
    total_up: int
    total_down: int

# Pod List Endpoint (Cluster page, Phase 12)

class PodInfo(BaseModel):
    name: str
    namespace: str
    service_label: str
    # None when the webhook hasn't (yet, or ever) patched this pod's
    # GHOST_NOTE_ID env var in - the label alone doesn't prove injection.
    ghost_note_id: Optional[str] = None
    injected: bool

class PodListResponse(BaseModel):
    pods: List[PodInfo]

# Pod State Endpoint (Shadow Sidecar, PRD 4B)

class PodStateRequest(BaseModel):
    ghost_note_id: Optional[str] = None
    pod: str
    namespace: str
    status: str
    ts: str

class PodStateResponse(BaseModel):
    recorded: bool

# Error Response
    
class ErrorResponse(BaseModel):
    error: str
    status_code: int

# Intent Classifier Endpoint (Phase 13.3)
class IntentRequest(BaseModel):
    command: str

class IntentResponse(BaseModel):
    label: Literal["high_risk", "low_risk", "no_note"]
    source: Literal["rules", "model"]

