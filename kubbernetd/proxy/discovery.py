import time
import structlog
from threading import Lock
from typing import Optional

from kubernetes import client

log = structlog.get_logger()


class ServiceDiscovery:
    def __init__(self):
        self.core_api = client.CoreV1Api()
        self._cache: dict[tuple[str, str], tuple[list[str], float]] = {}
        self._lock = Lock()
        self._cache_ttl = 5

    def resolve(self, namespace: str, name: str) -> list[str]:
        cached = self._from_cache(namespace, name)
        if cached is not None:
            return cached
        return self._fetch(namespace, name)

    def _from_cache(self, namespace: str, name: str) -> Optional[list[str]]:
        with self._lock:
            entry = self._cache.get((namespace, name))
            if entry is None:
                return None
            ips, ts = entry
            if time.monotonic() - ts > self._cache_ttl:
                return None
            return ips

    def _fetch(self, namespace: str, name: str) -> list[str]:
        try:
            ep = self.core_api.read_namespaced_endpoints(name=name, namespace=namespace)
            ips = []
            for subset in ep.subsets or []:
                for addr in subset.addresses or []:
                    if addr.ip:
                        ips.append(addr.ip)
            with self._lock:
                self._cache[(namespace, name)] = (ips, time.monotonic())
            return ips
        except client.exceptions.ApiException as e:
            if e.status == 404:
                log.warning("service not found", name=name, namespace=namespace)
                return []
            log.warning("failed to fetch endpoints", name=name, namespace=namespace, error=str(e))
            return []
        except Exception as e:
            log.warning("unexpected error resolving service", error=str(e))
            return []

    def has_ready_pods(self, namespace: str, name: str) -> bool:
        ips = self.resolve(namespace, name)
        return len(ips) > 0

    def clear_cache(self, namespace: Optional[str] = None, name: Optional[str] = None):
        with self._lock:
            if namespace and name:
                self._cache.pop((namespace, name), None)
            elif namespace:
                self._cache = {k: v for k, v in self._cache.items() if k[0] != namespace}
            else:
                self._cache.clear()