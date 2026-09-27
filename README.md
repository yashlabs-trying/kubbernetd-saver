# kubbernetd-saver

> Scale Kubernetes pods to zero when idle. Save costs. Instant cold start.

## What is it?

**kubbernetd** is a dead-simple Kubernetes operator that watches your deployments and scales them to **zero replicas** when they're idle — and brings them back **instantly** when traffic returns.

- **Works with per-hour & serverless pods** — savings either way
- **Instant cold start** via shadow pod technique
- **One command to install** — `kubbernetd install`
- **One command to enable** — `kubbernetd watch deployment/my-model`
- **Live dashboard** — `kubbernetd dashboard --watch`

## Quick start

```bash
# Install the CLI
pip install kubbernetd

# Install the operator in your cluster
kubbernetd install --namespace kubbernetd

# Enable cost-saving on a deployment
kubbernetd watch deployment/my-model --idle-timeout 5m

# See your savings
kubbernetd dashboard --watch
```

## Commands

| Command | Description |
|---|---|
| `install` | Install the operator, CRD, and RBAC into your cluster |
| `watch <deployment>` | Start watching a deployment for idle scaling |
| `unwatch <deployment>` | Stop watching a deployment |
| `dashboard` | Show savings dashboard with live data |
| `status` | Check operator health |

## How it works

```
[3 pods] ── idle 5m ──► [0 pods] ── traffic arrives ──► [pods start + serve]
                               ▲                          │
                               └── instant cold start ────┘
```

### Architecture

```
                    ┌──────────────────────┐
                    │   kubbernetd-operator │  Watches idle time, scales to 0
                    └──────────┬───────────┘
                               │
  ┌──────────────┐    ┌───────▼────────────┐
  │  kubbernetd   │    │  Model Pod         │
  │  -proxy       │───►│  + kubbernetd      │
  │ (buffer reqs) │    │   -agent (sidecar) │
  └──────────────┘    └────────────────────┘
```

## Configuration

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `KUBBERNETD_IDLE_TIMEOUT` | `300` | Seconds of idle before scaling to zero |
| `KUBBERNETD_CHECK_INTERVAL` | `30` | How often the operator checks idle status |
| `KUBBERNETD_METRICS_PORT` | `8080` | Prometheus metrics port |
| `KUBBERNETD_SHADOW_PODS` | `1` | Number of hidden warm pods for instant cold start |
| `KUBBERNETD_WARMUP_CMD` | `""` | Command to run for model warmup |
| `KUBBERNETD_REQUEST_TTL` | `30` | Max seconds to buffer a request during cold start |

## Cost savings

kubbernetd tracks idle time per deployment and estimates savings based on:

- **Per-hour pod cost**: $0.50/hr (default, adjustable)
- **Idle time**: Total seconds the deployment was at zero replicas
- **Saved** = (idle_seconds / 3600) * hourly_cost

Run `kubbernetd dashboard --watch` to see live savings.

## License

MIT