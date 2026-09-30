import asyncio
import structlog
from kubernetes import client

from kubbernetd.proxy.discovery import EndpointDiscovery

log = structlog.get_logger()

WAKE_ANNOTATION = "kubbernetd.io/wake-desired-replicas"


class GroupSignaler:
    def __init__(self, discovery: EndpointDiscovery):
        self.custom_api = client.CustomObjectsApi()
        self.discovery = discovery
        self._poll_interval = 1.0

    async def ensure_ready(self, namespace: str, group: str, target_service: str, timeout: float = 120.0) -> bool:
        ready_before = self.discovery.has_ready_pods(namespace, target_service)
        if ready_before:
            return True
        self._signal_wake(namespace, group, target_service)
        return await self._wait_for_readiness(namespace, group, target_service, timeout)

    def _signal_wake(self, namespace: str, group: str, target_service: str):
        try:
            rg = self.custom_api.get_namespaced_custom_object(
                group="kubbernetd.io", version="v1",
                namespace=namespace, plural="replicagroups",
                name=group,
            )

            annotations = rg.get("metadata", {}).get("annotations", {})
            if annotations.get(WAKE_ANNOTATION):
                log.info("wake already requested for replicagroup", group=group)
                return

            spec = rg.get("spec", {})
            desired = str(spec.get("model", {}).get("workers", 1))

            patch = {
                "metadata": {
                    "annotations": {
                        WAKE_ANNOTATION: desired,
                    }
                }
            }
            self.custom_api.patch_namespaced_custom_object(
                group="kubbernetd.io", version="v1",
                namespace=namespace, plural="replicagroups",
                name=group,
                body=patch,
            )
            self.discovery.clear_cache(namespace, target_service)
            log.info("signaled wake for replicagroup", group=group, namespace=namespace,
                      desired_replicas=desired, target_service=target_service)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                log.warning("replicagroup not found", group=group, error=str(e))
            else:
                log.warning("wake signal failed", group=group, error=str(e))
        except Exception as e:
            log.warning("wake signal failed unexpectedly", group=group, error=str(e))

    async def _wait_for_readiness(self, namespace: str, group: str, target_service: str, timeout: float) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                rg = self.custom_api.get_namespaced_custom_object(
                    group="kubbernetd.io", version="v1",
                    namespace=namespace, plural="replicagroups",
                    name=group,
                )
                status = rg.get("status", {})
                phase = status.get("phase", "UNKNOWN")
                if phase == "RUNNING":
                    log.info("replicagroup ready", group=group, phase=phase)
                    return True
                if phase == "ERROR":
                    log.warning("replicagroup in error state", group=group)
                    return False
            except client.exceptions.ApiException:
                pass
            except Exception as e:
                log.warning("error checking replicagroup status", group=group, error=str(e))
            if self.discovery.has_ready_pods(namespace, target_service):
                return True
            await asyncio.sleep(self._poll_interval)
        log.warning("replicagroup not ready within timeout", group=group, timeout=timeout)
        return False
