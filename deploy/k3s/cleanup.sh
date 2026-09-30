#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# cleanup.sh — removes all kubbernetd + test resources
# Safety: never deletes k3s or NVIDIA runtime
# ──────────────────────────────────────────────────────────────

echo "=== Cleaning up kubbernetd resources ==="

# Delete ReplicaGroups
kubectl delete replicagroups --all -A 2>/dev/null || true

# Delete operator
kubectl delete -f deploy/kubbernetd/operator.yaml -n kubbernetd 2>/dev/null || true
kubectl delete -f deploy/kubbernetd/proxy.yaml -n kubbernetd 2>/dev/null || true
kubectl delete -f deploy/kubbernetd/rbac.yaml -n kubbernetd 2>/dev/null || true

# Delete namespace (will clean up all resources)
kubectl delete namespace kubbernetd --force --grace-period=0 2>/dev/null || true

# Delete CRD
kubectl delete -f deploy/kubbernetd/crd.yaml 2>/dev/null || true

# Delete test models
kubectl delete deployment test-model test-model-2 2>/dev/null || true
kubectl delete service test-model test-model-2 2>/dev/null || true

# Delete GPU test artifacts
kubectl delete pod gpu-test 2>/dev/null || true

echo "=== Cleanup complete ==="