import asyncio
import structlog
from aiohttp import web

from kubbernetd.proxy.buffer import RequestBuffer
from kubbernetd.proxy.forwarder import RequestForwarder
from kubbernetd.proxy.signal import ScaleSignaler
from kubbernetd.proxy.discovery import ServiceDiscovery

log = structlog.get_logger()


class ProxyServer:
    def __init__(
        self,
        buffer: RequestBuffer,
        forwarder: RequestForwarder,
        signaler: ScaleSignaler,
        discovery: ServiceDiscovery,
        cleanup_interval: int = 60,
    ):
        self.buffer = buffer
        self.forwarder = forwarder
        self.signaler = signaler
        self.discovery = discovery
        self.cleanup_interval = cleanup_interval
        self.app = web.Application()
        self.app.router.add_route("*", "/{tail:.*}", self.handle_request)

    async def start_background_tasks(self):
        asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(self.cleanup_interval)
            expired = self.buffer.cleanup_expired()
            if expired:
                log.info("cleaned up expired buffered requests", count=expired)

    async def handle_request(self, request: web.Request) -> web.Response:
        namespace = request.headers.get("X-Kubbernetd-Namespace", "default")
        service = request.headers.get("X-Kubbernetd-Service", "")

        if not service:
            return web.Response(status=400, text="missing X-Kubbernetd-Service header")

        if self.discovery.has_ready_pods(namespace, service):
            ips = self.discovery.resolve(namespace, service)
            if ips:
                return await self.forwarder.forward(
                    method=request.method,
                    path=request.path_qs or request.path,
                    headers=dict(request.headers),
                    body=await self._read_body(request),
                    target_ip=ips[0],
                )

        queued = self.buffer.buffer(namespace, service, request)
        if queued.status != 202:
            return queued

        if self.buffer.needs_scale_signal(namespace, service):
            asyncio.create_task(self._drain_after_scale(namespace, service))

        return queued

    async def _drain_after_scale(self, namespace: str, service: str):
        try:
            ready = await self.signaler.ensure_ready(namespace, service)
            if ready:
                entries = self.buffer.pop_ready(namespace, service)
                ips = self.discovery.resolve(namespace, service)
                if ips:
                    for entry in entries:
                        entry.response = await self.forwarder.forward(
                            method=entry.method,
                            path=entry.path,
                            headers=entry.headers,
                            body=entry.body,
                            target_ip=ips[0],
                        )
                    log.info("drained buffered requests", service=service, count=len(entries))
                else:
                    log.warning("no endpoints after scale-up", service=service)
            else:
                self.buffer.mark_scaled(namespace, service)
        except Exception as e:
            log.exception("drain failed", service=service, namespace=namespace, error=str(e))
            self.buffer.mark_scaled(namespace, service)

    async def _read_body(self, request: web.Request) -> bytes:
        try:
            return await request.read()
        except Exception:
            return b""


def main():
    discovery = ServiceDiscovery()
    buffer = RequestBuffer()
    forwarder = RequestForwarder()
    signaler = ScaleSignaler(discovery)
    server = ProxyServer(buffer, forwarder, signaler, discovery)
    app = server.app

    async def on_startup(app):
        await server.start_background_tasks()

    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()