import structlog
from aiohttp import ClientSession, ClientTimeout, web

log = structlog.get_logger()


class RequestForwarder:
    def __init__(self, upstream_port: int = 8080, timeout_seconds: int = 30):
        self.upstream_port = upstream_port
        self.timeout = ClientTimeout(total=timeout_seconds)

    async def forward(
        self,
        method: str,
        path: str,
        headers: dict,
        body: bytes,
        target_ip: str,
    ) -> web.Response:
        url = f"http://{target_ip}:{self.upstream_port}{path}"
        try:
            async with ClientSession(timeout=self.timeout) as session:
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=body if body else None,
                ) as resp:
                    response_body = await resp.read()
                    log.debug("forwarded request", url=url, status=resp.status)
                    return web.Response(
                        status=resp.status,
                        headers=dict(resp.headers),
                        body=response_body,
                    )
        except Exception as e:
            log.warning("forward failed", url=url, error=str(e))
            return web.Response(status=502, text=f"upstream error: {e}")