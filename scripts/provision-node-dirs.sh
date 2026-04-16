#!/bin/bash
# Provision local PV directories on mgplcb05 for TaxLens
set -euo pipefail

NODE_IP="192.168.29.147"
SSH_KEY="$HOME/.ssh/id_rsa_devops_ssh"

echo "=== Provisioning TaxLens directories on mgplcb05 ($NODE_IP) ==="

ssh -i "$SSH_KEY" "$NODE_IP" <<'REMOTE'
sudo mkdir -p /opt/k8s-pers/vol1/taxlens-docs
sudo chown 1000:1000 /opt/k8s-pers/vol1/taxlens-docs
sudo chmod 755 /opt/k8s-pers/vol1/taxlens-docs
echo "Created /opt/k8s-pers/vol1/taxlens-docs"
ls -la /opt/k8s-pers/vol1/ | grep taxlens
REMOTE

echo "=== Done ==="
