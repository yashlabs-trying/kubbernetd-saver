import asyncio
import time
import structlog
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

log = structlog.get_logger()


@dataclass
class HoldingEntry:
    created_at: float = field(default_factory=time.monotonic)


class RequestBuffer:
    def __init__(self, max_waiters: int = 256, request_ttl: float = 30.0):
        self._max_waiters = max_waiters
        self._request_ttl = request_ttl
        self._holders: dict[tuple[str, str], list[tuple[asyncio.Future, HoldingEntry]]] = defaultdict(list)
        self._pending_scale: set[tuple[str, str]] = set()
        self._request_store: dict[tuple[str, str], tuple] = {}

    def hold(self, namespace: str, service: str, future: asyncio.Future, request_data: tuple = None) -> bool:
        key = (namespace, service)
        holders = self._holders[key]
        if len(holders) >= self._max_waiters:
            log.warning("max waiters reached, rejecting", service=service, namespace=namespace)
            return False
        holders.append((future, HoldingEntry()))
        if request_data is not None:
            self._request_store[key] = request_data
        return True

    def needs_scale_signal(self, namespace: str, service: str) -> bool:
        key = (namespace, service)
        if key in self._pending_scale:
            return False
        self._pending_scale.add(key)
        return True

    def mark_signaled(self, namespace: str, service: str):
        self._pending_scale.discard((namespace, service))

    def release(self, namespace: str, service: str) -> tuple[list[tuple[asyncio.Future, HoldingEntry]], tuple]:
        key = (namespace, service)
        entries = self._holders.pop(key, [])
        stored = self._request_store.pop(key, None)
        self._pending_scale.discard(key)
        return entries, stored

    def waiter_count(self, namespace: str, service: str) -> int:
        return len(self._holders.get((namespace, service), []))

    def cleanup_expired(self) -> int:
        now = time.monotonic()
        total = 0
        expired_keys = []
        for key, entries in list(self._holders.items()):
            alive = []
            for future, entry in entries:
                if entry.created_at and now - entry.created_at > self._request_ttl:
                    if not future.done():
                        future.set_exception(TimeoutError("request expired while waiting for wake"))
                    total += 1
                else:
                    alive.append((future, entry))
            if alive:
                self._holders[key] = alive
            else:
                expired_keys.append(key)
        for key in expired_keys:
            self._holders.pop(key, None)
            self._pending_scale.discard(key)
        return total