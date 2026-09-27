# Quickstart

## Prerequisites

- Python 3.10+
- Kubernetes cluster
- kubectl configured

## Install

```bash
pip install kubbernetd

# Install the operator into your cluster
kubbernetd install --namespace kubbernetd
```

## Enable cost-saving on a deployment

```bash
kubbernetd watch deployment/my-model --idle-timeout 5m
```

## Verify

```bash
kubectl get costsavers
```