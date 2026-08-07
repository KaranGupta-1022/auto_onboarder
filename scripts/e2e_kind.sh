#!/usr/bin/env bash
# scripts/e2e_kind.sh
#
# Full end-to-end webhook verification against a real kind cluster:
#   create/reuse cluster -> build+load webhook image -> apply webhook + TLS
#   -> apply test-workload.yaml -> assert GHOST_NOTE_ID landed on the labeled
#   pod and NOT on the unlabeled one.
#
# Requires on PATH: docker, kind, kubectl, openssl. Idempotent - safe to
# re-run (kubectl apply, cluster-exists check, workload delete+reapply).
#
# Usage:
#   ./scripts/e2e_kind.sh                        # webhook-only e2e (default)
#   RUN_KUBECTL_GHOST=1 ./scripts/e2e_kind.sh     # also deploys the Brain API,
#                                                  # ingests a doc, and checks
#                                                  # `kubectl ghost` returns a note
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

CLUSTER_NAME="ghostkube"

echo "==> Cluster"
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "kind cluster '$CLUSTER_NAME' already exists, reusing it."
else
  kind create cluster --name "$CLUSTER_NAME" --config kind-config.yaml
fi
kubectl config use-context "kind-$CLUSTER_NAME" >/dev/null

echo "==> Certs"
./scripts/gen-certs.sh

echo "==> Webhook image"
docker build -t ghostkube/webhook:dev ./webhook
kind load docker-image ghostkube/webhook:dev --name "$CLUSTER_NAME"

echo "==> Webhook deployment + TLS secret"
kubectl apply -f k8s/webhook-deployment.yaml
kubectl create secret tls webhook-server-tls \
  --cert=server.crt --key=server.key -n ghostkube \
  --dry-run=client -o yaml | kubectl apply -f -
# The running Pod (if any) loaded its cert at process startup and won't pick
# up a re-generated one from the Secret on its own - restart so it always
# serves whatever cert was just written, even on a reused cluster.
kubectl -n ghostkube rollout restart deployment/ghostkube-webhook

echo "==> MutatingWebhookConfiguration"
CA_BUNDLE=$(base64 -w0 ca.crt)
sed "s|PLACEHOLDER_CA_BUNDLE_BASE64|${CA_BUNDLE}|" k8s/mutatingwebhook.yaml | kubectl apply -f -

kubectl -n ghostkube rollout status deployment/ghostkube-webhook --timeout=120s

echo "==> Test workload"
kubectl delete -f k8s/test-workload.yaml --ignore-not-found
kubectl apply -f k8s/test-workload.yaml
kubectl rollout status deployment/hello-auth --timeout=120s
kubectl wait --for=condition=Ready pod/hello-nolabel --timeout=120s

echo "==> Asserting GHOST_NOTE_ID injection"
AUTH_POD=$(kubectl get pods -l app=hello-auth -o jsonpath='{.items[0].metadata.name}')
GOT=$(kubectl exec "$AUTH_POD" -- printenv GHOST_NOTE_ID)
if [ "$GOT" != "svc:auth-service" ]; then
  echo "FAIL: hello-auth GHOST_NOTE_ID='$GOT', expected 'svc:auth-service'"
  exit 1
fi
echo "PASS: hello-auth GHOST_NOTE_ID=$GOT"

if kubectl exec hello-nolabel -- printenv GHOST_NOTE_ID >/dev/null 2>&1; then
  echo "FAIL: hello-nolabel has GHOST_NOTE_ID set, expected unset"
  exit 1
fi
echo "PASS: hello-nolabel has no GHOST_NOTE_ID"

if [ "${RUN_KUBECTL_GHOST:-0}" != "1" ]; then
  echo "==> Skipping kubectl-ghost check (set RUN_KUBECTL_GHOST=1 to include it)"
  echo "E2E webhook checks passed."
  exit 0
fi

echo "==> Brain API + Chroma (RUN_KUBECTL_GHOST=1)"
docker build -f api/Dockerfile -t ghostkube/api:dev .
kind load docker-image ghostkube/api:dev --name "$CLUSTER_NAME"
kubectl apply -f k8s/chroma-statefulset.yaml
kubectl apply -f k8s/api-config.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl -n ghostkube rollout status statefulset/ghostkube-chroma --timeout=180s
kubectl -n ghostkube rollout status deployment/ghostkube-api --timeout=180s

echo "==> Port-forwarding the Brain API and ingesting a doc"
kubectl -n ghostkube port-forward svc/ghostkube-api 8000:8000 >/tmp/ghostkube-portforward.log 2>&1 &
PF_PID=$!
trap 'kill $PF_PID 2>/dev/null || true' EXIT
sleep 3

curl -sf -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"url": "https://raw.githubusercontent.com/octocat/Hello-World/master/README", "metadata": {"service": "auth-service"}}' \
  > /dev/null

echo "==> kubectl ghost"
NOTE=$("$ROOT_DIR/kubectl-ghost.exe" "$AUTH_POD" 2>&1) || NOTE="$(kubectl-ghost "$AUTH_POD" 2>&1)"
echo "$NOTE"
if [ -z "$NOTE" ]; then
  echo "FAIL: kubectl ghost returned no output"
  exit 1
fi
echo "PASS: kubectl ghost returned a note"
