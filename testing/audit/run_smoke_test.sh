#!/bin/bash
export PATH="/opt/homebrew/bin:$PATH"
echo "=== SMOKE TEST ==="
echo "=== PROXY REQUEST TO TEST MODEL ==="
curl -s -o /dev/null -w "HTTP %{http_code}" -H "X-Kubbernetd-Service: test-model-rg" --max-time 30 http://localhost:18080/
echo ""
echo "=== REPLICAS ==="
kubectl get deployment test-model -o jsonpath="{.spec.replicas}"
echo ""
echo "=== RG STATUS ==="
kubectl get replicagroup test-model-rg -n default -o jsonpath="{.status.phase}"
echo ""
echo "=== ALL PODS ==="
kubectl get pods -A
echo "=== SMOKE DONE ==="
