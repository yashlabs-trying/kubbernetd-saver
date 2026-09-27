import structlog

log = structlog.get_logger()


class RequestForwarder:
    async def forward(self, request_body: bytes, target_url: str) -> bytes:
        log.info("forwarding request", target=target_url)
        return b"ok"