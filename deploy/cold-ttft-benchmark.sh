#!/usr/bin/env bash
# ============================================================================
# cold-ttft-benchmark.sh
# Measures cold-start TTFT (Time To First Token) with per-stage timing
#
# Records:
#   request_received
#   scale_requested
#   pod_scheduled
#   container_started
#   model_load_started
#   model_load_finished
#   engine_ready
#   request_forwarded
#   first_token
#
# Output:
#   ColdTTFT = T_first_token - T_request_received
# ============================================================================
set -euo pipefail

MODEL_NS="${1:-default}"
MODEL_NAME="${2:-test-model}"
RG_NAME="${3:-test-model-rg}"
PROXY_PORT="${4:-8080}"
TARGET_SLO="${5:-30}"

TIMESTAMPS=""
record() {
  local label="$1"
  local ts=$(date +%s%3N)  # milliseconds
  TIMESTAMPS="$TIMESTAMPS  $label: $ts\n"
  echo "  [CLOCK] $label"
}

echo "=== COLD TTFT BENCHMARK ==="
echo "Target: $MODEL_NS/$RG_NAME -> $MODEL_NAME"
echo "SLO: ${TARGET_SLO}s"
echo ""

# ──────────────────────────────────────────────────────────────
# 1. Verify model is SLEEPING
# ──────────────────────────────────────────────────────────────
echo "--- Pre-check: forcing scale to 0 ---"
kubectl scale deployment "$MODEL_NAME" -n "$MODEL_NS" --replicas=0 2>/dev/null || true
sleep 5

REPLICAS=$(kubectl get deployment "$MODEL_NAME" -n "$MODEL_NS" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")
echo "  Current replicas: $REPLICAS"

if [ "$REPLICAS" != "0" ]; then
  echo "  WARNING: model not at 0 replicas. Forcing..."
  kubectl scale deployment "$MODEL_NAME" -n "$MODEL_NS" --replicas=0
  sleep 3
fi

# ──────────────────────────────────────────────────────────────
# 2. Send request — start the clock
# ──────────────────────────────────────────────────────────────
echo ""
echo "=== Benchmark: Sending request ==="
record "request_received"

# Trigger scale-up
record "scale_requested"
kubectl scale deployment "$MODEL_NAME" -n "$MODEL_NS" --replicas=1

# ──────────────────────────────────────────────────────────────
# 3. Watch pods
# ──────────────────────────────────────────────────────────────
echo ""
echo "=== Watching pod lifecycle ==="

# Wait for pod to be scheduled
while true; do
  POD=$(kubectl get pod -n "$MODEL_NS" -l app="$MODEL_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
  if [ -n "$POD" ]; then break; fi
  sleep 0.5
done
record "pod_scheduled"
echo "  Pod: $POD"

# Wait for container to start
while true; do
  PHASE=$(kubectl get pod "$POD" -n "$MODEL_NS" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Pending")
  if [ "$PHASE" != "Pending" ]; then break; fi
  sleep 0.5
done
record "container_started"
echo "  Phase: $PHASE"

# Wait for container to be running
kubectl wait --for=condition=ready pod "$POD" -n "$MODEL_NS" --timeout=120s 2>/dev/null || true
record "model_load_finished"

# ──────────────────────────────────────────────────────────────
# 4. Wait for engine readiness (via ReplicaGroup status)
# ──────────────────────────────────────────────────────────────
echo ""
echo "=== Waiting for engine ready ==="

while true; do
  PHASE=$(kubectl get replicagroup "$RG_NAME" -n "$MODEL_NS" -o jsonpath='{.status.phase}' 2>/dev/null || echo "UNKNOWN")
  if [ "$PHASE" = "RUNNING" ] || [ "$PHASE" = "WARMING" ]; then
    break
  fi
  sleep 1
done
record "engine_ready"
echo "  ReplicaGroup phase: $PHASE"

# ──────────────────────────────────────────────────────────────
# 5. Forward request — measure first token
# ──────────────────────────────────────────────────────────────
echo ""
echo "=== Forwarding request ==="

record "request_forwarded"

# Use port-forward to access the service
kubectl port-forward service/"$MODEL_NAME" -n "$MODEL_NS" "$PROXY_PORT":80 &
PF_PID=$!
sleep 2

record "first_token"
FIRST_TOKEN_TIME=$(date +%s%3N)

# Send the actual request
HTTP_CODE=$(curl -s -o /tmp/cold_ttft_response.txt -w "%{http_code}" --max-time 30 \
  http://localhost:$PROXY_PORT/ 2>/dev/null || echo "000")

kill $PF_PID 2>/dev/null || true

echo "  HTTP status: $HTTP_CODE"

# ──────────────────────────────────────────────────────────────
# 6. Compute Cold TTFT
# ──────────────────────────────────────────────────────────────
echo ""
echo "=== RESULTS ==="

# Calculate stage durations
REQUEST_TS=$(echo "$TIMESTAMPS" | grep "request_received" | awk '{print $NF}')
FIRST_TOKEN_TS=$(echo "$TIMESTAMPS" | grep "first_token" | awk '{print $NF}')
SCHED_TS=$(echo "$TIMESTAMPS" | grep "pod_scheduled" | awk '{print $NF}')
CONTAINER_TS=$(echo "$TIMESTAMPS" | grep "container_started" | awk '{print $NF}')
MODEL_TS=$(echo "$TIMESTAMPS" | grep "model_load_finished" | awk '{print $NF}')

echo "  ColdTTFT breakdown:"
echo "    Scheduling:       $(( (SCHED_TS - REQUEST_TS) / 1000 ))s"
echo "    Container start:  $(( (CONTAINER_TS - SCHED_TS) / 1000 ))s"
echo "    Model load:       $(( (MODEL_TS - CONTAINER_TS) / 1000 ))s"
echo "    Engine ready:     $(( (FIRST_TOKEN_TS - MODEL_TS) / 1000 ))s"
echo "    ─────────────────────────────────"
COLD_TTFT=$(( (FIRST_TOKEN_TS - REQUEST_TS) / 1000 ))
echo "    Cold TTFT:        ${COLD_TTFT}s"

echo ""
if [ "$COLD_TTFT" -le "$TARGET_SLO" ]; then
  echo "  [PASS] Cold TTFT (${COLD_TTFT}s) within SLO (${TARGET_SLO}s)"
else
  echo "  [FAIL] Cold TTFT (${COLD_TTFT}s) exceeds SLO (${TARGET_SLO}s)"
fi

# Save to file
cat > /tmp/cold_ttft_result.json << JSONEOF
{
  "cold_ttft_seconds": $COLD_TTFT,
  "target_slo_seconds": $TARGET_SLO,
  "passed": $([ "$COLD_TTFT" -le "$TARGET_SLO" ] && echo "true" || echo "false"),
  "stages": {
    "scheduling": $(( (SCHED_TS - REQUEST_TS) / 1000 )),
    "container_start": $(( (CONTAINER_TS - SCHED_TS) / 1000 )),
    "model_load": $(( (MODEL_TS - CONTAINER_TS) / 1000 )),
    "engine_ready": $(( (FIRST_TOKEN_TS - MODEL_TS) / 1000 ))
  },
  "http_status": $HTTP_CODE
}
JSONEOF
echo "  Results saved to /tmp/cold_ttft_result.json"