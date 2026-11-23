# Tesseract Ignite — Risk Register

## Bugs Discovered and Fixed

| ID | Severity | Subsystem | Description | Fix |
|---|---|---|---|---|
| BUG-001 | Critical | CLI, Agent | `config.load_incluster_client()` doesn't exist. Wrong method name in 5 files. | Changed to `load_incluster_config()` |
| BUG-002 | Critical | CRD | `bootstrap.cpuRAM` default `0` is int but schema type is string → CRD install fails | Changed default to `"0"` |
| BUG-003 | Critical | Proxy | `TCPConnector` created in `__init__` before event loop is running → RuntimeError | Lazy initialization in `_get_session()` |
| BUG-004 | Critical | Operator | `KUBERNETD_PROXY_PORT` env var collides with Kubernetes service env var (`tcp://ip:port`) → operator crash loop | Renamed to `KUBERNETD_PROXY_LISTEN_PORT` |
| BUG-005 | Critical | Controller | RUNNING→SLEEPING transition missing from TRANSITIONS table. Groups with 0 workers get stuck in RUNNING, never processing wake signals | Added RUNNING→SLEEPING; wake annotation check in `_handle_running` |
| BUG-006 | Medium | Controller | `wake_started_at` never initialized → `lastWakeDuration` would be wildly incorrect | Set in `_handle_sleeping` |
| BUG-007 | Medium | Controller | `error_count` never reset on successful wake → progressive backoff accumulates across cycles | Reset in `_handle_warming` |
| BUG-008 | High | Controller | `should_scale_up` used `idle_seconds < timeout` instead of `in_flight > 0` → could miss wake triggers | Changed to check `in_flight > 0` |
| BUG-009 | Medium | Dashboard | `spec.target` should be `spec.targetRef` → dashboard always showed "unknown" name | Field name fix |
| BUG-010 | Medium | E2E Helper | `sys.argv[1]` takes precedence over `E2E_HELPER_MODE` env var → can't configure mode via env | Changed precedence: env var first |
| BUG-011 | Low | RBAC | Missing `watch` permission on `customresourcedefinitions` → kopf watch degraded | Added `watch` verb |
| BUG-012 | Low | Proxy | Blocking k8s API calls in async context → event loop blocked | Wrapped in `run_in_executor` |

## Architectural Weaknesses

| ID | Severity | Description |
|---|---|---|
| WEAK-001 | Medium | No leader election for operator. Multiple replicas could conflict. |
| WEAK-002 | Medium | Tick loop runs in a daemon thread. If API call hangs, entire reconciliation blocks. |
| WEAK-003 | Low | Wake annotation polling (1s interval in proxy) creates API server load during cold starts. |
| WEAK-004 | Low | No request ID correlation across proxy/operator/agent logs. |
| WEAK-005 | Low | No finalizer on ReplicaGroup CRD. Resource cleanup relies on operator being alive. |
| WEAK-006 | Low | Operator watches all namespaces with cluster-wide scope. No namespace filtering. |

## Resource Constraints (Mac M5)

| Item | Value |
|---|---|
| RAM | 16 GB |
| CPUs | 10 |
| Free disk | ~360 GB |
| Container runtime | Colima VM (4 CPU, 6 GB RAM) |
| Max concurrent requests | 25 verified stable; 100 caused OOM |

## Test Coverage Gaps

| Gap | Risk |
|---|---|
| No streaming response E2E test | Streaming may have undiscovered bugs |
| No leader election test | Multi-replica operator not validated |
| No NetworkPolicy tests | CNI enforcement not verified |
| No real GPU engine integration | Cold-start timing numbers are synthetic |
| No multi-cluster tests | Cross-cluster routing not validated |
