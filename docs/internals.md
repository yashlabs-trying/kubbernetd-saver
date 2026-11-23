# Internals

## Idle Detection

The operator maintains an in-memory map of last-request timestamps per (namespace, deployment). On each tick (every `checkInterval` seconds), it checks if `now - lastRequest > idleTimeout`. If so, it scales the deployment to 0.

## Scale-to-Zero

When the operator decides to scale down, it patches the Deployment's `spec.replicas` to 0 via the Kubernetes API. The Service and Endpoints remain intact — they just point to nothing.

## Warm standby ("shadow") pods — planned

The `shadowPods` field is accepted by the CRD and stored by the operator, but is
not acted on yet. The design: keep N hidden ready pods outside the Service
selector and swap one in on wake-up, so the first request does not wait for a
full cold start. Until then, wake-up latency is the full cold start, measured
stage by stage with `deploy/cold-ttft-benchmark.sh`.

## Request Buffering

The proxy holds incoming requests in an in-memory queue while the deployment is scaling up. Once the readiness probe passes, it drains the queue to the new pod.