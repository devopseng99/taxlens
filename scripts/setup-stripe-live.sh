#!/bin/bash
# TaxLens — Stripe Live Mode Cutover
#
# Prerequisites:
#   1. Create live products in Stripe Dashboard (https://dashboard.stripe.com/products):
#      - TaxLens Starter     — $29/mo  (monthly recurring)
#      - TaxLens Professional — $99/mo  (monthly recurring)
#      - TaxLens Enterprise  — $299/mo (monthly recurring)
#
#   2. Create a restricted API key (https://dashboard.stripe.com/apikeys):
#      - Permissions: Customers (Write), Checkout Sessions (Write),
#        Subscriptions (Write), Webhook Endpoints (Read),
#        Billing Portal (Write), Usage Records (Write)
#      - Name: "TaxLens API"
#
#   3. Create a live webhook endpoint (https://dashboard.stripe.com/webhooks):
#      - URL: https://dropit.istayintek.com/api/billing/webhook
#      - Events: checkout.session.completed, customer.subscription.updated,
#                customer.subscription.deleted, invoice.paid, invoice.payment_failed
#      - Copy the signing secret (whsec_...)
#
# Usage:
#   ./setup-stripe-live.sh <live_secret_key> <live_webhook_secret> \
#       <starter_price_id> <professional_price_id> <enterprise_price_id>
#
# This script:
#   1. Updates the K8s secret with live credentials
#   2. Sets STRIPE_LIVE_MODE_CONFIRMED=true
#   3. Restarts the API pod
#   4. Verifies health endpoint shows stripe_mode=live

set -euo pipefail

if [ "$#" -ne 5 ]; then
    echo "Usage: $0 <live_secret_key> <live_webhook_secret> <starter_price> <pro_price> <ent_price>"
    echo ""
    echo "Example:"
    echo "  $0 rk_live_xxx whsec_xxx price_1AAA price_1BBB price_1CCC"
    echo ""
    echo "See script header for prerequisites."
    exit 1
fi

LIVE_KEY=$1
LIVE_WEBHOOK=$2
STARTER_PRICE=$3
PROFESSIONAL_PRICE=$4
ENTERPRISE_PRICE=$5

# Validate key prefixes
if [[ ! "$LIVE_KEY" =~ ^(sk_live_|rk_live_) ]]; then
    echo "ERROR: Secret key must start with sk_live_ or rk_live_"
    echo "  Got: ${LIVE_KEY:0:12}..."
    exit 1
fi

if [[ ! "$LIVE_WEBHOOK" =~ ^whsec_ ]]; then
    echo "ERROR: Webhook secret must start with whsec_"
    exit 1
fi

echo "=== TaxLens Stripe Live Mode Cutover ==="
echo ""
echo "  Secret key: ${LIVE_KEY:0:12}...${LIVE_KEY: -4}"
echo "  Webhook:    ${LIVE_WEBHOOK:0:10}..."
echo "  Starter:    $STARTER_PRICE"
echo "  Professional: $PROFESSIONAL_PRICE"
echo "  Enterprise: $ENTERPRISE_PRICE"
echo ""
read -p "This will enable REAL CHARGES. Continue? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "1/3 — Updating K8s secret..."
kubectl create secret generic taxlens-stripe \
    --namespace=taxlens \
    --from-literal=secret-key="$LIVE_KEY" \
    --from-literal=webhook-secret="$LIVE_WEBHOOK" \
    --from-literal=price-starter="$STARTER_PRICE" \
    --from-literal=price-professional="$PROFESSIONAL_PRICE" \
    --from-literal=price-enterprise="$ENTERPRISE_PRICE" \
    --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "2/3 — Setting STRIPE_LIVE_MODE_CONFIRMED in deployment..."
# Patch the deployment to add the confirmation env var
kubectl set env deployment/taxlens-api -n taxlens \
    STRIPE_LIVE_MODE_CONFIRMED=true

echo ""
echo "3/3 — Waiting for rollout..."
kubectl rollout status deployment/taxlens-api -n taxlens --timeout=120s

echo ""
echo "=== Verification ==="
sleep 5
HEALTH=$(curl -s https://dropit.istayintek.com/api/health)
MODE=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('stripe_mode','?'))")
echo "  stripe_mode: $MODE"

if [ "$MODE" = "live" ]; then
    echo ""
    echo "✓ Stripe LIVE mode is active. Real charges will be processed."
    echo ""
    echo "To revert to test mode:"
    echo "  kubectl set env deployment/taxlens-api -n taxlens STRIPE_LIVE_MODE_CONFIRMED-"
    echo "  # Then update the secret back to test keys"
else
    echo ""
    echo "WARNING: stripe_mode is '$MODE', expected 'live'."
    echo "Check pod logs: kubectl logs -n taxlens -l app.kubernetes.io/component=api --tail=20"
fi
