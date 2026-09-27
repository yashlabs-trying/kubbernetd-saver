import structlog
from aiohttp import web

from kubbernetd.proxy.buffer import RequestBuffer
from kubbernetd.proxy.signal import ScaleSignaler

log = structlog.get_logger()


class ProxyServer:
    def __init__(self, buffer: RequestBuffer, signaler: ScaleSignaler):
        self.buffer = buffer
        self.signaler = signaler
        self.app = web.Application()
        self.app.router.add_route("*", "/{tail:.*}", self.handle_request)

    async def handle_request(self, request: web.Request) -> web.Response:
        service = request.headers.get("X-Kubbernetd-Service", "unknown")
        namespace = request.headers.get("X-Kubbernetd-Namespace", "default")

        if not self.buffer.is_ready(service):
            await self.signaler.request_scale_up(namespace, service)
            response = await self.buffer.buffer_request(request)
            return response

        return await self.buffer.forward_request(request)

    def run(self, host: str = "0.0.0.0", port: int = 8080):
        web.run_app(self.app, host=host, port=port)


def main():
    buffer = RequestBuffer()
    signaler = ScaleSignaler()
    server = ProxyServer(buffer, signaler)
    server.run()