#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# verify-gpu.sh — check that nvidia.com/gpu is schedulable
# ──────────────────────────────────────────────────────────────

echo "=== Verifying GPU Availability ==="

# Check node labels
echo "--- Node GPU labels ---"
k3s kubectl get nodes -o json | \
  jq '.items[0].status.capacity' | \
  grep -i nvidia || echo "No nvidia capacity found"

echo ""
echo "--- Deploying GPU test pod ---"
k3s kubectl apply -f - << 'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test
spec:
  restartPolicy: OnFailure
  containers:
    - name: cuda-test
      image: nvidia/cuda:12.4.1-base-ubuntu22.04
      command: ["nvidia-smi"]
      resources:
        limits:
          nvidia.com/gpu: 1
EOF

echo "Waiting for pod..."
sleep 10
k3s kubectl logs gpu-test 2>&1 || true

echo ""
echo "=== GPU Status ==="
k3s kubectl describe pod gpu-test 2>&1 | grep -E "State:|Status:" || true

k3s kubectl delete pod gpu-test --force --grace-period=0 2>/dev/null || true

echo ""
echo "=== nvidia-smi (host) ==="
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader