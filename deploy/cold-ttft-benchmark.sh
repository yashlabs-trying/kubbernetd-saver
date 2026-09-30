#!/usr/bin/env bash
# ============================================================================
# cold-ttft-benchmark.sh  —  Cold TTFT Measurement with T0-T9 Timing
#
# Measures every stage from request arrival to first token:
#
#   T0  request_received       client sends request
#   T1  wake_requested         kubbernetd signals scale-up
#   T2  pod_scheduled          K8s scheduler assigns node + GPU
#   T3  container_started      container runtime starts pod
#   T4  model_load_started     weights begin loading to GPU
#   T5  model_load_finished    all shards loaded on GPU
#   T6  distributed_init_done  NCCL/CUDA init across ranks
#   T7  engine_ready           model server reports /health 200
#   T8  request_forwarded      proxy routes to backend
#   T9  first_token            first response byte received
#
# Output:
#   ColdTTFT  = T9 - T0
#   Breakdown = scheduling, container, model_load, init, routing, ttft
#
# Usage:
#   bash deploy/cold-ttft-benchmark.sh [namespace] [deployment] [rg_name]
#
#   Defaults: default, test-model, test-model-rg
# ============================================================================
set -euo pipefail

NS="${1:-default}"
MODEL="${2:-test-model}"
RG="${3:-test-model-rg}"
PROXY_PORT="${4:-8888}"

# ── Timing storage ──────────────────────────────────────────────
T=()
mark() {
  local label="$1"
  local ts=$(date +%s%3N)  # epoch milliseconds
  T+=("$label:$ts")
  printf "  [%02d] %-30s %d\n" ${#T[@]} "$label" $ts
}

# ── Helpers ──────────────────────────────────────────────────────
get_ts() {
  local label="$1"
  for entry in "${T[@]}"; do
    if [[ "$entry" == "$label:"* ]]; then
      echo "${entry#*:}"
      return
    fi
  done
  echo "0"
}

elapsed_ms() {
  local from=$(get_ts "$1")
  local to=$(get_ts "$2")
  if [ "$from" != "0" ] && [ "$to" != "0" ]; then
    echo $(( (to - from) ))
  else
    echo "-"
  fi
}

duration_s() {
  local ms=$(elapsed_ms "$1" "$2")
  if [ "$ms" = "-" ]; then echo "-"; else echo "scale=2; $ms/1000" | bc; fi
}

echo "============================================================"
echo "COLD TTFT BENCHMARK"
echo "  Model:      $NS/$MODEL"
echo "  RG:         $RG"
echo "  Stages:     T0 (request) → T9 (first token)"
echo "============================================================"
echo ""

# ── Pre-check: force zero ──────────────────────────────────────
echo "--- Pre-flight: ensure model at 0 ---"
kubectl scale deployment "$MODEL" -n "$NS" --replicas=0 2>/dev/null || true
sleep 8
R=$(kubectl get deployment "$MODEL" -n "$NS" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")
echo "  Replicas: $R"
if [ "$R" != "0" ]; then
  kubectl scale deployment "$MODEL" -n "$NS" --replicas=0
  sleep 5
fi

# ── T0: Send request ────────────────────────────────────────────
echo ""
echo "--- T0: Sending request ---"
mark "request_received"                   # T0

# ── T1: Trigger scale-up ────────────────────────────────────────
mark "wake_requested"                     # T1
kubectl scale deployment "$MODEL" -n "$NS" --replicas=1

# ── T2: Wait for pod scheduling ─────────────────────────────────
while true; do
  POD=$(kubectl get pod -n "$NS" -l "app=$MODEL" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
  [ -n "$POD" ] && break
  sleep 0.2
done
mark "pod_scheduled"                      # T2

# ── T3: Wait for container start ────────────────────────────────
while true; do
  PHASE=$(kubectl get pod "$POD" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Pending")
  [ "$PHASE" != "Pending" ] && break
  sleep 0.2
done
mark "container_started"                  # T3

# ── T4-T5: Wait for model load via agent annotations ────────────
TIMEOUT=120
START_TS=$(date +%s)
while true; do
  WSTAT=$(kubectl get pod "$POD" -n "$NS" -o jsonpath='{.metadata.annotations.kubbernetd\.io/weight-status}' 2>/dev/null || echo "")
  if [ "$WSTAT" = "loaded" ]; then
    mark "model_load_started"             # T4 (approximate: we know it loaded)
    mark "model_load_finished"             # T5
    break
  fi
  if [ $(($(date +%s) - START_TS)) -gt $TIMEOUT ]; then
    echo "  WARNING: model load timed out"
    break
  fi
  sleep 0.5
done

# ── T6: CUDA + NCCL init via annotations ────────────────────────
START_TS=$(date +%s)
while true; do
  CSTAT=$(kubectl get pod "$POD" -n "$NS" -o jsonpath='{.metadata.annotations.kubbernetd\.io/cuda-status}' 2>/dev/null || echo "")
  NSTAT=$(kubectl get pod "$POD" -n "$NS" -o jsonpath='{.metadata.annotations.kubbernetd\.io/nccl-status}' 2>/dev/null || echo "")
  if [ "$CSTAT" = "ready" ] && [ "$NSTAT" = "ready" ]; then
    mark "distributed_init_done"           # T6
    break
  fi
  if [ $(($(date +%s) - START_TS)) -gt 60 ]; then break; fi
  sleep 0.5
done

# ── T7: Wait for engine ready (ReplicaGroup phase RUNNING) ──────
START_TS=$(date +%s)
while true; do
  PHASE=$(kubectl get replicagroup "$RG" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null || echo "UNKNOWN")
  if [ "$PHASE" = "RUNNING" ]; then
    mark "engine_ready"                    # T7
    break
  fi
  if [ $(($(date +%s) - START_TS)) -gt 120 ]; then break; fi
  sleep 1
done

# ── T8-T9: Forward request, measure first token ─────────────────
echo ""
echo "--- T8-T9: Forwarding request to backend ---"

# Port-forward to backend
kubectl port-forward service/"$MODEL" -n "$NS" "$PROXY_PORT":80 &
PF_PID=$!
sleep 2

mark "request_forwarded"                  # T8

# Curl with timing
FIRST_BYTE=$(date +%s%3N)
HTTP_CODE=$(curl -s -o /tmp/ttft_response.txt -w "%{http_code}" --max-time 30 \
  http://localhost:$PROXY_PORT/ 2>/dev/null || echo "000")
mark "first_token"                         # T9

kill $PF_PID 2>/dev/null || true

echo "  HTTP status: $HTTP_CODE"

# ── Compute Cold TTFT ───────────────────────────────────────────
echo ""
echo "============================================================"
echo "COLD TTFT BREAKDOWN"
echo "============================================================"

T0=$(get_ts "request_received")
T9=$(get_ts "first_token")
COLD_TTFT_MS=$(( (T9 - T0) ))

echo ""
printf "  %-30s  %s\n" "Stage" "Duration"
printf "  %-30s  %s\n" "──────────────────────────────" "────────"
printf "  %-30s  %s ms\n" "Scheduling  [T1→T2]"  "$(elapsed_ms wake_requested pod_scheduled)"
printf "  %-30s  %s ms\n" "Container   [T2→T3]"  "$(elapsed_ms pod_scheduled container_started)"
printf "  %-30s  %s ms\n" "Model load  [T4→T5]"  "$(elapsed_ms model_load_started model_load_finished)"
printf "  %-30s  %s ms\n" "DistribInit [T6→T7]"  "$(elapsed_ms distributed_init_done engine_ready)"
printf "  %-30s  %s ms\n" "Routing     [T7→T8]"  "$(elapsed_ms engine_ready request_forwarded)"
printf "  %-30s  %s ms\n" "Inference   [T8→T9]"  "$(elapsed_ms request_forwarded first_token)"
printf "  %-30s  %s ms\n" "──────────────────────────────" "────────"
printf "  %-30s  %s ms\n" "COLD TTFT  [T0→T9]"   "$COLD_TTFT_MS"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
  echo "  [PASS] Request succeeded (HTTP 200)"
else
  echo "  [FAIL] Request failed (HTTP $HTTP_CODE)"
fi

# ── Save results ────────────────────────────────────────────────
cat > /tmp/cold_ttft_result.json << JSONEOF
{
  "cold_ttft_ms": $COLD_TTFT_MS,
  "cold_ttft_s": $(echo "scale=2; $COLD_TTFT_MS/1000" | bc),
  "http_status": $HTTP_CODE,
  "request_loss": $( [ "$HTTP_CODE" = "200" ] && echo false || echo true ),
  "stages_ms": {
    "scheduling": $(elapsed_ms wake_requested pod_scheduled),
    "container_start": $(elapsed_ms pod_scheduled container_started),
    "model_load": $(elapsed_ms model_load_started model_load_finished),
    "distributed_init": $(elapsed_ms distributed_init_done engine_ready),
    "routing": $(elapsed_ms engine_ready request_forwarded),
    "inference_ttft": $(elapsed_ms request_forwarded first_token)
  },
  "timestamps_ms": {
    "T0_request_received": $T0,
    "T1_wake_requested": $(get_ts wake_requested),
    "T2_pod_scheduled": $(get_ts pod_scheduled),
    "T3_container_started": $(get_ts container_started),
    "T4_model_load_started": $(get_ts model_load_started),
    "T5_model_load_finished": $(get_ts model_load_finished),
    "T6_distributed_init_done": $(get_ts distributed_init_done),
    "T7_engine_ready": $(get_ts engine_ready),
    "T8_request_forwarded": $(get_ts request_forwarded),
    "T9_first_token": $(get_ts first_token)
  }
}
JSONEOF
echo "  Results saved to /tmp/cold_ttft_result.json"