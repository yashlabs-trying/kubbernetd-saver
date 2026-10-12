#!/usr/bin/env python3
from kubernetes import client, config
config.load_kube_config()
apps = client.AppsV1Api()
try:
    result = apps.patch_namespaced_deployment_scale(
        name="test-model", namespace="default",
        body={"spec": {"replicas": 0}},
    )
    print("API call succeeded, replicas:", result.spec.replicas)
except Exception as e:
    print("API call failed:", e)
