# kubbernetd-saver

> Scale Kubernetes pods to zero when idle. Save costs. Instant cold start.

## What is it?

**kubbernetd** is a dead-simple Kubernetes operator that watches your deployments and scales them to **zero replicas** when they're idle — and brings them back **instantly** when traffic returns.

- **Works with per-hour & serverless pods** — savings either way
- **Instant cold start** via shadow pod technique
- **One command to install** — `kubbernetd install`
- **One command to enable** — `kubbernetd watch deployment/my-model`

## Quick start

```bash
pip install kubbernetd

# Install the operator in your cluster
kubbernetd install

# Enable cost-saving on a deployment
kubbernetd watch deployment/my-model --idle-timeout 5m

# See your savings
kubbernetd dashboard
```

## How it works

```
[3 pods] ── idle 5m ──► [0 pods] ── traffic arrives ──► [pods start + serve]
                               ▲                          │
                               └── instant cold start ────┘
```

## License

MIT