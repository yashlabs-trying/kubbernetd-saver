#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# k3s-install.sh — installs k3s with containerd on Ubuntu
# ──────────────────────────────────────────────────────────────

echo "=== Installing k3s ==="

# Install k3s (lightweight K8s)
curl -sfL https://get.k3s.io | \
  INSTALL_K3S_EXEC="server \
    --disable=traefik \
    --disable=servicelb \
    --write-kubeconfig-mode=644 \
    --kubelet-arg=feature-gates=KubeletInUserNamespace=true" \
  sh -

# Wait for node to be ready
echo "=== Waiting for node ready ==="
sleep 10
k3s kubectl wait --for=condition=Ready node --all --timeout=60s || true

# Copy kubeconfig for kubectl
mkdir -p ~/.kube
cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
chmod 600 ~/.kube/config
export KUBECONFIG=~/.kube/config
echo "export KUBECONFIG=~/.kube/config" >> ~/.bashrc

echo "=== k3s installed ==="
k3s kubectl get nodes