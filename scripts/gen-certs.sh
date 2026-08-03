#!/usr/bin/env bash
# scripts/gen-certs.sh
#
# Generates a self-signed CA and a server cert/key for the GhostKube
# mutating webhook. Regenerate any time the certs are missing or expired —
# nothing here is meant to be committed (see .gitignore).
#
# Output (repo root by default): ca.crt, ca.key, server.crt, server.key
#
# The server cert's SAN must be the in-cluster DNS name the API server
# dials when it calls the webhook Service: <svc>.<namespace>.svc
set -euo pipefail

# Git Bash on Windows rewrites leading-slash args (like "/CN=...") into Windows
# paths before openssl ever sees them. Disable that here so -subj survives.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${1:-$SCRIPT_DIR/..}"
SVC="ghostkube-webhook-svc"
NS="ghostkube"
CN="${SVC}.${NS}.svc"

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

# extfile carrying the SAN; openssl chokes on CRLF here, so keep this LF-only.
printf 'subjectAltName = DNS:%s\n' "$CN" > server-ext.cnf

# CA
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -subj "/CN=ghostkube-webhook-ca" -days 3650 -out ca.crt

# Server key + CSR, signed by the CA above with the required SAN
openssl genrsa -out server.key 2048
openssl req -new -key server.key -subj "/CN=${CN}" -out server.csr
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 3650 -extfile server-ext.cnf

rm -f server.csr ca.srl server-ext.cnf

echo "Wrote to $OUT_DIR:"
echo "  ca.crt      - CA cert (base64 this into MutatingWebhookConfiguration's caBundle)"
echo "  ca.key      - CA private key (kept locally only; needed to re-sign, not committed)"
echo "  server.crt  - webhook server cert (SAN: ${CN})"
echo "  server.key  - webhook server private key (goes into the webhook-server-tls Secret)"
