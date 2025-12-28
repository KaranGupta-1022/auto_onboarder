# api/models.py
from pydantic import BaseModel
from typing import List, Optional

class IngestRequest(BaseModel):
    repo_url: str

class GhostNoteRequest(BaseModel):
    query: str
    service_name: Optional[str] = None

class GhostNoteResponse(BaseModel):
    path: str
    content: str
    score: float