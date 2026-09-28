import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
from kubbernetd.proxy.warmup import probe_model_readiness


@pytest.mark.anyio
async def test_probe_refused_connection():
    result = await probe_model_readiness("127.0.0.1", 18080, timeout=2.0)
    assert result is False


@pytest.mark.anyio
async def test_probe_timeout():
    result = await probe_model_readiness("10.0.0.1", 8080, timeout=0.1)
    assert result is False