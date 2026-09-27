import time
from collections import defaultdict
from threading import Lock
from typing import Optional

from kubbernetd.common.config import OperatorConfig


class IdleDetector:
    def __init__(self, config: OperatorConfig):
        self.config = config
        self._last_request: dict[tuple[str, str], float] = {}
        self._lock = Lock()

    def watch(self, namespace: str, name: str):
        pass

    def unwatch(self, namespace: str, name: str):
        with self._lock:
            self._last_request.pop((namespace, name), None)

    def touch(self, namespace: str, name: str):
        with self._lock:
            self._last_request[(namespace, name)] = time.time()

    def idle_seconds(self, namespace: str, name: str) -> Optional[float]:
        with self._lock:
            last = self._last_request.get((namespace, name))
        if last is None:
            return None
        return time.time() - last