import asyncio
import time
import pytest
from unittest.mock import Mock, patch, AsyncMock
from aiohttp import web
from kubbernetd.proxy.buffer import RequestBuffer


@pytest.fixture
def buffer():
    return RequestBuffer(max_waiters=5, request_ttl=30.0)


class TestBuffer:
    def test_add_waiter(self, buffer):
        future = asyncio.get_event_loop().create_future()
        buffer.add_waiter("default", "test-svc", future)
        assert buffer.waiter_count("default", "test-svc") == 1

    def test_max_waiters_rejects(self, buffer):
        for i in range(5):
            fut = asyncio.get_event_loop().create_future()
            buffer.add_waiter("default", "svc", fut)

        rejected_future = asyncio.get_event_loop().create_future()
        buffer.add_waiter("default", "svc", rejected_future)
        assert rejected_future.done()
        with pytest.raises(Exception, match="too many waiters"):
            rejected_future.result()

    def test_pop_waiters_returns_all(self, buffer):
        fut1 = asyncio.get_event_loop().create_future()
        fut2 = asyncio.get_event_loop().create_future()
        buffer.add_waiter("default", "svc", fut1)
        buffer.add_waiter("default", "svc", fut2)

        entries = buffer.pop_waiters("default", "svc")
        assert len(entries) == 2
        assert buffer.waiter_count("default", "svc") == 0

    def test_needs_scale_signal(self, buffer):
        assert buffer.needs_scale_signal("default", "svc") is True
        assert buffer.needs_scale_signal("default", "svc") is False

    def test_mark_scaled_resets_signal(self, buffer):
        buffer.needs_scale_signal("default", "svc")
        buffer.mark_scaled("default", "svc")
        assert buffer.needs_scale_signal("default", "svc") is True

    def test_cleanup_expired_resolves_futures(self, buffer):
        fut = asyncio.get_event_loop().create_future()
        buffer.add_waiter("default", "svc", fut)
        buffer._waiters[("default", "svc")][0][1].created_at = time.monotonic() - 60

        expired = buffer.cleanup_expired()
        assert expired == 1
        assert buffer.waiter_count("default", "svc") == 0
        assert fut.done()