#!/bin/bash
# Setup Plaid credentials as K8s secret for TaxLens
#
# Usage:
#   # Generate a Fernet key first:
#   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#
#   # Create the secret:
#   bash scripts/setup-plaid-secrets.sh <client_id> <secret> <fernet_key>
#
#   # Or set env vars:
#   export PLAID_CLIENT_ID=xxx PLAID_SECRET=xxx PLAID_FERNET_KEY=xxx
#   bash scripts/setup-plaid-secrets.sh

set -euo pipefail

NAMESPACE="taxlens"
SECRET_NAME="plaid-credentials"

CLIENT_ID="${1:-${PLAID_CLIENT_ID:-}}"
SECRET="${2:-${PLAID_SECRET:-}}"
FERNET_KEY="${3:-${PLAID_FERNET_KEY:-}}"

if [[ -z "$CLIENT_ID" || -z "$SECRET" || -z "$FERNET_KEY" ]]; then
  echo "Usage: $0 <client_id> <secret> <fernet_key>"
  echo "  Or set PLAID_CLIENT_ID, PLAID_SECRET, PLAID_FERNET_KEY env vars"
  echo ""
  echo "Generate a Fernet key:"
  echo "  python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
  exit 1
fi

echo "Creating Plaid credentials secret in namespace $NAMESPACE..."

kubectl create secret generic "$SECRET_NAME" \
  --namespace="$NAMESPACE" \
  --from-literal=client-id="$CLIENT_ID" \
  --from-literal=secret="$SECRET" \
  --from-literal=fernet-key="$FERNET_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Done. Enable Plaid in values.yaml: plaid.enabled: true"
echo "Then: helm upgrade --install taxlens charts/taxlens -n taxlens -f overrides.yaml"
