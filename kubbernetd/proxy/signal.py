import asyncio
import structlog
from kubernetes import client

from kubbernetd.proxy.discovery import EndpointDiscovery

log = structlog.get_logger()


class GroupSignaler:
    def __init__(self, discovery: EndpointDiscovery):
        self.apps_api = client.AppsV1Api()
        self.custom_api = client.CustomObjectsApi()
        self.discovery = discovery
        self._poll_interval = 1.0

    async def ensure_ready(self, namespace: str, group: str, timeout: float = 120.0) -> bool:
        ready_before = self.discovery.has_ready_pods(namespace, group)
        if ready_before:
            return True
        self._signal_wake(namespace, group)
        return await self._wait_for_readiness(namespace, group, timeout)

    def _signal_wake(self, namespace: str, group: str):
        try:
            rg = self.custom_api.get_namespaced_custom_object(
                group="kubbernetd.io", version="v1",
                namespace=namespace, plural="replicagroups",
                name=group,
            )
            spec = rg.get("spec", {})
            target = spec.get("targetRef", {})
            deployment_name = target.get("name", group)

            dep = self.apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
            current = dep.spec.replicas or 0
            if current > 0:
                log.info("deployment already scaling", group=group, replicas=current)
                return

            body = {"spec": {"replicas": spec.get("model", {}).get("workers", 1)}}
            self.apps_api.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=namespace,
                body=body,
            )
            self.discovery.clear_cache(namespace, group)
            log.info("signaled wake for replicagroup", group=group, namespace=namespace)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                log.warning("replicagroup or deployment not found", group=group, error=str(e))
            else:
                log.warning("wake signal failed", group=group, error=str(e))
        except Exception as e:
            log.warning("wake signal failed unexpectedly", group=group, error=str(e))

    async def _wait_for_readiness(self, namespace: str, group: str, timeout: float) -> bool:
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
            if self.discovery.has_ready_pods(namespace, group):
                return True
            await asyncio.sleep(self._poll_interval)
        log.warning("replicagroup not ready within timeout", group=group, timeout=timeout)
        return False