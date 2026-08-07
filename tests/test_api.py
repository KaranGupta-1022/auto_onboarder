from fastapi.testclient import TestClient

from api.app import app
from api import pipeline

client = TestClient(app)


def test_health_reports_ok_and_touches_chroma():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["chroma_connected"] is True
    assert isinstance(body["chunk_count"], int)


# Must run before any test in this file ingests data - it asserts on the
# temp collection while it's still empty. Files/tests execute in pytest's
# default (alphabetical) order, and no ingest happens earlier than this.
def test_ghost_note_search_against_empty_collection_returns_no_results():
    response = client.post("/ghost-note", json={"query": "anything at all"})

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_ingest_then_search_round_trip(monkeypatch):
    doc_text = "def hello_world():\n    return 'hello from the ghostkube test fixture'\n"

    class _FakeResponse:
        text = doc_text

        def raise_for_status(self):
            pass

    monkeypatch.setattr(pipeline.requests, "get", lambda *a, **kw: _FakeResponse())

    ingest_response = client.post("/ingest", json={"url": "https://example.com/doc.py"})
    assert ingest_response.status_code == 200
    ingest_body = ingest_response.json()
    assert ingest_body["status"] == "success"
    assert ingest_body["chunks_ingested"] >= 1

    search_response = client.post("/ghost-note", json={"query": "hello world function"})
    assert search_response.status_code == 200
    results = search_response.json()["results"]
    assert len(results) >= 1
    assert results[0]["metadata"]["path"] == "doc.py"


def test_ingest_malformed_url_returns_400():
    response = client.post("/ingest", json={"url": "not-a-url"})

    assert response.status_code == 400
    assert "error" in response.json()
