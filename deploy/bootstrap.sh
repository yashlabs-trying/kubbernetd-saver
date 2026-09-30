#!/usr/bin/env bash
# ============================================================================
# kubbernetd-bootstrap.sh
# One-command setup: Ubuntu + NVIDIA Driver → k3s → GPU → kubbernetd → test
#
# Usage:
#   curl -sfL https://raw.githubusercontent.com/yashlabs-trying/kubbernetd-saver/main/deploy/bootstrap.sh | bash
#
# Or locally:
#   bash deploy/bootstrap.sh
# ============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $1"; }
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$SCRIPT_DIR/k3s"
KUBE_DIR="$SCRIPT_DIR/kubbernetd"
MODEL_DIR="$SCRIPT_DIR/test-model"

log "=== KUBBERNETD BOOTSTRAP ==="
log "Script dir: $SCRIPT_DIR"

# ──────────────────────────────────────────────────────────────
# Step 1: Install k3s
# ──────────────────────────────────────────────────────────────
log "Step 1/6: Installing k3s..."
bash "$K3S_DIR/install.sh" && ok "k3s installed" || fail "k3s install failed"

# ──────────────────────────────────────────────────────────────
# Step 2: Install NVIDIA runtime
# ──────────────────────────────────────────────────────────────
log "Step 2/6: Configuring NVIDIA container runtime..."
bash "$K3S_DIR/nvidia-runtime.sh" && ok "NVIDIA runtime configured" || fail "NVIDIA runtime failed"

# ──────────────────────────────────────────────────────────────
# Step 3: Deploy NVIDIA device plugin
# ──────────────────────────────────────────────────────────────
log "Step 3/6: Deploying NVIDIA device plugin..."
kubectl apply -f "$K3S_DIR/device-plugin.yaml"
sleep 15
kubectl -n kube-system wait --for=condition=ready pod -l name=nvidia-device-plugin-ds --timeout=30s 2>/dev/null && ok "device plugin ready" || fail "device plugin not ready"

# ──────────────────────────────────────────────────────────────
# Step 4: Verify GPU
# ──────────────────────────────────────────────────────────────
log "Step 4/6: Verifying GPU access..."
bash "$K3S_DIR/verify-gpu.sh" 2>&1 | head -20

GPU_AVAIL=$(kubectl get nodes -o json | jq '.items[0].status.capacity["nvidia.com/gpu"]' 2>/dev/null || echo "0")
if [ "$GPU_AVAIL" != "null" ] && [ "$GPU_AVAIL" -gt 0 ] 2>/dev/null; then
  ok "nvidia.com/gpu=${GPU_AVAIL} available"
else
  fail "nvidia.com/gpu not detected - check NVIDIA drivers"
  exit 1
fi

# ──────────────────────────────────────────────────────────────
# Step 5: Deploy kubbernetd
# ──────────────────────────────────────────────────────────────
log "Step 5/6: Deploying kubbernetd operator..."
kubectl create namespace kubbernetd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$KUBE_DIR/crd.yaml"
kubectl apply -f "$KUBE_DIR/rbac.yaml"
kubectl apply -f "$KUBE_DIR/operator.yaml"
sleep 15
kubectl -n kubbernetd wait --for=condition=available deployment/kubbernetd-operator --timeout=60s 2>/dev/null && ok "operator ready" || fail "operator not ready"

# ──────────────────────────────────────────────────────────────
# Step 6: Deploy test model + ReplicaGroup
# ──────────────────────────────────────────────────────────────
log "Step 6/6: Deploying test model..."
kubectl apply -f "$MODEL_DIR/deployment.yaml"
kubectl apply -f "$MODEL_DIR/service.yaml"
kubectl wait --for=condition=available deployment/test-model --timeout=60s 2>/dev/null && ok "test model ready" || fail "test model not ready"

kubectl apply -f "$MODEL_DIR/costsaver.yaml"
sleep 5
RG_STATE=$(kubectl get replicagroup test-model-rg -n default -o jsonpath='{.status.phase}' 2>/dev/null || echo "UNKNOWN")
ok "ReplicaGroup phase: $RG_STATE"

# ──────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────
echo ""
log "=== BOOTSTRAP COMPLETE ==="
echo ""
kubectl get nodes
echo ""
kubectl get pods -A | grep -E "kubbernetd|test-model|nvidia"
echo ""
kubectl get replicagroups -A
echo ""
log "GPU: $(nvidia-smi --query-gpu=name,memory.free --format=csv,noheader 2>&1 | head -1)"
log "Cold TTFT benchmark ready. Run:  kubbernetd dashboard --watch"
log "Test wake:                   kubectl scale deployment test-model --replicas=0"
log "Then send request:           curl -H 'X-Kubbernetd-Service: test-model-rg' http://<proxy-ip>/v1/chat"