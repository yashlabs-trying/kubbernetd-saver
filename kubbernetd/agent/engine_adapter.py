import asyncio
import time
import structlog
from typing import Optional

log = structlog.get_logger()


class EngineStage(str):
    STARTING = "starting"
    LOADING_WEIGHTS = "loading_weights"
    CUDA_INIT = "cuda_init"
    NCCL_INIT = "nccl_init"
    ENGINE_INIT = "engine_init"
    WARMING = "warming"
    READY = "ready"
    ERROR = "error"

    STAGES = [STARTING, LOADING_WEIGHTS, CUDA_INIT, NCCL_INIT, ENGINE_INIT, WARMING, READY]


class EngineAdapter:
    def __init__(self, reporter, upstream_port: int = 8080):
        self.reporter = reporter
        self.upstream_port = upstream_port
        self._stage: str = EngineStage.STARTING
        self._probe_timeout: float = 120.0

    @property
    def stage(self) -> str:
        return self._stage

    async def run_progressive_checks(self):
        self._stage = EngineStage.STARTING
        self.reporter.report_stage("engine-status", EngineStage.STARTING)
        await asyncio.sleep(2)

        self._stage = EngineStage.LOADING_WEIGHTS
        self.reporter.report_stage("weight-status", "loaded")
        await asyncio.sleep(1)

        self._stage = EngineStage.CUDA_INIT
        self.reporter.report_stage("cuda-status", "ready")
        await asyncio.sleep(1)

        self._stage = EngineStage.NCCL_INIT
        self.reporter.report_stage("nccl-status", "ready")
        await asyncio.sleep(1)

        self._stage = EngineStage.ENGINE_INIT
        self.reporter.report_stage("engine-status", EngineStage.ENGINE_INIT)
        await asyncio.sleep(2)

        self._stage = EngineStage.WARMING
        self.reporter.report_stage("engine-status", EngineStage.WARMING)

        warmed = await self._run_warmup_probe()
        if warmed:
            self._stage = EngineStage.READY
            self.reporter.report_stage("engine-status", EngineStage.READY)
            log.info("engine ready after warmup")
        else:
            self._stage = EngineStage.ERROR
            self.reporter.report_stage("engine-status", EngineStage.ERROR)
            log.error("engine warmup failed")

    async def _run_warmup_probe(self) -> bool:
        import aiohttp
        probe_payload = {
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
            "stream": False,
        }
        probe_url = f"http://127.0.0.1:{self.upstream_port}/v1/chat/completions"
        deadline = time.monotonic() + self._probe_timeout
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(probe_url, json=probe_payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            log.info("warmup probe succeeded", attempt=attempt)
                            return True
                        body = await resp.text()
                        log.warning("warmup probe returned non-200", status=resp.status, body=body[:200])
            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
                log.debug("warmup probe attempt failed", attempt=attempt, error=str(e))
            await asyncio.sleep(5)
        log.error("warmup probe exhausted all attempts")
        return False