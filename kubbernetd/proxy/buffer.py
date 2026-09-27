import asyncio
from collections import defaultdict

from aiohttp import web


class RequestBuffer:
    def __init__(self):
        self._ready: dict[str, bool] = defaultdict(bool)
        self._pending: dict[str, list[web.Request]] = defaultdict(list)

    def is_ready(self, service: str) -> bool:
        return self._ready.get(service, False)

    def mark_ready(self, service: str):
        self._ready[service] = True

    async def buffer_request(self, request: web.Request) -> web.Response:
        self._pending[request.headers.get("X-Kubbernetd-Service", "unknown")].append(request)
        return web.Response(status=202, text="queued")

    async def forward_request(self, request: web.Request) -> web.Response:
        raise NotImplementedError