# kubbernetd Architecture

## Overview

kubbernetd is a Kubernetes operator that watches deployments and scales them to zero replicas when idle. When traffic returns, a buffering proxy holds the request, signals the operator to scale up, and forwards the request once the model reports ready.

## Components

### Operator
- Watches CostSaver and ReplicaGroup CRDs
- Runs the idle detection loop
- Scales deployments up/down
- Exposes Prometheus metrics

### Proxy
- Intercepts incoming traffic
- Buffers requests during cold start
- Signals the operator to scale up

### Agent (sidecar)
- Runs alongside model pods
- Handles model warm-up
- Reports last-request timestamps

## Data Flow

1. User creates a CostSaver CR targeting a Deployment
2. Operator watches the deployment's idle time
3. After idleTimeout seconds with no traffic → scale to 0
4. When traffic arrives at the proxy → signals operator → scale up
5. Proxy forwards the buffered request once the agent reports the model ready (health check + warmup)