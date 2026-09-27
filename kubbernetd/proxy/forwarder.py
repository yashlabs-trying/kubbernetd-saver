import structlog
from aiohttp import ClientSession, ClientTimeout, web

log = structlog.get_logger()


class RequestForwarder:
    def __init__(self, upstream_port: int = 8080, timeout_seconds: int = 300):
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
                    resp_headers = dict(resp.headers)
                    resp_headers.pop("Transfer-Encoding", None)
                    return web.Response(
                        status=resp.status,
                        headers=resp_headers,
                        body=response_body,
                    )
        except Exception as e:
            log.warning("forward failed", url=url, error=str(e))
            return web.Response(status=502, text=f"upstream error: {e}")

    async def forward_streaming(self, request: web.Request, target_ip: str) -> web.StreamResponse:
        path = request.path_qs or request.path
        url = f"http://{target_ip}:{self.upstream_port}{path}"
        body = getattr(request, "_cached_body", None)
        if body is None:
            try:
                body = await request.read()
            except Exception:
                body = b""

        try:
            async with ClientSession(timeout=self.timeout) as session:
                async with session.request(
                    method=request.method,
                    url=url,
                    headers=dict(request.headers),
                    data=body if body else None,
                ) as resp:
                    response = web.StreamResponse(
                        status=resp.status,
                        headers=dict(resp.headers),
                    )
                    await response.prepare(request)
                    async for chunk in resp.content.iter_chunked(8192):
                        await response.write(chunk)
                    await response.write_eof()
                    return response
        except Exception as e:
            log.warning("streaming forward failed", url=url, error=str(e))
            return web.Response(status=502, text=f"upstream error: {e}")