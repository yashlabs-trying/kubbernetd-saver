import os
import sys
import time
from threading import Lock
from typing import Optional

import structlog

from kubbernetd.common.types import OperatorConfig

log = structlog.get_logger()


class IdleDetector:
    def __init__(self, config: OperatorConfig):
        self.config = config
        self._last_request: dict[tuple[str, str], float] = {}
        self._watched: set[tuple[str, str]] = set()
        self._lock = Lock()

        if sys.platform == "win32":
            log.warning(
                "Running on Windows — time.monotonic() is not reliable for production. "
                "Use Linux for production deployments."
            )

    def watch(self, namespace: str, name: str):
        with self._lock:
            self._watched.add((namespace, name))
            self._last_request.setdefault((namespace, name), time.monotonic())
        log.info("started watching", namespace=namespace, deployment=name)

    def unwatch(self, namespace: str, name: str):
        with self._lock:
            self._watched.discard((namespace, name))
            self._last_request.pop((namespace, name), None)
        log.info("stopped watching", namespace=namespace, deployment=name)

    def is_watched(self, namespace: str, name: str) -> bool:
        with self._lock:
            return (namespace, name) in self._watched

    def touch(self, namespace: str, name: str):
        with self._lock:
            self._last_request[(namespace, name)] = time.monotonic()

    def idle_seconds(self, namespace: str, name: str) -> Optional[float]:
        with self._lock:
            last = self._last_request.get((namespace, name))
            if last is None or (namespace, name) not in self._watched:
                return None
        return time.monotonic() - last

    def all_idle(self) -> list[tuple[str, str, float]]:
        result = []
        now = time.monotonic()
        with self._lock:
            for ns, name in list(self._watched):
                last = self._last_request.get((ns, name))
                if last is not None:
                    result.append((ns, name, now - last))
        return result

    def cleanup_stale(self, max_age_seconds: float = 86400):
        now = time.monotonic()
        removed = 0
        with self._lock:
            stale = [
                k for k, v in self._last_request.items()
                if now - v > max_age_seconds and k not in self._watched
            ]
            for k in stale:
                del self._last_request[k]
                removed += 1
        if removed:
            log.debug("cleaned up stale entries", count=removed)