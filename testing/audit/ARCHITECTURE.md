# Tesseract Ignite — Architecture Audit

## System Overview

Tesseract Ignite (kubbernetd-saver) is a Kubernetes operator that watches ReplicaGroup CRDs, scales deployments to zero replicas when idle, and wakes them on demand via a proxy.

## Components

### 1. Custom Resource Definition: `replicagroups.kubbernetd.io`

- **Group**: kubbernetd.io/v1
- **Kind**: ReplicaGroup
- **Scope**: Namespaced
- **Status subresource**: enabled

### 2. Operator (`kubbernetd-operator`)

- Entry point: `kubbernetd.operator.main:main`
- Uses kopf framework for CRD event handling
- Tick loop (10s interval) for reconciliation
- State machine: ReplicaGroupController with GroupPhase transitions

### 3. Proxy (`kubbernetd-proxy`)

- Entry point: `kubbernetd.proxy.server:main`
- aiohttp HTTP server on port 8080
- Request buffering, wake signaling, streaming forward
- Active-request annotation on ReplicaGroup CRD

### 4. Agent sidecar (`kubbernetd-agent`)

- Runs alongside inference engines
- Reports status via pod annotations
- Progressive readiness checks (weight loading, CUDA, NCCL, engine init, warmup)

### 5. CLI (`kubbernetd`)

- Typer-based CLI for install, watch, unwatch, dashboard, status

## State Machine (GroupPhase)

```
UNKNOWN → RUNNING / SLEEPING
RUNNING → DRAINING / SLEEPING / ERROR
DRAINING → SCALING_DOWN / RUNNING
SCALING_DOWN → SLEEPING / ERROR
SLEEPING → ALLOCATING / ERROR
ALLOCATING → STARTING / SLEEPING / ERROR
STARTING → LOADING_WEIGHTS / ALLOCATING / ERROR
LOADING_WEIGHTS → INITIALIZING / STARTING / ERROR
INITIALIZING → WARMING / LOADING_WEIGHTS / ERROR
WARMING → RUNNING / INITIALIZING / ERROR
ERROR → SLEEPING / ALLOCATING / ERROR
```

## Data Flow

### Cold Start Path:
1. Client sends request to proxy with X-Kubbernetd-Service header
2. Proxy checks authorization via CRD lookup
3. Proxy sets `kubbernetd.io/active-requests` annotation
4. Proxy discovers no ready endpoints → buffers request
5. Proxy sets `kubbernetd.io/wake-desired-replicas` annotation
6. Operator tick detects annotation → transitions SLEEPING→ALLOCATING
7. Operator scales deployment to workers count
8. Pod starts, agent reports stages via annotations
9. Operator transitions through STARTING→LOADING_WEIGHTS→INITIALIZING→WARMING→RUNNING
10. Proxy detects RUNNING phase → releases buffered requests
11. Client receives response

### Scale-to-Zero Path:
1. Idle timeout reached in RUNNING phase
2. Transitions: RUNNING→DRAINING→SCALING_DOWN→SLEEPING
3. Deployment scaled to 0 replicas

## Key Dependencies

- Python 3.10+
- kopf (Kubernetes operator framework)
- kubernetes Python client
- aiohttp (proxy server)
- typer (CLI)
- prometheus-client (metrics)
- structlog (logging)
- rich (CLI formatting)
