# sidecar/sidecar_main.py
"""Shadow Sidecar (PRD 4B) - demo-minimal pod-state reporter.

Injected by the mutating webhook alongside a pod's app container(s) whenever
the pod opted in via the ghostkube.io/service label. Deliberately not a full
observability agent: it emits one coarse JSON heartbeat every 30s and nothing
else - no log scraping, no metrics, no secrets access.

Env:
  GHOST_NOTE_ID   - injected by the webhook alongside the app container's copy
  POD_NAME        - via fieldRef: metadata.name
  POD_NAMESPACE   - via fieldRef: metadata.namespace
  LOG_ONLY        - default "1": stdout JSON lines only
  BRAIN_URL       - optional; if set (and LOG_ONLY is falsy), also POST each
                    tick to BRAIN_URL/pod-state, best-effort
"""
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shadow-sidecar")

GHOST_NOTE_ID = os.getenv("GHOST_NOTE_ID", "")
POD_NAME = os.getenv("POD_NAME", "")
POD_NAMESPACE = os.getenv("POD_NAMESPACE", "")
BRAIN_URL = os.getenv("BRAIN_URL", "").rstrip("/")
LOG_ONLY = os.getenv("LOG_ONLY", "1").strip().lower() in ("1", "true", "yes", "on")
INTERVAL_SECONDS = 30


def build_tick() -> dict:
    return {
        "ghost_note_id": GHOST_NOTE_ID,
        "pod": POD_NAME,
        "namespace": POD_NAMESPACE,
        "status": "running",
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def report(tick: dict) -> None:
    print(json.dumps(tick), flush=True)

    if LOG_ONLY or not BRAIN_URL:
        return

    # Best-effort only, same failure philosophy as the webhook's
    # failurePolicy: Ignore - a Brain API outage must never take a watched
    # pod's sidecar down.
    req = urllib.request.Request(
        f"{BRAIN_URL}/pod-state",
        data=json.dumps(tick).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except (urllib.error.URLError, OSError) as e:
        logger.warning("Failed to POST pod-state to %s: %s", BRAIN_URL, e)


def main() -> None:
    logger.info(
        "Shadow Sidecar starting: pod=%s namespace=%s ghost_note_id=%s log_only=%s brain_url=%s",
        POD_NAME, POD_NAMESPACE, GHOST_NOTE_ID, LOG_ONLY, BRAIN_URL or "(none)",
    )
    while True:
        report(build_tick())
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
