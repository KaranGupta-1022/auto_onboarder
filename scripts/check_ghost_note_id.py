"""scripts/check_ghost_note_id.py

Tiny unit-style check for the Phase 8 v2 GHOST_NOTE_ID format: "svc:<service-label>".
Run with: python scripts/check_ghost_note_id.py

Only exercises pure logic (no cluster, no Chroma, no embedding model), so it's
fast enough to run on every change to webhook.py or the service-suffix parsing
in api/pipeline.py's search_ghost_notes().
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webhook"))
from webhook import make_patch_for_pod  # noqa: E402


def service_from_ghost_note_id(ghost_note_id):
    """Mirrors the extraction in api/pipeline.py::search_ghost_notes."""
    if ghost_note_id and ghost_note_id.startswith("svc:"):
        return ghost_note_id[len("svc:"):] or None
    return None


def check(label, expected):
    got = label == expected
    print(f"{'PASS' if got else 'FAIL'}: {label!r} == {expected!r}")
    return got


def main():
    ok = True

    # webhook.py: labeled pod gets a "svc:"-prefixed GHOST_NOTE_ID
    pod = {
        "metadata": {"labels": {"ghostkube.io/service": "auth-service"}},
        "spec": {"containers": [{"name": "c"}]},
    }
    patches = make_patch_for_pod(pod)
    ok &= check(patches[0]["value"][0]["value"], "svc:auth-service")

    # webhook.py: unlabeled pod is untouched
    ok &= check(make_patch_for_pod({"spec": {"containers": [{"name": "c"}]}}) == [], True)

    # api/pipeline.py contract: "svc:" prefix is stripped to the service name
    ok &= check(service_from_ghost_note_id("svc:auth-service"), "auth-service")
    ok &= check(service_from_ghost_note_id("auth-service"), None)
    ok &= check(service_from_ghost_note_id(None), None)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
