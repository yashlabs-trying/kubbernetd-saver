import asyncio
import structlog
from kubernetes import client

from kubbernetd.proxy.discovery import ServiceDiscovery

log = structlog.get_logger()


class ScaleSignaler:
    def __init__(self, discovery: ServiceDiscovery):
        self.apps_api = client.AppsV1Api()
        self.discovery = discovery
        self._poll_interval = 1.0

    async def ensure_ready(self, namespace: str, deployment: str, timeout: float = 30.0) -> bool:
        self._signal_scale_up(namespace, deployment)
        return await self._wait_for_endpoints(namespace, deployment, timeout)

    def _signal_scale_up(self, namespace: str, deployment: str):
        try:
            body = {"spec": {"replicas": 1}}
            self.apps_api.patch_namespaced_deployment_scale(
                name=deployment,
                namespace=namespace,
                body=body,
            )
            self.discovery.clear_cache(namespace, deployment)
            log.info("signaled scale-up", namespace=namespace, deployment=deployment)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                log.warning("deployment not found for scale-up", namespace=namespace, deployment=deployment)
            else:
                log.warning("scale-up signal failed", namespace=namespace, deployment=deployment, error=str(e))
        except Exception as e:
            log.warning("scale-up signal failed unexpectedly", error=str(e))

    async def _wait_for_endpoints(self, namespace: str, service: str, timeout: float) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if self.discovery.has_ready_pods(namespace, service):
                log.info("endpoints ready", namespace=namespace, service=service)
                return True
            await asyncio.sleep(self._poll_interval)
        log.warning("endpoints not ready within timeout", namespace=namespace, service=service, timeout=timeout)
        return False