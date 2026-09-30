# E2E Test Helper

Single Docker image that simulates various model-server behaviors for CI testing.

## Modes

| Mode | Command | Behavior |
|------|---------|----------|
| normal | `python server.py normal` | Immediate 200 on `/` and `/readiness` |
| slow-start | `python server.py slow-start` | `/readiness` returns 503 for `$READINESS_DELAY` seconds (default 15), then 200 |
| long-request | `python server.py long-request` | `/work?seconds=N` keeps the connection open for N seconds, then returns 200 |
| stream | `python server.py stream` | `/stream?seconds=N&interval=M` sends chunks every M seconds for N seconds |
| all | `python server.py all` | All endpoints available |

## Build

```bash
docker build -t kubbernetd/e2e-helper:ci .
```
