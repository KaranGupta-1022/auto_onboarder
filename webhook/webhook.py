# webhook/webhook.py
import base64
import json
import logging 
import uuid
from typing import Dict, Any, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
logger = logging.getLogger("webhook")
logging.basicConfig(level=logging.INFO)

# Create JSONPatch operations: inject GHOST_NOTE_ID into each app container's
# env, then append the Shadow Sidecar container (PRD 4B)
def make_patch_for_pod(pod: Dict[str, Any]) -> List[Dict[str, Any]]:
    metadata = pod.get("metadata", {})
    labels = metadata.get("labels", {}) or {}
    service_label = labels.get("ghostkube.io/service")
    if not service_label:
        return []
    
    # "svc:" makes this an explicit join key against chunk metadata.service
    # rather than free text, so the Brain API can tell a resolved note ID
    # from an arbitrary string. The label stays the source of truth.
    ghost_value = f"svc:{service_label}"
    
    patches: List[Dict[str, Any]] = []
    containers = pod.get("spec", {}).get("containers", [])
    for i, container in enumerate(containers):
        env = container.get("env")
        if env is None:
            patches.append({
                "op": "add",
                "path": f"/spec/containers/{i}/env",
                "value": [{"name": "GHOST_NOTE_ID", "value": ghost_value}]
            })
        else:
            patches.append({
                "op": "add",
                "path": f"/spec/containers/{i}/env/-",
                "value": {"name": "GHOST_NOTE_ID", "value": ghost_value}
            })

    patches.extend(make_shadow_sidecar_patch(containers, ghost_value))
    return patches


SHADOW_SIDECAR_NAME = "ghostkube-shadow"


def make_shadow_sidecar_patch(containers: List[Dict[str, Any]], ghost_value: str) -> List[Dict[str, Any]]:
    """Append the Shadow Sidecar (PRD 4B), unless one is already present.

    Demo-minimal: reports coarse pod state via stdout JSON on a 30s loop, with
    an optional POST to the Brain API. See sidecar/sidecar_main.py - this is
    deliberately not a full observability agent.
    """
    if any(c.get("name") == SHADOW_SIDECAR_NAME for c in containers):
        return []

    sidecar = {
        "name": SHADOW_SIDECAR_NAME,
        "image": "ghostkube/sidecar:dev",
        "imagePullPolicy": "IfNotPresent",
        "env": [
            {"name": "GHOST_NOTE_ID", "value": ghost_value},
            {"name": "POD_NAME", "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}}},
            {"name": "POD_NAMESPACE", "valueFrom": {"fieldRef": {"fieldPath": "metadata.namespace"}}},
        ],
        "resources": {
            "requests": {"cpu": "10m", "memory": "32Mi"},
            "limits": {"cpu": "50m", "memory": "64Mi"},
        },
    }
    return [{
        "op": "add",
        "path": "/spec/containers/-",
        "value": sidecar,
    }]

@app.post("/mutate")
# Handle AdmissionReview v1 requests. Return AdmissionReview v1 response.
async def mutate(request: Request):
    body = await request.json()
    logger.info(f"Admission request received: uid={body.get('request', {}).get('uid')}")
    req = body.get("request", {})
    uid = req.get("uid")

    # default response: allow
    response = {
        "uid": uid,
        "allowed": True,
    }

    # only process pod CREATE requests
    kind = req.get("kind", {}).get("kind")
    operation = req.get("operation")
    if kind != "Pod" or operation != "CREATE":
        # return admission response allow
        admission_review = {"apiVersion": "admission.k8s.io/v1", "kind": "AdmissionReview", "response": response}
        return JSONResponse(content=admission_review)

    obj = req.get("object", {})
    patches = make_patch_for_pod(obj)
    if patches:
        patch_str = json.dumps(patches)
        patch_b64 = base64.b64encode(patch_str.encode()).decode()
        response.update({
            "patch": patch_b64,
            "patchType": "JSONPatch",
        })

    admission_review = {"apiVersion": "admission.k8s.io/v1", "kind": "AdmissionReview", "response": response}
    logger.info(f"Responding admission uid={uid} patches={len(patches)}")
    return JSONResponse(content=admission_review)