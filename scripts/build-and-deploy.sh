#!/bin/bash
# Build, transfer, and deploy TaxLens to K8s
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NODE_IP="192.168.29.147"
SSH_KEY="$HOME/.ssh/id_rsa_devops_ssh"
IMAGE="localhost/taxlens-api:latest"
TAR="/tmp/taxlens-api.tar"
NS="taxlens"

echo "=== Building TaxLens API image ==="
cd "$REPO_ROOT"
podman build --network=host -f Dockerfile -t "$IMAGE" .

echo "=== Saving and transferring to mgplcb05 ==="
podman save "$IMAGE" -o "$TAR"
cat "$TAR" | ssh -i "$SSH_KEY" "$NODE_IP" \
  "cat > /tmp/taxlens-api.tar && sudo /var/lib/rancher/rke2/bin/ctr --address /run/k3s/containerd/containerd.sock -n k8s.io images import /tmp/taxlens-api.tar && rm /tmp/taxlens-api.tar"
rm -f "$TAR"

echo "=== Deploying via Helm ==="
helm upgrade --install taxlens "$REPO_ROOT/charts/taxlens" \
  --namespace="$NS" --create-namespace

echo "=== Waiting for rollout ==="
kubectl rollout status deployment/taxlens-api -n "$NS" --timeout=120s

echo "=== Verifying ==="
kubectl get pods -n "$NS"
echo ""
echo "Done. Add CF tunnel entry for dropit.istayintek.com -> taxlens-api.taxlens.svc.cluster.local:8000"
