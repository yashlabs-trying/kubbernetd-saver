import structlog
from kubernetes import client

log = structlog.get_logger()


class TargetAuthorizer:
    def __init__(self):
        self.custom_api = client.CustomObjectsApi()

    async def authorize(self, namespace: str, service: str) -> bool:
        try:
            self.custom_api.get_namespaced_custom_object(
                group="kubbernetd.io", version="v1",
                namespace=namespace, plural="replicagroups",
                name=service,
            )
            return True
        except client.exceptions.ApiException as e:
            if e.status == 404:
                log.warning("unauthorized target - no ReplicaGroup found", service=service, namespace=namespace)
                return False
            log.warning("auth check failed", service=service, error=str(e))
            return False
        except Exception as e:
            log.warning("auth check failed unexpectedly", error=str(e))
            return False