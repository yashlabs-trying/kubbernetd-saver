import asyncio
import time
import pytest
from unittest.mock import Mock, patch, AsyncMock
from kubbernetd.proxy.buffer import RequestBuffer


def _make_future():
    loop = asyncio.new_event_loop()
    return loop.create_future()


@pytest.fixture
def buffer():
    return RequestBuffer(max_waiters=5, request_ttl=30.0)


class TestHold:
    def test_hold_accepts_request(self, buffer):
        future = _make_future()
        accepted = buffer.hold("default", "test-rg", future)
        assert accepted is True
        assert buffer.waiter_count("default", "test-rg") == 1

    def test_hold_rejects_when_full(self, buffer):
        for i in range(5):
            fut = _make_future()
            buffer.hold("default", "rg", fut)

        rejected_future = _make_future()
        accepted = buffer.hold("default", "rg", rejected_future)
        assert accepted is False

    def test_release_returns_entries_and_data(self, buffer):
        future = _make_future()
        buffer.hold("default", "rg", future, ("GET", "/v1/chat", {"host": "test"}, b"hello"))
        entries, stored = buffer.release("default", "rg")
        assert len(entries) == 1
        assert stored == ("GET", "/v1/chat", {"host": "test"}, b"hello")
        assert buffer.waiter_count("default", "rg") == 0

    def test_release_empty(self, buffer):
        entries, stored = buffer.release("default", "unknown")
        assert entries == []
        assert stored is None

    def test_needs_scale_signal(self, buffer):
        assert buffer.needs_scale_signal("default", "rg") is True
        assert buffer.needs_scale_signal("default", "rg") is False

    def test_mark_signaled_resets(self, buffer):
        buffer.needs_scale_signal("default", "rg")
        buffer.mark_signaled("default", "rg")
        assert buffer.needs_scale_signal("default", "rg") is True

    def test_cleanup_expired(self, buffer):
        fut = _make_future()
        buffer.hold("default", "rg", fut)
        buffer._holders[("default", "rg")][0][1].created_at = time.monotonic() - 60
        expired = buffer.cleanup_expired()
        assert expired == 1
        assert buffer.waiter_count("default", "rg") == 0