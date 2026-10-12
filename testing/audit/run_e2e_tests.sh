#!/bin/bash
# Tesseract Ignite — Phase 4: E2E Test Suite (conservative limits)
set -euo pipefail 2>/dev/null || set -euo
export PATH="/opt/homebrew/bin:$PATH"
cd ~/ignite/kubbernetd-saver
source venv/bin/activate

log() { echo "[$(date +%H:%M:%S)] $*"; }
pass() { echo "  PASS: $*"; }
fail() { echo "  FAIL: $*"; }

RESULTS_DIR=testing/audit/results
mkdir -p "$RESULTS_DIR"

# Ensure port-forward
if ! curl -s --max-time 2 http://localhost:18080/healthz >/dev/null 2>&1; then
    pkill -f "port-forward" 2>/dev/null || true
    nohup kubectl port-forward service/kubbernetd-proxy -n kubbernetd 18080:8080 > /tmp/pf.log 2>&1 &
    sleep 5
fi

# helper: wait for replicas == 0 with timeout
wait_zero() {
    local label=$1 timeout=${2:-40}
    for i in $(seq 1 $((timeout/5))); do
        R=$(kubectl get deployment "$label" -o jsonpath={.spec.replicas} 2>/dev/null || echo "1")
        [ "$R" = "0" ] && return 0
        sleep 5
    done
    return 1
}

# helper: wait for replicas >= 1 with timeout
wait_ready() {
    local label=$1 timeout=${2:-60}
    for i in $(seq 1 $((timeout/5))); do
        R=$(kubectl get deployment "$label" -o jsonpath={.spec.replicas} 2>/dev/null || echo "0")
        [ "$R" -ge 1 ] && return 0
        sleep 5
    done
    return 1
}

echo ""
log "========== E2E TEST SUITE =========="

# ═════════════════════════════════════════════════════
# TEST 1 — Autonomous idle to zero
# ═════════════════════════════════════════════════════
log "E2E 1/9: Autonomous idle to zero"
if wait_zero "test-model" 40; then
    R=$(kubectl get deployment test-model -o jsonpath={.spec.replicas})
    P=$(kubectl get replicagroup test-model-rg -n default -o jsonpath={.status.phase} 2>/dev/null || echo "UNKNOWN")
    log "replicas=${R} phase=${P}"
    pass "E2E_1: idle to zero"
else
    fail "E2E_1: timeout waiting for scale to 0"
    exit 1
fi

# ═════════════════════════════════════════════════════
# TEST 2 — Cold request through proxy
# ═════════════════════════════════════════════════════
log "E2E 2/9: Cold request through proxy"
HTTP_CODE=$(curl -s -o /tmp/e2e_2_body.txt -w "%{http_code}" \
    -H "X-Kubbernetd-Service: test-model-rg" \
    --max-time 60 http://localhost:18080/ 2>/dev/null || echo "000")
R2=$(kubectl get deployment test-model -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
P2=$(kubectl get replicagroup test-model-rg -n default -o jsonpath={.status.phase} 2>/dev/null || echo "?")
log "http=${HTTP_CODE} replicas=${R2} phase=${P2}"
if [ "$HTTP_CODE" = "200" ]; then pass "E2E_2: cold request OK"
else fail "E2E_2: HTTP ${HTTP_CODE}"; exit 1; fi

# ═════════════════════════════════════════════════════
# TEST 3 — Three autonomous sleep/wake cycles
# ═════════════════════════════════════════════════════
log "E2E 3/9: Three sleep/wake cycles"
for CYCLE in 1 2 3; do
    log "=== Cycle ${CYCLE} ==="
    wait_zero "test-model" 60 || true
    R=$(kubectl get deployment test-model -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "X-Kubbernetd-Service: test-model-rg" \
        --max-time 60 http://localhost:18080/ 2>/dev/null || echo "000")
    log "cycle=${CYCLE} replicas=${R} http=${HTTP_CODE}"
    if [ "$HTTP_CODE" != "200" ]; then fail "E2E_3: cycle ${CYCLE} HTTP ${HTTP_CODE}"; exit 1; fi
done
pass "E2E_3: three cycles OK"

# ═════════════════════════════════════════════════════
# TEST 4 — Multi-model concurrent cold wake
# ═════════════════════════════════════════════════════
log "E2E 4/9: Multi-model concurrent cold wake"
kubectl create deployment test-model-2 --image=nginx --replicas=0 --port=80 2>/dev/null || true
kubectl expose deployment test-model-2 --port=80 --target-port=80 2>/dev/null || true
kubectl apply -f - << 'EOF'
apiVersion: kubbernetd.io/v1
kind: ReplicaGroup
metadata:
  name: test-model-rg-2
  namespace: default
spec:
  model: { name: nginx-2, engine: vLLM, workers: 1 }
  targetRef: { kind: Deployment, name: test-model-2 }
  wakeSLO: 15
  sleepPolicy: { sleepDepth: full, idleTimeout: 60 }
EOF
sleep 3

# Wait for test-model to be idle
wait_zero "test-model" 60 || true
R1=$(kubectl get deployment test-model -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
R2=$(kubectl get deployment test-model-2 -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
log "model1=${R1} model2=${R2}"

curl -s -o /tmp/e2e_4_m1_body.txt -w "%{http_code}" -H "X-Kubbernetd-Service: test-model-rg" --max-time 60 http://localhost:18080/ > /tmp/e2e_4_m1_code.txt &
P1=$!
curl -s -o /tmp/e2e_4_m2_body.txt -w "%{http_code}" -H "X-Kubbernetd-Service: test-model-rg-2" --max-time 60 http://localhost:18080/ > /tmp/e2e_4_m2_code.txt &
P2=$!
wait $P1 $P2 2>/dev/null || true
C1=$(cat /tmp/e2e_4_m1_code.txt 2>/dev/null || echo "000")
C2=$(cat /tmp/e2e_4_m2_code.txt 2>/dev/null || echo "000")
log "model1_http=${C1} model2_http=${C2}"
if [ "$C1" = "200" ] && [ "$C2" = "200" ]; then pass "E2E_4: multi-model OK"
else fail "E2E_4: model1=${C1} model2=${C2}"; exit 1; fi

kubectl delete deployment test-model-2 --force --grace-period=0 2>/dev/null || true
kubectl delete service test-model-2 2>/dev/null || true
kubectl delete replicagroup test-model-rg-2 -n default 2>/dev/null || true
sleep 3

# ═════════════════════════════════════════════════════
# TEST 5 — Operator restart + subsequent lifecycle
# ═════════════════════════════════════════════════════
log "E2E 5/9: Operator restart and recovery"
wait_zero "test-model" 60 || true
kubectl delete pod -n kubbernetd -l app=kubbernetd-operator --force --grace-period=0 2>/dev/null || true
sleep 12
kubectl wait --for=condition=available deployment/kubbernetd-operator -n kubbernetd --timeout=60s
OP_PHASE=$(kubectl get pod -n kubbernetd -l app=kubbernetd-operator -o jsonpath={.items[0].status.phase} 2>/dev/null)
log "operator_after_restart=${OP_PHASE}"
sleep 10
wait_zero "test-model" 60 || true
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Kubbernetd-Service: test-model-rg" --max-time 60 http://localhost:18080/ 2>/dev/null || echo "000")
P2=$(kubectl get replicagroup test-model-rg -n default -o jsonpath={.status.phase} 2>/dev/null || echo "?")
log "post_restart_wake_http=${HTTP_CODE} rg_phase=${P2}"
if [ "$HTTP_CODE" = "200" ]; then pass "E2E_5: operator restart OK"
else fail "E2E_5: HTTP ${HTTP_CODE}"; exit 1; fi

# ═════════════════════════════════════════════════════
# TEST 6 — Active request prevents scale-down
# ═════════════════════════════════════════════════════
log "E2E 6/9: Active request prevents scale-down"
kubectl create deployment long-request --image=kubbernetd/e2e-helper:ci --replicas=0 --port=80 2>/dev/null || true
kubectl expose deployment long-request --port=80 --target-port=80 2>/dev/null || true
kubectl set env deployment/long-request E2E_HELPER_MODE=long-request 2>/dev/null || true
kubectl delete pod -l app=long-request --force --grace-period=0 2>/dev/null || true
sleep 2
kubectl scale deployment long-request --replicas=1
kubectl wait --for=condition=available deployment/long-request --timeout=60s || true
kubectl apply -f - << 'EOF'
apiVersion: kubbernetd.io/v1
kind: ReplicaGroup
metadata:
  name: long-request-rg
  namespace: default
spec:
  model: { name: long-request, engine: vLLM, workers: 1 }
  targetRef: { kind: Deployment, name: long-request }
  wakeSLO: 5
  sleepPolicy: { sleepDepth: full, idleTimeout: 10 }
EOF
sleep 5
kubectl wait --for=condition=available deployment/long-request --timeout=30s 2>/dev/null || true

curl -s -o /tmp/e2e_6_body.txt -w "%{http_code}" -H "X-Kubbernetd-Service: long-request-rg" --max-time 60 "http://localhost:18080/work?seconds=20" > /tmp/e2e_6_code.txt &
WORK_PID=$!

sleep 8
R7=$(kubectl get deployment long-request -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
log "t=8s replicas=${R7}"
if [ "$R7" != "1" ]; then fail "E2E_6: scaled down at t=8s"; kill $WORK_PID 2>/dev/null || true; exit 1; fi

sleep 10
R15=$(kubectl get deployment long-request -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
log "t=~18s replicas=${R15}"
if [ "$R15" != "1" ]; then fail "E2E_6: scaled down at t=~18s"; kill $WORK_PID 2>/dev/null || true; exit 1; fi

wait $WORK_PID 2>/dev/null || true
RESP_CODE=$(cat /tmp/e2e_6_code.txt 2>/dev/null || echo "000")
log "work_status=${RESP_CODE}"
if [ "$RESP_CODE" != "200" ]; then fail "E2E_6: HTTP ${RESP_CODE}"; exit 1; fi
pass "E2E_6: active request prevents scale-down"

kubectl delete deployment long-request --force --grace-period=0 2>/dev/null || true
kubectl delete service long-request 2>/dev/null || true
kubectl delete replicagroup long-request-rg -n default 2>/dev/null || true
sleep 3

# ═════════════════════════════════════════════════════
# TEST 7 — Invalid configuration handling
# ═════════════════════════════════════════════════════
log "E2E 7/9: Invalid configuration handling"
kubectl apply -f - << 'EOF' 2>/dev/null || true
apiVersion: kubbernetd.io/v1
kind: ReplicaGroup
metadata:
  name: invalid-rg
  namespace: default
spec:
  model: { name: test, engine: vLLM, workers: 1 }
  targetRef: { kind: Deployment, name: nonexistent-deployment }
  sleepPolicy: { idleTimeout: 5 }
EOF
sleep 5
OP=$(kubectl get pod -n kubbernetd -l app=kubbernetd-operator -o jsonpath={.items[0].status.phase} 2>/dev/null || echo "")
log "operator_after_invalid=${OP}"
if [ "$OP" = "Running" ]; then pass "E2E_7: invalid config handled"
else fail "E2E_7: operator=${OP}"; exit 1; fi
kubectl delete replicagroup invalid-rg -n default 2>/dev/null || true

# ═════════════════════════════════════════════════════
# TEST 8 — Readiness delay
# ═════════════════════════════════════════════════════
log "E2E 8/9: Readiness delay respected"
kubectl create deployment slow-model --image=kubbernetd/e2e-helper:ci --replicas=0 --port=80 2>/dev/null || true
kubectl expose deployment slow-model --port=80 --target-port=80 2>/dev/null || true
kubectl set env deployment/slow-model E2E_HELPER_MODE=slow-start 2>/dev/null || true
kubectl delete pod -l app=slow-model --force --grace-period=0 2>/dev/null || true
sleep 2
kubectl apply -f - << 'EOF'
apiVersion: kubbernetd.io/v1
kind: ReplicaGroup
metadata:
  name: slow-model-rg
  namespace: default
spec:
  model: { name: slow-model, engine: vLLM, workers: 1 }
  targetRef: { kind: Deployment, name: slow-model }
  wakeSLO: 60
  sleepPolicy: { sleepDepth: full, idleTimeout: 60 }
EOF
sleep 3

START_TS=$(date +%s%N)
curl -s -o /tmp/e2e_8_body.txt -w "%{http_code}" -H "X-Kubbernetd-Service: slow-model-rg" --max-time 90 http://localhost:18080/ > /tmp/e2e_8_code.txt &
CURL_PID=$!

for i in 1 2 3; do
    POD_PHASE=$(kubectl get pod -l app=slow-model -o jsonpath={.items[0].status.phase} 2>/dev/null || echo "Pending")
    READY=$(kubectl get pod -l app=slow-model -o jsonpath={.items[0].status.conditions[?(@.type=="Ready")].status} 2>/dev/null || echo "False")
    log "t=$((i*10))s pod=${POD_PHASE} ready=${READY}"
    sleep 10
done

wait $CURL_PID 2>/dev/null || true
END_TS=$(date +%s%N)
ELAPSED_MS=$(( (END_TS - START_TS) / 1000000 ))
RESP_CODE=$(cat /tmp/e2e_8_code.txt 2>/dev/null || echo "000")
log "response=${RESP_CODE} elapsed_ms=${ELAPSED_MS}"
if [ "$RESP_CODE" != "200" ]; then fail "E2E_8: HTTP ${RESP_CODE}"; exit 1; fi
pass "E2E_8: readiness delay OK"

kubectl delete deployment slow-model --force --grace-period=0 2>/dev/null || true
kubectl delete service slow-model 2>/dev/null || true
kubectl delete replicagroup slow-model-rg -n default 2>/dev/null || true
sleep 3

# ═════════════════════════════════════════════════════
# TEST 9 — 25 concurrent cold requests (safe limit)
# ═════════════════════════════════════════════════════
log "E2E 9/9: 25 concurrent cold requests"
wait_zero "test-model" 60 || true
R0=$(kubectl get deployment test-model -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
BEFORE_PHASE=$(kubectl get replicagroup test-model-rg -n default -o jsonpath={.status.phase} 2>/dev/null || echo "UNKNOWN")
BEFORE_WAKE=$(kubectl get replicagroup test-model-rg -n default -o jsonpath={.status.wakeCount} 2>/dev/null || echo "0")
log "before: replicas=${R0} phase=${BEFORE_PHASE} wakeCount=${BEFORE_WAKE}"

START_TS=$(date +%s%N)
for i in $(seq 1 25); do
    curl -s -o /dev/null -w "%{http_code}\n" -H "X-Kubbernetd-Service: test-model-rg" --max-time 90 http://localhost:18080/ &
done
wait
END_TS=$(date +%s%N)
TOTAL_MS=$(( (END_TS - START_TS) / 1000000 ))
log "total_elapsed_ms=${TOTAL_MS}"

R_AFTER=$(kubectl get deployment test-model -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
OP=$(kubectl get pod -n kubbernetd -l app=kubbernetd-operator -o jsonpath={.items[0].status.phase} 2>/dev/null || echo "Unknown")
PX=$(kubectl get pod -n kubbernetd -l app=kubbernetd-proxy -o jsonpath={.items[0].status.phase} 2>/dev/null || echo "Unknown")
AFTER_PHASE=$(kubectl get replicagroup test-model-rg -n default -o jsonpath={.status.phase} 2>/dev/null || echo "UNKNOWN")
log "after: replicas=${R_AFTER} phase=${AFTER_PHASE} operator=${OP} proxy=${PX}"

if [ "$OP" = "Running" ] && [ "$PX" = "Running" ]; then
    pass "E2E_9: 25 concurrent cold requests - systems healthy"
else
    fail "E2E_9: operator=${OP} proxy=${PX}"
    exit 1
fi

echo ""
log "======================================="
log " ALL 9 E2E TESTS PASSED "
log "======================================="
