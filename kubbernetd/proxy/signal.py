import structlog
from kubernetes import client

log = structlog.get_logger()


class ScaleSignaler:
    def __init__(self):
        self.apps_api = client.AppsV1Api()

    async def request_scale_up(self, namespace: str, deployment: str):
        log.info("signaling scale-up", namespace=namespace, deployment=deployment)
        body = {"spec": {"replicas": 1}}
        self.apps_api.patch_namespaced_deployment_scale(
            name=deployment,
            namespace=namespace,
            body=body,
        )