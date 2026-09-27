# Internals

## Idle Detection

The operator maintains an in-memory map of last-request timestamps per (namespace, deployment). On each tick (every `checkInterval` seconds), it checks if `now - lastRequest > idleTimeout`. If so, it scales the deployment to 0.

## Scale-to-Zero

When the operator decides to scale down, it patches the Deployment's `spec.replicas` to 0 via the Kubernetes API. The Service and Endpoints remain intact — they just point to nothing.

## Shadow Pod Instant Cold Start

When a deployment has `shadowPods > 0`, the operator keeps that many hidden pods running (not in the Service's selector). On scale-up, it swaps the shadow pod into the selector first, then spins up the rest. This gives near-instant cold starts.

## Request Buffering

The proxy holds incoming requests in an in-memory queue while the deployment is scaling up. Once the readiness probe passes, it drains the queue to the new pod.