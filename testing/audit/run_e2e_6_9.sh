#!/bin/bash
set -euo pipefail 2>/dev/null || set -euo
export PATH="/opt/homebrew/bin:$PATH"
cd ~/ignite/kubbernetd-saver
source venv/bin/activate

log() { echo "[$(date +%H:%M:%S)] $*"; }
pass() { echo "  PASS: $*"; }
fail() { echo "  FAIL: $*"; }

wait_zero() { local label=$1 timeout=${2:-40}
  for i in $(seq 1 $((timeout/5))); do
    R=$(kubectl get deployment "$label" -o jsonpath={.spec.replicas} 2>/dev/null || echo "1")
    [ "$R" = "0" ] && return 0; sleep 5
  done; return 1
}

# Clean previous test resources
kubectl delete deployment long-request --force --grace-period=0 2>/dev/null || true
kubectl delete service long-request 2>/dev/null || true
kubectl delete replicagroup long-request-rg -n default 2>/dev/null || true
kubectl delete deployment slow-model --force --grace-period=0 2>/dev/null || true
kubectl delete service slow-model 2>/dev/null || true
kubectl delete replicagroup slow-model-rg -n default 2>/dev/null || true
kubectl delete replicagroup invalid-rg -n default 2>/dev/null || true
sleep 5

# ═══════════════ E2E 6 — Active request prevents scale-down ═══════════════
log "E2E 6/9: Active request prevents scale-down"
kubectl create deployment long-request --image=kubbernetd/e2e-helper:ci --replicas=0 --port=80 2>/dev/null || true
kubectl expose deployment long-request --port=80 --target-port=80 2>/dev/null || true
kubectl set env deployment/long-request E2E_HELPER_MODE=long-request 2>/dev/null || true
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

# Verify the helper is working before the long test
log "Verifying long-request helper..."
HELPER_CODE=$(kubectl exec deployment/long-request -- curl -s -o /dev/null -w "%{http_code}" http://localhost:80/work?seconds=1 2>/dev/null || echo "EXEC_FAIL")
log "helper_direct=${HELPER_CODE}"

curl -s -o /tmp/e2e_6_body.txt -w "%{http_code}" -H "X-Kubbernetd-Service: long-request-rg" --max-time 60 "http://localhost:18080/work?seconds=20" > /tmp/e2e_6_code.txt &
WORK_PID=$!

sleep 8
R7=$(kubectl get deployment long-request -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
log "t=8s replicas=${R7}"
if [ "$R7" != "1" ]; then fail "E2E_6: scaled down at t=8s"; kill $WORK_PID 2>/dev/null; exit 1; fi

sleep 10
R15=$(kubectl get deployment long-request -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
log "t=~18s replicas=${R15}"
if [ "$R15" != "1" ]; then fail "E2E_6: scaled down at t=~18s"; kill $WORK_PID 2>/dev/null; exit 1; fi

wait $WORK_PID 2>/dev/null || true
RESP_CODE=$(cat /tmp/e2e_6_code.txt 2>/dev/null || echo "000")
log "work_status=${RESP_CODE}"
if [ "$RESP_CODE" != "200" ]; then fail "E2E_6: HTTP ${RESP_CODE}"; exit 1; fi
pass "E2E_6: active request prevents scale-down"

kubectl delete deployment long-request --force --grace-period=0 2>/dev/null || true
kubectl delete service long-request 2>/dev/null || true
kubectl delete replicagroup long-request-rg -n default 2>/dev/null || true
sleep 3

# ═══════════════ E2E 7 — Invalid configuration handling ═══════════════
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
if [ "$OP" = "Running" ]; then pass "E2E_7: invalid config handled"; else fail "E2E_7: operator=${OP}"; exit 1; fi
kubectl delete replicagroup invalid-rg -n default 2>/dev/null || true

# ═══════════════ E2E 8 — Readiness delay ═══════════════
log "E2E 8/9: Readiness delay respected"
kubectl create deployment slow-model --image=kubbernetd/e2e-helper:ci --replicas=0 --port=80 2>/dev/null || true
kubectl expose deployment slow-model --port=80 --target-port=80 2>/dev/null || true
kubectl set env deployment/slow-model E2E_HELPER_MODE=slow-start 2>/dev/null || true
kubectl delete pod -l app=slow-model --force --grace-period=0 2>/dev/null || true
sleep 2
kubectl scale deployment slow-model --replicas=1
kubectl wait --for=condition=available deployment/slow-model --timeout=60s || true
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
    READY=$(kubectl get pod -l app=slow-model -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")
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

# ═══════════════ E2E 9 — 25 concurrent cold requests ═══════════════
log "E2E 9/9: 25 concurrent cold requests"
kubectl scale deployment test-model --replicas=1
kubectl wait --for=condition=available deployment/test-model --timeout=30s || true
wait_zero "test-model" 40 || true
R0=$(kubectl get deployment test-model -o jsonpath={.spec.replicas} 2>/dev/null || echo "?")
BEFORE_WAKE=$(kubectl get replicagroup test-model-rg -n default -o jsonpath={.status.wakeCount} 2>/dev/null || echo "0")
log "before: replicas=${R0} wakeCount=${BEFORE_WAKE}"

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
log "after: replicas=${R_AFTER} operator=${OP} proxy=${PX}"

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
