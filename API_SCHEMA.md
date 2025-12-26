# GhostKube API Schema

## POST /ingest
Endpoint to ingest a GitHub repository or PR into the vector database.

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
- `url` (string, required): GitHub repository or PR URL to scrape
- `source_type` (string, optional): Type of source - "repo" or "pr" (default: "repo")
- `metadata` (object, optional): Additional metadata to store with chunks

### Response (Success - 200)
```json
{
  "status": "success",
  "chunks_ingested": 42,
  "total_characters": 15680,
  "message": "Successfully ingested repository"
}
```

### Response (Error - 400)
```json
{
  "error": "Invalid URL provided",
  "status_code": 400
}
```

---

## GET /ghost-note
Endpoint to search for relevant "ghost notes" from ingested content.

### Query Parameters
- `q` (required, string): Search term or service name to find relevant notes
- `top_k` (optional, integer, default: 3): Number of results to return

### Example Request
```
GET /ghost-note?q=auth-service&top_k=5
```

### Response (Success - 200)
```json
{
  "query": "auth-service",
  "results": [
    {
      "text": "The auth-api pod crashes when JWT token expires...",
      "relevance_score": 0.87,
      "metadata": {
        "source_url": "https://github.com/owner/repo/pull/123",
        "chunk_number": 5,
        "source_type": "pr"
      }
    },
    {
      "text": "Known issue with token refresh logic in auth service...",
      "relevance_score": 0.82,
      "metadata": {
        "source_url": "https://github.com/owner/repo",
        "chunk_number": 12,
        "source_type": "repo"
      }
    }
  ]
}
```

**Response fields:**
- `query`: The search term that was queried
- `results`: Array of relevant chunks (max `top_k` results)
  - `text`: The actual chunk content
  - `relevance_score`: 0.0-1.0 score indicating how relevant this result is
  - `metadata`: Info about the source (URL, chunk ID, source type)

### Response (Error - 400)
```json
{
  "error": "Missing required query parameter: q",
  "status_code": 400
}
```

---

## GET /health
Health check endpoint to verify API and database connectivity.

### Response (Success - 200)
```json
{
  "status": "ok",
  "chroma_connected": true
}
```

**Response fields:**
- `status`: "ok" if healthy, "error" otherwise
- `chroma_connected`: true if ChromaDB is accessible, false otherwise