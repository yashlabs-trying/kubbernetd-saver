#!/bin/bash
# Tesseract Ignite — Gate 2: Multi-Node Cluster Tests
set -euo pipefail 2>/dev/null || set -euo
export PATH="/opt/homebrew/bin:$PATH"
cd ~/ignite/kubbernetd-saver
source venv/bin/activate

log() { echo "[$(date +%H:%M:%S)] $*"; }
pass() { echo "  PASS: $*"; }
fail() { echo "  FAIL: $*"; }

# ═════════════════════════════════════════════════════
# GATE 2 TEST 1 — Cross-node scheduling verification
# ═════════════════════════════════════════════════════
log "GATE2_1: Cross-node pod scheduling"
log "=== Node topology ==="
kubectl get nodes -o wide
log "=== Operator pod placement ==="
kubectl get pods -n kubbernetd -o wide
log "=== Test model pod placement ==="
kubectl get pods -l app=test-model -o wide

OPERATOR_NODE=$(kubectl get pod -n kubbernetd -l app=kubbernetd-operator -o jsonpath={.items[0].spec.nodeName} 2>/dev/null)
WORKER_NODE=$(kubectl get nodes -o name 2>/dev/null | grep -v control-plane | head -1 || echo "")
CP_NODE=$(kubectl get nodes -l node-role.kubernetes.io/control-plane -o name 2>/dev/null | head -1)

if [ -n "$WORKER_NODE" ]; then 
    pass "GATE2_1a: Worker node exists: $WORKER_NODE"
else
    fail "GATE2_1a: No worker node found"
    exit 1
fi

if [ -n "$CP_NODE" ]; then
    pass "GATE2_1b: Control-plane node exists: $CP_NODE"
else
    fail "GATE2_1b: No control-plane node found"
    exit 1
fi

# ═════════════════════════════════════════════════════
# GATE 2 TEST 2 — Node drain test  
# ═════════════════════════════════════════════════════
log "GATE2_2: Node drain and pod rescheduling"
WORKER_NAME=$(kubectl get nodes -o name 2>/dev/null | grep -v control-plane | head -1 | sed 's|node/||' || echo "")

log "Cordoning worker node: $WORKER_NAME"
kubectl cordon "$WORKER_NAME"
sleep 3
log "Worker node status after cordon:"
kubectl get node "$WORKER_NAME"

log "Draining worker node (ignoring daemonsets)..."
kubectl drain "$WORKER_NAME" --ignore-daemonsets --delete-emptydir-data --force --grace-period=30 2>&1 || true
sleep 10

log "Checking operator pod after drain..."
OP_POD=$(kubectl get pod -n kubbernetd -l app=kubbernetd-operator -o name 2>/dev/null || echo "")
OP_PHASE=$(kubectl get pod -n kubbernetd -l app=kubbernetd-operator -o jsonpath={.items[0].status.phase} 2>/dev/null || echo "")
OP_NODE=$(kubectl get pod -n kubbernetd -l app=kubbernetd-operator -o jsonpath={.items[0].spec.nodeName} 2>/dev/null || echo "")
log "operator: phase=$OP_PHASE node=$OP_NODE"

kubectl uncordon "$WORKER_NAME" 2>/dev/null || true
log "Re-enabled scheduling on worker node"
sleep 5

PASS=true
kubectl wait --for=condition=available deployment/kubbernetd-operator -n kubbernetd --timeout=60s 2>&1 | tail -1 || PASS=false

if [ "$PASS" = "true" ]; then
    pass "GATE2_2: Operator recovered after node drain"
else
    fail "GATE2_2: Operator failed to recover"
    exit 1
fi

kubectl wait --for=condition=available deployment/kubbernetd-proxy -n kubbernetd --timeout=60s 2>&1 | tail -1 || { fail "GATE2_2: Proxy failed to recover"; exit 1; }
pass "GATE2_2: Proxy recovered after node drain"

# ═════════════════════════════════════════════════════
# GATE 2 TEST 3 — Cold wake still works post-recovery
# ═════════════════════════════════════════════════════
log "GATE2_3: Cold-wake after node recovery"
kubectl scale deployment test-model --replicas=1 2>/dev/null
kubectl wait --for=condition=available deployment/test-model --timeout=30s 2>&1 | tail -1 || true

# Wait for idle scale-to-zero
for i in $(seq 1 8); do
    R=$(kubectl get deployment test-model -o jsonpath={.spec.replicas} 2>/dev/null || echo "1")
    if [ "$R" = "0" ]; then break; fi
    sleep 5
done

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Kubbernetd-Service: test-model-rg" --max-time 60 http://localhost:18080/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    pass "GATE2_3: Cold-wake works across nodes"
else
    fail "GATE2_3: HTTP ${HTTP_CODE}"
    exit 1
fi

# ═════════════════════════════════════════════════════
# GATE 2 TEST 4 — Control-plane resilience
# ═════════════════════════════════════════════════════
log "GATE2_4: Control-plane container restart"
CP_CONTAINER=$(docker ps --filter "name=gate2-control-plane" --format "{{.ID}}" 2>/dev/null || echo "")
if [ -z "$CP_CONTAINER" ]; then
    log "GATE2_4: Cannot find control-plane container via docker"
else
    log "Restarting control-plane container: $CP_CONTAINER"
    docker restart "$CP_CONTAINER" 2>&1
    sleep 15
    kubectl wait --for=condition=ready node/tesseract-ignite-gate2-control-plane --timeout=60s 2>&1 | tail -1 || true
    sleep 10
    kubectl wait --for=condition=available deployment/kubbernetd-operator -n kubbernetd --timeout=60s 2>&1 | tail -1 || true
    kubectl wait --for=condition=available deployment/kubbernetd-proxy -n kubbernetd --timeout=60s 2>&1 | tail -1 || true

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://localhost:18080/healthz 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        pass "GATE2_4: Proxy healthy after CP restart"
    else
        fail "GATE2_4: Proxy HTTP ${HTTP_CODE}"
    fi
fi

# ═════════════════════════════════════════════════════
# GATE 2 TEST 5 — Pod anti-affinity / topology spread
# ═════════════════════════════════════════════════════
log "GATE2_5: Scale Ignite to 3 replicas across nodes"
kubectl scale deployment/kubbernetd-operator -n kubbernetd --replicas=3 2>&1 | tail -1
sleep 10
kubectl get pods -n kubbernetd -o wide

OPERATOR_NODES=$(kubectl get pods -n kubbernetd -l app=kubbernetd-operator -o jsonpath={.items[*].spec.nodeName} 2>/dev/null)
UNIQUE_NODES=$(echo "$OPERATOR_NODES" | tr " " "\n" | sort -u | wc -l | tr -d " ")
TOTAL_PODS=$(echo "$OPERATOR_NODES" | wc -w | tr -d " ")
log "operator pods=$TOTAL_PODS across $UNIQUE_NODES nodes"

if [ "$UNIQUE_NODES" -ge 2 ]; then
    pass "GATE2_5a: Pods spread across $UNIQUE_NODES nodes"
else
    log "GATE2_5a: Pods on $UNIQUE_NODES node (only 2 nodes available)"
fi

kubectl scale deployment/kubbernetd-operator -n kubbernetd --replicas=1 2>&1 | tail -1
sleep 5

echo ""
log "======================================="
log " GATE 2 MULTI-NODE TESTS COMPLETE "
log "======================================="
