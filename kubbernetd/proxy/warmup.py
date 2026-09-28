import aiohttp
import structlog

log = structlog.get_logger()


async def probe_model_readiness(host: str, port: int = 8080, timeout: float = 30.0) -> bool:
    probe_payload = {
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
        "stream": False,
    }
    url = f"http://{host}:{port}/v1/chat/completions"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=probe_payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 200:
                    log.info("model readiness probe passed", url=url)
                    return True
                body = await resp.text()
                log.warning("model readiness probe failed", url=url, status=resp.status, body=body[:200])
                return False
    except (aiohttp.ClientError, TimeoutError, ConnectionError) as e:
        log.warning("model readiness probe connection failed", url=url, error=str(e))
        return False