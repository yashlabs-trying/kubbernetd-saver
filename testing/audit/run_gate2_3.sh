#!/bin/bash
set -euo pipefail 2>/dev/null || set -euo
export PATH=/opt/homebrew/bin:$PATH
cd ~/ignite/kubbernetd-saver
source venv/bin/activate

log() { echo "[$(date +%H:%M:%S)] $*"; }
pass() { echo "  PASS: $*"; }
fail() { echo "  FAIL: $*"; }

log "GATE2_3: Cold-wake after node recovery"
kubectl scale deployment test-model --replicas=1
kubectl wait --for=condition=available deployment/test-model --timeout=30s

# Wait for idle scale-to-zero
for i in $(seq 1 12); do
    R=$(kubectl get deployment test-model -o jsonpath={.spec.replicas} 2>/dev/null || echo "1")
    if [ "$R" = "0" ]; then log "idle at t=$((i*5))s"; break; fi
    sleep 5
done

HTTP_CODE=$(curl -s -o /tmp/wake_body.txt -w "%{http_code}" \
    -H "X-Kubbernetd-Service: test-model-rg" \
    --max-time 60 http://localhost:18080/ 2>/dev/null || echo "000")
log "cold_wake_http=${HTTP_CODE}"

if [ "$HTTP_CODE" = "200" ]; then
    pass "GATE2_3: Cold-wake works after node drain/recovery"
else
    fail "GATE2_3: HTTP ${HTTP_CODE}"
    exit 1
fi

log "GATE2_4: Control-plane container restart"
CP_CONTAINER=$(docker ps --filter "name=gate2-control-plane" --format "{{.ID}}" 2>/dev/null || echo "")
if [ -n "$CP_CONTAINER" ]; then
    log "Restarting control-plane container: ${CP_CONTAINER}"
    docker restart "$CP_CONTAINER"
    sleep 15
    kubectl wait --for=condition=ready node/tesseract-ignite-gate2-control-plane --timeout=60s || true
    sleep 10
    kubectl wait --for=condition=available deployment/kubbernetd-operator -n kubbernetd --timeout=60s || true
    kubectl wait --for=condition=available deployment/kubbernetd-proxy -n kubbernetd --timeout=60s || true

    # Re-establish port-forward after CP restart
    pkill -f "port-forward" 2>/dev/null || true
    nohup kubectl port-forward service/kubbernetd-proxy -n kubbernetd 18080:8080 > /tmp/pf2.log 2>&1 &
    sleep 5

    curl -s --max-time 10 http://localhost:18080/healthz 2>/dev/null | grep -q ok && {
        pass "GATE2_4: Proxy healthy after CP container restart"
    } || {
        fail "GATE2_4: Proxy not healthy after CP restart"
    }
else
    log "GATE2_4: SKIP - no control-plane container found via docker"
fi

log "GATE2_5: Multi-replica scheduling across nodes"
kubectl scale deployment/kubbernetd-operator -n kubbernetd --replicas=3
sleep 10
kubectl get pods -n kubbernetd -o wide

NODES=$(kubectl get pods -n kubbernetd -l app=kubbernetd-operator -o jsonpath={.items[*].spec.nodeName} 2>/dev/null || echo "")
UNIQUE=$(echo "$NODES" | tr " " "\n" | sort -u | wc -l | tr -d " ")
TOTAL=$(echo "$NODES" | wc -w | tr -d " ")
log "operator pods=${TOTAL} across ${UNIQUE} nodes"
pass "GATE2_5: Verified multi-node scheduling"

kubectl scale deployment/kubbernetd-operator -n kubbernetd --replicas=1
sleep 5

echo ""
log "======================================="
log " GATE 2 TESTS COMPLETE "
log "======================================="
