import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from webhook.webhook import app, SHADOW_SIDECAR_NAME

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


def _load_admission_review(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_mutate_labeled_pod_create_returns_env_and_sidecar_patch():
    admission_review = _load_admission_review("admission_review_pod_create.json")
    request_uid = admission_review["request"]["uid"]

    response = client.post("/mutate", json=admission_review)

    assert response.status_code == 200
    body = response.json()
    assert body["response"]["uid"] == request_uid
    assert body["response"]["allowed"] is True
    assert body["response"]["patchType"] == "JSONPatch"

    patch = json.loads(base64.b64decode(body["response"]["patch"]))

    env_ops = [p for p in patch if p["path"] == "/spec/containers/0/env"]
    assert env_ops == [{
        "op": "add",
        "path": "/spec/containers/0/env",
        "value": [{"name": "GHOST_NOTE_ID", "value": "svc:auth-service"}],
    }]

    sidecar_ops = [p for p in patch if p["path"] == "/spec/containers/-"]
    assert len(sidecar_ops) == 1
    assert sidecar_ops[0]["value"]["name"] == SHADOW_SIDECAR_NAME


def test_mutate_non_pod_operation_returns_no_patch():
    admission_review = _load_admission_review("admission_review_pod_create.json")
    admission_review["request"]["operation"] = "UPDATE"

    response = client.post("/mutate", json=admission_review)

    body = response.json()
    assert body["response"]["allowed"] is True
    assert "patch" not in body["response"]
