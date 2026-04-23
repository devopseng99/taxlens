#!/bin/bash
# Setup Stripe products and prices for TaxLens.
#
# The restricted API key (rk_test_*) does not have product/price write permissions.
# Create these in the Stripe Dashboard (https://dashboard.stripe.com/test/products)
# then run this script to update the K8s secret with the price IDs.
#
# Products to create in Stripe Dashboard:
#   1. TaxLens Starter   — $29/mo  recurring (monthly)
#   2. TaxLens Professional — $99/mo  recurring (monthly)
#   3. TaxLens Enterprise — $299/mo recurring (monthly)
#
# Each product gets a default Price object. Copy the price_xxx IDs.
#
# Usage:
#   ./setup-stripe-products.sh <starter_price_id> <professional_price_id> <enterprise_price_id>
#
# Example:
#   ./setup-stripe-products.sh price_1ABC price_2DEF price_3GHI

set -euo pipefail

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <starter_price_id> <professional_price_id> <enterprise_price_id>"
    echo ""
    echo "Create products in Stripe Dashboard first:"
    echo "  1. TaxLens Starter     — \$29/mo  (monthly recurring)"
    echo "  2. TaxLens Professional — \$99/mo  (monthly recurring)"
    echo "  3. TaxLens Enterprise  — \$299/mo (monthly recurring)"
    echo ""
    echo "Then pass the price IDs to this script."
    exit 1
fi

STARTER_PRICE=$1
PROFESSIONAL_PRICE=$2
ENTERPRISE_PRICE=$3

echo "Updating taxlens-stripe secret with price IDs..."
kubectl get secret taxlens-stripe -n taxlens -o json | \
    python3 -c "
import sys, json, base64
secret = json.load(sys.stdin)
secret['data']['price-starter'] = base64.b64encode(b'$STARTER_PRICE').decode()
secret['data']['price-professional'] = base64.b64encode(b'$PROFESSIONAL_PRICE').decode()
secret['data']['price-enterprise'] = base64.b64encode(b'$ENTERPRISE_PRICE').decode()
json.dump(secret, sys.stdout)
" | kubectl apply -f - 2>&1

echo ""
echo "Secret updated. Price IDs:"
echo "  Starter:      $STARTER_PRICE"
echo "  Professional:  $PROFESSIONAL_PRICE"
echo "  Enterprise:    $ENTERPRISE_PRICE"
echo ""
echo "Now restart the API pod to pick up the new env vars:"
echo "  kubectl rollout restart deployment/taxlens-api -n taxlens"
