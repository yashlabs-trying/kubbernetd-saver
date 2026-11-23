# Quickstart

## Prerequisites

- Python 3.10+
- Kubernetes cluster
- kubectl configured

## Install

```bash
git clone https://github.com/yashlabs-trying/kubbernetd-saver
cd kubbernetd-saver
pip install -e .

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