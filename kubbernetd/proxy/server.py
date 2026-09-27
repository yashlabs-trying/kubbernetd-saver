import asyncio
import structlog
from aiohttp import web, ClientSession, ClientTimeout

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
        self._draining: set[tuple[str, str]] = set()

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
                return await self.forwarder.forward_streaming(
                    request=request,
                    target_ip=ips[0],
                )

        return await self._wait_for_upstream(request, namespace, service)

    async def _wait_for_upstream(
        self, request: web.Request, namespace: str, service: str
    ) -> web.Response:
        key = (namespace, service)

        result_future = asyncio.get_event_loop().create_future()
        self.buffer.add_waiter(namespace, service, result_future)

        should_signal = self.buffer.needs_scale_signal(namespace, service)
        if should_signal and key not in self._draining:
            self._draining.add(key)
            asyncio.create_task(self._drain_waiter(namespace, service))

        body = await self._read_body(request)
        self.buffer.store_request_data(namespace, service, request, body)

        try:
            response = await asyncio.wait_for(result_future, timeout=30.0)
            return response
        except asyncio.TimeoutError:
            log.warning("upstream wait timeout", service=service, namespace=namespace)
            return web.Response(status=504, text="upstream did not become ready in time")

    async def _drain_waiter(self, namespace: str, service: str):
        try:
            ready = await self.signaler.ensure_ready(namespace, service)
            if ready:
                ips = self.discovery.resolve(namespace, service)
                if ips:
                    requests_data = self.buffer.pop_waiters(namespace, service)
                    for req_data, future in requests_data:
                        if not future.done():
                            resp = await self.forwarder.forward_streaming(
                                request=req_data,
                                target_ip=ips[0],
                            )
                            future.set_result(resp)
                    log.info("drained waiters", service=service, count=len(requests_data))
                else:
                    self._fail_waiters(namespace, service, "no endpoints after scale-up")
            else:
                self._fail_waiters(namespace, service, "scale-up timed out")
        except Exception as e:
            log.exception("drain failed", service=service, error=str(e))
            self._fail_waiters(namespace, service, f"drain error: {e}")
        finally:
            self._draining.discard((namespace, service))
            self.buffer.mark_scaled(namespace, service)

    def _fail_waiters(self, namespace: str, service: str, reason: str):
        entries = self.buffer.pop_waiters(namespace, service)
        for _, future in entries:
            if not future.done():
                future.set_exception(Exception(reason))
        log.warning("failed waiters", service=service, count=len(entries), reason=reason)

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