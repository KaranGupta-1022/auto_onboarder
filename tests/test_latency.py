import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api import pipeline

client = TestClient(app)

CONCURRENCY = 10
LATENCY_BUDGET_S = 0.8
IS_CI = os.getenv("CI", "").lower() in ("1", "true", "yes")


# Latency budgets are hardware-dependent - a shared CI runner under noisy-
# neighbor load isn't a fair test of this. Correctness tests still run in CI;
# only this timing assertion is local-only.
@pytest.mark.skipif(IS_CI, reason="latency budget is hardware-dependent; run locally, not on shared CI runners")
def test_ghost_note_latency_under_budget_at_concurrency(monkeypatch):
    doc_text = "def handler():\n    return 'seed content for the latency test corpus'\n"

    class _FakeResponse:
        text = doc_text

        def raise_for_status(self):
            pass

    monkeypatch.setattr(pipeline.requests, "get", lambda *a, **kw: _FakeResponse())
    ingest_response = client.post("/ingest", json={"url": "https://example.com/latency_seed.py"})
    assert ingest_response.status_code == 200

    def _timed_search(i):
        start = time.perf_counter()
        response = client.post("/ghost-note", json={"query": f"seed content number {i}"})
        elapsed = time.perf_counter() - start
        assert response.status_code == 200
        return elapsed

    # One untimed warm-up call: the first inference after model load pays a
    # one-time cost that would otherwise inflate every latency number below.
    client.post("/ghost-note", json={"query": "warm up"})

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        durations = sorted(pool.map(_timed_search, range(CONCURRENCY)))

    p95 = durations[max(0, int(len(durations) * 0.95) - 1)]
    assert p95 < LATENCY_BUDGET_S, f"p95 latency {p95:.3f}s exceeds {LATENCY_BUDGET_S}s budget: {durations}"
