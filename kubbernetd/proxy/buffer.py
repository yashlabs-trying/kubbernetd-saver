import asyncio
import time
import structlog
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from aiohttp import web

log = structlog.get_logger()


@dataclass
class WaitingEntry:
    request_data: Optional[web.Request] = None
    request_body: bytes = b""
    created_at: float = field(default_factory=time.monotonic)


class RequestBuffer:
    def __init__(self, max_waiters: int = 256, request_ttl: float = 30.0):
        self._max_waiters = max_waiters
        self._request_ttl = request_ttl
        self._waiters: dict[tuple[str, str], list[tuple[asyncio.Future, WaitingEntry]]] = defaultdict(list)
        self._pending_scale: set[tuple[str, str]] = set()
        self._request_store: dict[tuple[str, str], tuple] = {}

    def add_waiter(self, namespace: str, service: str, future: asyncio.Future):
        key = (namespace, service)
        if len(self._waiters[key]) >= self._max_waiters:
            future.set_exception(Exception("too many waiters"))
            return
        self._waiters[key].append((future, WaitingEntry()))

    def store_request_data(self, namespace: str, service: str, request: web.Request, body: bytes):
        key = (namespace, service)
        self._request_store[key] = (request, body)

    def needs_scale_signal(self, namespace: str, service: str) -> bool:
        key = (namespace, service)
        if key in self._pending_scale:
            return False
        self._pending_scale.add(key)
        return True

    def mark_scaled(self, namespace: str, service: str):
        self._pending_scale.discard((namespace, service))

    def pop_waiters(self, namespace: str, service: str) -> list[tuple]:
        key = (namespace, service)
        entries = self._waiters.pop(key, [])
        stored = self._request_store.pop(key, None)
        results = []
        for future, entry in entries:
            if stored:
                req, body = stored
                req._cached_body = body
                results.append((req, future))
            else:
                results.append((entry.request_data, future))
        self._pending_scale.discard(key)
        return results

    def waiter_count(self, namespace: str, service: str) -> int:
        return len(self._waiters.get((namespace, service), []))

    def cleanup_expired(self) -> int:
        now = time.monotonic()
        total = 0
        expired_keys = []
        for key, entries in list(self._waiters.items()):
            alive = []
            for future, entry in entries:
                if entry.created_at and now - entry.created_at > self._request_ttl:
                    if not future.done():
                        future.set_exception(Exception("request expired"))
                    total += 1
                else:
                    alive.append((future, entry))
            if alive:
                self._waiters[key] = alive
            else:
                expired_keys.append(key)
        for key in expired_keys:
            self._waiters.pop(key, None)
            self._request_store.pop(key, None)
            self._pending_scale.discard(key)
        return total