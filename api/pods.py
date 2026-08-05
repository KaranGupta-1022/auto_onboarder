# api/pods.py
import logging

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

logger = logging.getLogger(__name__)

GHOST_SERVICE_LABEL = "ghostkube.io/service"


def _load_k8s_config() -> bool:
    """Try in-cluster config first (running as a pod under Phase 9's
    ghostkube-api Deployment), fall back to the local kubeconfig (kind on a
    laptop, Phase 7). Never raises - returns False so a missing/unreachable
    cluster degrades to an empty pod list instead of crashing the API.
    """
    try:
        config.load_incluster_config()
        return True
    except config.ConfigException:
        pass

    try:
        config.load_kube_config()
        return True
    except config.ConfigException as e:
        logger.warning(
            "Could not load a Kubernetes config (in-cluster or kubeconfig): %s", e
        )
        return False


def list_watched_pods() -> list[dict]:
    """List every pod carrying the ghostkube.io/service label, cluster-wide.

    Best-effort: any failure (no kubeconfig, cluster unreachable, RBAC denial)
    logs and returns an empty list rather than raising, so a laptop without a
    running kind cluster - or a Deployment missing the Role Phase 9's README
    calls out - doesn't take down the whole Brain API over a page that's
    allowed to just show "no pods."
    """
    if not _load_k8s_config():
        return []

    try:
        v1 = client.CoreV1Api()
        pods = v1.list_pod_for_all_namespaces(label_selector=GHOST_SERVICE_LABEL)
    except ApiException as e:
        logger.warning("Kubernetes API call failed while listing pods: %s", e)
        return []
    except Exception as e:
        logger.warning("Unexpected error listing pods: %s", e)
        return []

    results = []
    for pod in pods.items:
        service_label = (pod.metadata.labels or {}).get(GHOST_SERVICE_LABEL)

        # The label alone doesn't prove the mutating webhook actually ran -
        # this pod could predate the webhook, or the webhook could be down.
        # The real signal is whether GHOST_NOTE_ID actually landed in a
        # container's env (webhook/webhook.py::make_patch_for_pod).
        ghost_note_id = None
        for container in pod.spec.containers or []:
            for env_var in container.env or []:
                if env_var.name == "GHOST_NOTE_ID":
                    ghost_note_id = env_var.value
                    break
            if ghost_note_id:
                break

        results.append({
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "service_label": service_label,
            "ghost_note_id": ghost_note_id,
            "injected": ghost_note_id is not None,
        })

    return results
