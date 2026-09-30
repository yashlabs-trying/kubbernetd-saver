#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# nvidia-runtime.sh — configures NVIDIA container runtime for k3s
# https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
# ──────────────────────────────────────────────────────────────

echo "=== Installing NVIDIA Container Toolkit ==="

# Add NVIDIA package repositories
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

apt-get update -qq
apt-get install -y -qq nvidia-container-toolkit

# Configure containerd for NVIDIA
echo "=== Configuring containerd for NVIDIA ==="
nvidia-ctk runtime configure --runtime=containerd
systemctl restart containerd

# Restart k3s to pick up the new runtime
echo "=== Restarting k3s ==="
systemctl restart k3s
sleep 10

echo "=== NVIDIA runtime configured ==="
k3s kubectl get nodes