# webhook/webhook.py
import base64
import json
import logging 
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app.post("/mutate")
async def mutate(request: Request):
    body = await request.json()
    req = body.get("request", {})
    uid = req.get("uid", "")
    pod = req.get("object", {}) or {}
    metadata = pod.get("metadata", {})
    labels = metadata.get("labels", {}) or {}
    
    # Only mutate if label exists
    service_label = labels.get("ghostkube.io/service")
    if not service_label:
        # Allow without mutation
        rep = {
            'apiVersion': 'admission.k8s.io/v1',
            'kind': 'AdmissionReview',
            'response': {
                'uid': uid,
                'allowed': True
            }
        }
        return JSONResponse(content=rep)
    
    # Generate a note id (could be deterministic based on label)
    note_id = f"{service_label}:{str(uuid.uuid4())[:]}"
    
    # Build JSONPatch operation to add env var each container
    patch_ops = []
    spec = pod.get("spec", {})
    containers = spec.get("containers", [])
    for i, container in enumerate(containers):
        # If container has env, append; otherwise add env array
        if "env" in container:
            path = f"/spec/containers/{i}/env/-"
            value = {"name": "GHOST_NOTE_ID", "value": note_id}
            patch_ops.append({"op": "add", "path": path, "value": value})
        else:
            path = f"/spec/containers/{i}/env"
            value = [{"name": "GHOST_NOTE_ID", "value": note_id}]
            patch_ops.append({"op": "add", "path": path, "value": value})
            
    patch_str = json.dumps(patch_ops)
    patch_b64 = base64.b64encode(patch_str.encode()).decode()
    
    admission_response = {
        "uid": uid,
        "allowed": True,
        "patch": patch_b64,
        "patchType": "JSONPatch"
    }
    
    resp = {
        'apiVersion': 'admission.k8s.io/v1',
        'kind': 'AdmissionReview',
        'response': admission_response
    }
    
    logger.info(f"Mutating pod {metadata.get('name')} labels={service_label} -> GHOST_NOTE_ID={note_id}")
    return JSONResponse(content=resp)