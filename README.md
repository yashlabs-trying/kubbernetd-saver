# kubbernetd

**Scale-to-zero for GPU model servers on Kubernetes.** Idle deployments drop to
zero replicas; the first new request is held by a buffering proxy while the
model wakes, then forwarded. No dropped requests, no paying for idle GPUs.

[![CI](https://github.com/yashlabs-trying/kubbernetd-saver/actions/workflows/ci.yml/badge.svg)](https://github.com/yashlabs-trying/kubbernetd-saver/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

```
 [N pods] ── idle for idleTimeout ──► [0 pods]
                                         │  request arrives
                                         ▼
                     proxy buffers request + signals operator
                                         │
                     operator scales up, waits for model readiness
                                         │
                     proxy forwards buffered request ──► first token
```

## Why

GPU inference pods are expensive and often idle (dev/staging models, long-tail
customer models, nightly batch endpoints). Kubernetes' HPA cannot scale to zero,
and naive scale-to-zero drops the first request. kubbernetd closes that gap for
model servers specifically: it understands that "pod Running" is not "model
ready", and it measures cold start stage by stage.

## What is implemented

| Component | What it does |
|---|---|
| **Operator** (kopf) | Watches `CostSaver` and `ReplicaGroup` CRDs, detects idleness, scales Deployments to 0 and back, exposes Prometheus metrics. |
| **ReplicaGroup CRD** | Model-aware state machine for multi-worker servers (vLLM-style TP/PP, shards, wake SLO, cold-start timeout, sleep policy). |
| **Buffering proxy** | Holds requests during wake-up, signals the operator, forwards with connection pooling, load-balancing, streaming and auth. |
| **Agent sidecar** | Graduated readiness: waits for the engine's real health endpoint plus a warmup request before declaring the pod ready. |
| **Weight cache** | DaemonSet that keeps model shards on node NVMe so a woken pod does not re-download weights. |
| **ColdTTFT benchmark** | [`deploy/cold-ttft-benchmark.sh`](deploy/cold-ttft-benchmark.sh) times every stage T0–T9: scheduling, container start, weight load, engine init, routing, first token. |
| **CLI** | `install`, `watch`, `unwatch`, `status`, `dashboard` (estimated savings). |

**Tests:** 77 unit tests, plus 9 end-to-end scenarios that run in CI on a real
[kind](https://kind.sigs.k8s.io/) cluster with the operator and proxy deployed:

1. idle deployment scales itself to zero
2. a cold request is preserved through the proxy (not dropped)
3. three back-to-back sleep/wake cycles
4. two models woken concurrently
5. operator restart mid-lifecycle
6. an in-flight request blocks scale-down
7. invalid configuration is rejected cleanly
8. a slow-starting model's real readiness delay is respected
9. 100 concurrent requests against a cold deployment

## Quick start

kubbernetd is not published to PyPI yet; install from source.

```bash
git clone https://github.com/yashlabs-trying/kubbernetd-saver
cd kubbernetd-saver
pip install -e ".[test]"
pytest -q                       # 77 unit tests, no cluster needed

# Install CRDs, RBAC, operator and proxy into the current kube-context
kubbernetd install --namespace kubbernetd

# Scale a deployment to zero after 5 idle minutes
kubbernetd watch deployment/my-model --idle-timeout 5m
kubbernetd dashboard --watch
```

A model-aware example for a multi-GPU vLLM deployment is in
[`config/samples/replicagroup-qwen.yaml`](config/samples/replicagroup-qwen.yaml).

## Measuring cold start

```bash
bash deploy/cold-ttft-benchmark.sh <namespace> <deployment> <replicagroup>
```

The script reports `ColdTTFT = T9 − T0` and the breakdown per stage, so you can
see whether a slow wake-up is scheduling, image pull, weight loading or engine
initialization. Cold start is dominated by weight loading for large models,
which is what the node-local weight cache targets.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `KUBBERNETD_IDLE_TIMEOUT` | `300` | Seconds without traffic before scaling to zero |
| `KUBBERNETD_CHECK_INTERVAL` | `30` | Idle-check period in seconds |
| `KUBBERNETD_METRICS_PORT` | `8080` | Prometheus metrics port |
| `KUBBERNETD_WARMUP_CMD` | `""` | Command run by the agent to warm the model |
| `KUBBERNETD_REQUEST_TTL` | `30` | Max seconds a request is buffered during wake-up |

## Savings estimate

The dashboard estimates savings as `idle_seconds / 3600 × hourly_cost`
(default `$0.50/h`, configurable per deployment). It is an estimate from
observed idle time, not a billing-API figure.

## Roadmap

- **Warm standby ("shadow") pods** — the `shadowPods` field is accepted by the
  CRD but not yet acted on. The plan is to keep N hidden ready pods outside the
  Service selector and swap one in on wake-up, trading a small idle cost for a
  near-zero first-token delay.
- Publish to PyPI and a Helm chart repository.
- Published ColdTTFT numbers for vLLM on A10G/L4/A100.

## Project layout

```
kubbernetd/
  operator/   kopf handlers, idle controller, ReplicaGroup controller, scaler, metrics
  proxy/      buffering reverse proxy, discovery, wake signalling, auth
  agent/      readiness sidecar, warmer, weight-cache manager, engine adapters
  monitor/    idle detection and Kubernetes watchers
  cli/        Typer CLI
config/       CRDs, RBAC, deployments, samples
helm/         Helm chart
deploy/       k3s bootstrap, ColdTTFT benchmark, test model
```

## License

MIT © Yashvardhan Singh Shekhawat
