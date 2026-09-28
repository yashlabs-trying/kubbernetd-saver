import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
from kubbernetd.agent.engine_adapter import EngineAdapter, EngineStage
from kubbernetd.agent.reporter import StatusReporter


class FakeReporter:
    def __init__(self):
        self.annotations = {}

    def report_stage(self, key: str, value: str):
        self.annotations[key] = value


@pytest.mark.anyio
async def test_engine_adapter_reports_stages():
    reporter = FakeReporter()
    adapter = EngineAdapter(reporter, upstream_port=8080)
    assert adapter.stage == EngineStage.STARTING

    asyncio.create_task(adapter.run_progressive_checks())
    await asyncio.sleep(0.5)
    assert "engine-status" in reporter.annotations
    assert reporter.annotations["engine-status"] in EngineStage.STAGES


@pytest.mark.anyio
async def test_warmup_probe_fails_on_refusal():
    reporter = FakeReporter()
    adapter = EngineAdapter(reporter, upstream_port=18080)
    adapter._probe_timeout = 2.0
    result = await adapter._run_warmup_probe()
    assert result is False


def test_engine_stages_order():
    reporter = FakeReporter()
    adapter = EngineAdapter(reporter)
    assert EngineStage.STAGES == [
        "starting", "loading_weights", "cuda_init",
        "nccl_init", "engine_init", "warming", "ready",
    ]