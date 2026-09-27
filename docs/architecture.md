# kubbernetd Architecture

## Overview

kubbernetd is a Kubernetes operator that watches deployments and scales them to zero replicas when idle. When traffic returns, it brings them back instantly via a shadow pod technique.

## Components

### Operator
- Watches CostSaver CRDs
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
5. Shadow pod serves instantly while new pods cold start