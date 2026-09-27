import structlog
from kubernetes import client

log = structlog.get_logger()


class Scaler:
    def __init__(self, apps_api: client.AppsV1Api):
        self.apps_api = apps_api

    def scale_to(self, namespace: str, name: str, replicas: int):
        body = {"spec": {"replicas": replicas}}
        self.apps_api.patch_namespaced_deployment_scale(
            name=name,
            namespace=namespace,
            body=body,
        )
        log.info("scaled deployment", name=name, namespace=namespace, replicas=replicas)

    def current_replicas(self, namespace: str, name: str) -> int:
        dep = self.apps_api.read_namespaced_deployment(name=name, namespace=namespace)
        if dep.spec.replicas is None:
            return 1
        return dep.spec.replicas