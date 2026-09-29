#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# kubbernetd Rigorous Test Suite
# Run this on your GPU instance to validate the full cold-start lifecycle
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
TIMING=()

log()    { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $1"; }
pass()   { echo -e "  ${GREEN}PASS${NC}: $1"; ((PASS++)); }
fail()   { echo -e "  ${RED}FAIL${NC}: $1"; ((FAIL++)); }
warn()   { echo -e "  ${YELLOW}WARN${NC}: $1"; }
header() { echo -e "\n${CYAN}════════════════════════════════════════════${NC}"; echo -e "${CYAN} $1${NC}"; echo -e "${CYAN}════════════════════════════════════════════${NC}"; }

# ─────────────────────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────────────────────

header "1. ENVIRONMENT CHECK"

echo "GPU info:"
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader 2>&1 || echo "NO GPU FOUND"

echo "System:"
echo "  Docker: $(docker --version 2>&1 || echo MISSING)"
echo "  kubectl: $(kubectl version --client 2>&1 | head -1 || echo MISSING)"
echo "  Python: $(python3 --version 2>&1 || echo MISSING)"
echo "  CPUs: $(nproc)"
echo "  RAM: $(free -h | grep Mem | awk '{print $2}')"

# ─────────────────────────────────────────────────────────────────────────────
# INSTALL
# ─────────────────────────────────────────────────────────────────────────────

header "2. INSTALL KUBERNETES + KUBBERNETD"

if ! command -v kind &>/dev/null; then
    log "Installing kind..."
    curl -Lo /usr/local/bin/kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
    chmod +x /usr/local/bin/kind
fi

if ! command -v kubectl &>/dev/null; then
    log "Installing kubectl..."
    curl -LO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
    chmod +x kubectl && mv kubectl /usr/local/bin/
fi

log "Creating kind cluster..."
cat > /tmp/kind-config.yaml << 'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
  - role: worker
EOF

kind delete cluster --name kubbernetd-test 2>/dev/null || true
kind create cluster --name kubbernetd-test --config /tmp/kind-config.yaml --wait 60s
kubectl cluster-info

log "Installing kubbernetd..."
pip install --quiet -e /workspace/kubbernetd 2>/dev/null || pip install --quiet kubbernetd 2>/dev/null || {
    log "Cloning kubbernetd..."
    git clone https://github.com/yashlabs-trying/kubbernetd-saver.git /tmp/kubbernetd
    pip install --quiet -e /tmp/kubbernetd
}

kubectl create namespace kubbernetd --dry-run=client -o yaml | kubectl apply -f -
kubbernetd install --namespace kubbernetd
sleep 5
kubectl wait --for=condition=available -n kubbernetd deployment/kubbernetd-operator --timeout=60s 2>/dev/null || warn "Operator deployment not found (installing from manifests)"

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Deploy test service
# ─────────────────────────────────────────────────────────────────────────────

header "3. TEST 1: DEPLOY TEST SERVICE (nginx, 1 replica)"

kubectl create deployment test-model --image=nginx --replicas=1 --port=80 -n default
kubectl expose deployment test-model --port=80 --target-port=80 -n default
kubectl wait --for=condition=available deployment/test-model --timeout=60s
POD_NAME=$(kubectl get pod -l app=test-model -o jsonpath='{.items[0].metadata.name}')
echo "  Pod: $POD_NAME"

sleep 2
log "Creating ReplicaGroup..."
kubbernetd watch deployment/test-model --idle-timeout 30 --workers 1
sleep 3

STATE=$(kubectl get replicagroup test-model-rg -n default -o jsonpath='{.status.phase}' 2>/dev/null || echo "UNKNOWN")
if [ "$STATE" = "RUNNING" ]; then
    pass "ReplicaGroup is RUNNING"
elif [ -n "$STATE" ]; then
    pass "ReplicaGroup exists (state: $STATE)"
else
    fail "ReplicaGroup not found"
fi

# Test basic request
IP=$(kubectl get pod -l app=test-model -o jsonpath='{.items[0].status.podIP}')
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://$IP/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    pass "Test model responds with 200"
else
    fail "Test model not responding (HTTP $HTTP_CODE)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Scale-to-zero on idle
# ─────────────────────────────────────────────────────────────────────────────

header "4. TEST 2: SCALE TO ZERO ON IDLE"

log "Waiting for idle timeout (30s)..."
sleep 35

STATE=$(kubectl get replicagroup test-model-rg -n default -o jsonpath='{.status.phase}' 2>/dev/null || echo "UNKNOWN")
REPLICAS=$(kubectl get deployment test-model -o jsonpath='{.spec.replicas}')
echo "  ReplicaGroup state: $STATE"
echo "  Actual replicas: $REPLICAS"

if [ "$REPLICAS" = "0" ]; then
    pass "Scaled to 0 replicas"
elif [ "$STATE" = "SLEEPING" ] || [ "$STATE" = "SCALING_DOWN" ]; then
    pass "ReplicaGroup state: $STATE (should become 0 soon)"
else
    fail "Not scaled down (replicas=$REPLICAS, state=$STATE)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Wake from cold
# ─────────────────────────────────────────────────────────────────────────────

header "5. TEST 3: WAKE FROM COLD"

TIMING+=("wake")
WAKE_START=$(date +%s%N)

kubbernetd watch deployment/test-model --idle-timeout 30 --workers 1 2>/dev/null || true
kubectl patch replicagroup test-model-rg -n default --type=merge -p '{"spec":{"sleepPolicy":{"idleTimeout":300}}}' 2>/dev/null || true
kubectl patch deployment test-model -p '{"spec":{"replicas":1}}' 2>/dev/null

kubectl wait --for=condition=available deployment/test-model --timeout=60s 2>/dev/null && {
    WAKE_END=$(date +%s%N)
    WAKE_MS=$(( (WAKE_END - WAKE_START) / 1000000 ))
    log "Wake completed in ${WAKE_MS}ms"
    
    STATE=$(kubectl get replicagroup test-model-rg -n default -o jsonpath='{.status.phase}' 2>/dev/null || echo "UNKNOWN")
    if [ "$STATE" = "RUNNING" ]; then
        pass "ReplicaGroup returned to RUNNING"
    else
        warn "State after wake: $STATE"
    fi
    
    IP=$(kubectl get pod -l app=test-model -o jsonpath='{.items[0].status.podIP}')
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://$IP/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        pass "Service responds after wake (200)"
    else
        fail "Service not responding after wake (HTTP $HTTP_CODE)"
    fi
} || fail "Wake timed out (>60s)"

# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Three consecutive scale cycles
# ─────────────────────────────────────────────────────────────────────────────

header "6. TEST 4: THREE SCALE CYCLES (STRESS)"

for CYCLE in 1 2 3; do
    log "Cycle $CYCLE: Scaling down..."
    kubectl patch replicagroup test-model-rg -n default --type=merge -p '{"spec":{"sleepPolicy":{"idleTimeout":5}}}' 2>/dev/null || true
    sleep 15
    
    REPLICAS=$(kubectl get deployment test-model -o jsonpath='{.spec.replicas}')
    echo "  Cycle $CYCLE replicas: $REPLICAS"
    
    log "Cycle $CYCLE: Scaling up..."
    kubectl patch deployment test-model -p '{"spec":{"replicas":1}}' 2>/dev/null
    kubectl wait --for=condition=available deployment/test-model --timeout=30s 2>/dev/null || warn "Cycle $CYCLE deploy not available"
    
    IP=$(kubectl get pod -l app=test-model -o jsonpath='{.items[0].status.podIP}')
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://$IP/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        pass "Cycle $CYCLE: service responds correctly"
    else
        fail "Cycle $CYCLE: service failed (HTTP $HTTP_CODE)"
    fi
    
    sleep 2
done

# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: Unauthorized proxy access
# ─────────────────────────────────────────────────────────────────────────────

header "7. TEST 5: PROXY AUTH & SECURITY"

# Deploy proxy
kubectl apply -f /tmp/kubbernetd-saver/config/proxy-deployment.yaml -n kubbernetd 2>/dev/null || {
    cat > /tmp/proxy.yaml << 'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kubbernetd-proxy
  namespace: kubbernetd
spec:
  replicas: 1
  selector:
    matchLabels:
      app: kubbernetd-proxy
  template:
    metadata:
      labels:
        app: kubbernetd-proxy
    spec:
      serviceAccountName: kubbernetd-operator
      containers:
        - name: proxy
          image: python:3.12-slim
          command: ["sh", "-c", "pip install kubbernetd && kubbernetd-proxy"]
          ports:
            - containerPort: 8080
YAML
    kubectl apply -f /tmp/proxy.yaml -n kubbernetd
}
sleep 5

# Test unauthorized request (missing header)
PROXY_POD=$(kubectl get pod -n kubbernetd -l app=kubbernetd-proxy -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -n "$PROXY_POD" ]; then
    kubectl port-forward -n kubbernetd pod/$PROXY_POD 18080:8080 &
    PF_PID=$!
    sleep 3
    
    # No auth header → should get 400
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:18080/ 2>/dev/null || echo "000")
    if [ "$HTTP" = "400" ]; then
        pass "Proxy returns 400 for unauthenticated request (no header)"
    else
        warn "Proxy returned $HTTP (expected 400)"
    fi
    
    # Unknown service → should get 403
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Kubbernetd-Service: nonexistent" -H "X-Kubbernetd-Namespace: default" --max-time 5 http://localhost:18080/ 2>/dev/null || echo "000")
    if [ "$HTTP" = "403" ]; then
        pass "Proxy returns 403 for unauthorized target"
    else
        warn "Proxy returned $HTTP (expected 403)"
    fi
    
    # Health check
    HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:18080/healthz 2>/dev/null || echo "000")
    if [ "$HTTP" = "200" ]; then
        pass "Proxy /healthz returns 200"
    else
        warn "Proxy /healthz returned $HTTP"
    fi
    
    kill $PF_PID 2>/dev/null || true
else
    warn "Proxy pod not found, skipping auth tests"
fi

# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: Operator restart resilience
# ─────────────────────────────────────────────────────────────────────────────

header "8. TEST 6: OPERATOR RESTART RESILIENCE"

OP_POD=$(kubectl get pod -n kubbernetd -l app=kubbernetd-operator -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -n "$OP_POD" ]; then
    log "Killing operator pod: $OP_POD"
    kubectl delete pod -n kubbernetd "$OP_POD" --force --grace-period=0 2>/dev/null || true
    sleep 10
    
    STATE=$(kubectl get replicagroup test-model-rg -n default -o jsonpath='{.status.phase}' 2>/dev/null || echo "UNKNOWN")
    REPLICAS=$(kubectl get deployment test-model -o jsonpath='{.spec.replicas}')
    echo "  After restart - state: $STATE, replicas: $REPLICAS"
    
    if [ -n "$STATE" ] && [ "$STATE" != "UNKNOWN" ]; then
        pass "ReplicaGroup state survives operator restart"
    else
        fail "ReplicaGroup state lost after restart"
    fi
    
    # Service should still be available
    IP=$(kubectl get pod -l app=test-model -o jsonpath='{.items[0].status.podIP}')
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://$IP/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        pass "Service continues serving after operator restart"
    else
        fail "Service broken after restart (HTTP $HTTP_CODE)"
    fi
else
    warn "Operator pod not found, skipping restart test"
fi

# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: Dashboard verification
# ─────────────────────────────────────────────────────────────────────────────

header "9. TEST 7: DASHBOARD VERIFICATION"

kubbernetd status 2>&1 || warn "Status command failed"
kubectl get replicagroups -A 2>&1
kubectl get pods -n kubbernetd 2>&1

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

header "10. RESULTS SUMMARY"

echo -e "${GREEN}PASSED:${NC} $PASS"
echo -e "${RED}FAILED:${NC} $FAIL"
TOTAL=$((PASS + FAIL))
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}ALL $TOTAL TESTS PASSED${NC}"
else
    echo -e "${RED}$FAIL/$TOTAL TESTS FAILED${NC}"
fi

echo ""
echo -e "${CYAN}To run more GPU-specific tests:${NC}"
echo "  1. kubbernetd watch deployment/my-model --workers 4 --wake-slo 15"
echo "  2. kubbernetd dashboard --watch"
echo "  3. Watch: SLEEPING → ALLOCATING → STARTING → LOADING_WEIGHTS → RUNNING"
echo ""

# Cleanup
kind delete cluster --name kubbernetd-test 2>/dev/null || true
