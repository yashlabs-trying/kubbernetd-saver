import asyncio
import time
import structlog
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from aiohttp import web

log = structlog.get_logger()


@dataclass
class BufferedRequest:
    method: str
    path: str
    headers: dict
    body: bytes
    created_at: float = field(default_factory=time.monotonic)
    response: web.Response = field(default_factory=lambda: web.Response(status=504, text="upstream timeout"))

    def is_expired(self, ttl: float) -> bool:
        return time.monotonic() - self.created_at > ttl


class RequestBuffer:
    def __init__(self, max_buffer_size: int = 256, request_ttl: float = 30.0):
        self._max_buffer_size = max_buffer_size
        self._request_ttl = request_ttl
        self._queues: dict[tuple[str, str], list[BufferedRequest]] = defaultdict(list)
        self._pending_scale: set[tuple[str, str]] = set()

    def buffer(self, namespace: str, service: str, request: web.Request) -> web.Response:
        key = (namespace, service)
        queue = self._queues[key]

        if len(queue) >= self._max_buffer_size:
            log.warning("buffer full, rejecting request", service=service, namespace=namespace)
            return web.Response(status=503, text="buffer full — too many queued requests")

        body = request.body
        if isinstance(body, (asyncio.StreamReader,)):
            body = b""

        entry = BufferedRequest(
            method=request.method,
            path=request.path_qs or request.path,
            headers=dict(request.headers),
            body=body,
        )
        queue.append(entry)
        log.debug("request buffered", service=service, namespace=namespace, queue_size=len(queue))
        return web.Response(status=202, text="queued")

    def needs_scale_signal(self, namespace: str, service: str) -> bool:
        key = (namespace, service)
        if key in self._pending_scale:
            return False
        self._pending_scale.add(key)
        return True

    def mark_scaled(self, namespace: str, service: str):
        self._pending_scale.discard((namespace, service))

    def pop_ready(self, namespace: str, service: str) -> list[BufferedRequest]:
        key = (namespace, service)
        queue = self._queues.pop(key, [])
        self._pending_scale.discard(key)
        return queue

    def queue_size(self, namespace: str, service: str) -> int:
        return len(self._queues.get((namespace, service), []))

    def cleanup_expired(self) -> int:
        now = time.monotonic()
        total = 0
        expired_keys = []
        for key, queue in list(self._queues.items()):
            alive = [r for r in queue if not r.is_expired(self._request_ttl)]
            expired_count = len(queue) - len(alive)
            total += expired_count
            if alive:
                self._queues[key] = alive
            else:
                expired_keys.append(key)
        for key in expired_keys:
            self._queues.pop(key, None)
            self._pending_scale.discard(key)
        return total