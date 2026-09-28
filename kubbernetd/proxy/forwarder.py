import structlog
from aiohttp import ClientSession, ClientTimeout, TCPConnector, web

log = structlog.get_logger()


class RequestForwarder:
    def __init__(self, upstream_port: int = 8080, timeout_seconds: int = 300, max_connections: int = 100):
        self.upstream_port = upstream_port
        connector = TCPConnector(limit=max_connections, limit_per_host=10, enable_cleanup_closed=True, ttl_dns_cache=300)
        self._session = ClientSession(
            timeout=ClientTimeout(total=timeout_seconds),
            connector=connector,
        )
        self._owns_session = True

    async def close(self):
        if self._owns_session:
            await self._session.close()

    async def forward_streaming(self, request: web.Request, target_ip: str) -> web.StreamResponse:
        path = request.path_qs or request.path
        url = f"http://{target_ip}:{self.upstream_port}{path}"
        body = getattr(request, "_cached_body", None)
        if body is None:
            try:
                body = await request.read()
            except Exception:
                body = b""
        headers = dict(request.headers)
        headers.pop("X-Kubbernetd-Namespace", None)
        headers.pop("X-Kubbernetd-Service", None)
        try:
            async with self._session.request(
                method=request.method,
                url=url,
                headers=headers,
                data=body if body else None,
            ) as resp:
                response = web.StreamResponse(
                    status=resp.status,
                    headers=dict(resp.headers),
                )
                response.content_type = resp.content_type or ""
                await response.prepare(request)
                async for chunk in resp.content.iter_chunked(65536):
                    if request.transport is None or request.transport.is_closing():
                        log.debug("client disconnected, stopping forward", url=url)
                        break
                    await response.write(chunk)
                await response.write_eof()
                return response
        except Exception as e:
            log.warning("streaming forward failed", url=url, error=str(e))
            return web.Response(status=502, text=f"upstream error: {e}")