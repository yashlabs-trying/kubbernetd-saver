import time
import pytest
from unittest.mock import Mock, patch, AsyncMock
from aiohttp import web
from kubbernetd.proxy.buffer import RequestBuffer, BufferedRequest


@pytest.fixture
def buffer():
    return RequestBuffer(max_buffer_size=5, request_ttl=30.0)


class TestBuffer:
    def test_buffer_accepts_request(self, buffer):
        req = Mock(spec=web.Request)
        req.method = "GET"
        req.path_qs = "/predict"
        req.headers = {"host": "test"}
        req.body = b""

        resp = buffer.buffer("default", "test-svc", req)
        assert resp.status == 202
        assert buffer.queue_size("default", "test-svc") == 1

    def test_buffer_full(self, buffer):
        for i in range(5):
            req = Mock(spec=web.Request)
            req.method = "GET"
            req.path_qs = "/predict"
            req.headers = {"host": "test"}
            req.body = b""
            buffer.buffer("default", "test-svc", req)

        req = Mock(spec=web.Request)
        req.method = "GET"
        req.path_qs = "/predict"
        req.headers = {"host": "test"}
        req.body = b""
        resp = buffer.buffer("default", "test-svc", req)
        assert resp.status == 503

    def test_pop_ready_returns_all_entries(self, buffer):
        req = Mock(spec=web.Request)
        req.method = "GET"
        req.path_qs = "/predict"
        req.headers = {"host": "test"}
        req.body = b""
        buffer.buffer("default", "test-svc", req)
        buffer.buffer("default", "test-svc", req)

        entries = buffer.pop_ready("default", "test-svc")
        assert len(entries) == 2
        assert buffer.queue_size("default", "test-svc") == 0

    def test_needs_scale_signal(self, buffer):
        assert buffer.needs_scale_signal("default", "svc") is True
        assert buffer.needs_scale_signal("default", "svc") is False

    def test_mark_scaled_resets_signal(self, buffer):
        buffer.needs_scale_signal("default", "svc")
        buffer.mark_scaled("default", "svc")
        assert buffer.needs_scale_signal("default", "svc") is True

    def test_cleanup_expired(self, buffer):
        req = Mock(spec=web.Request)
        req.method = "GET"
        req.path_qs = "/predict"
        req.headers = {"host": "test"}
        req.body = b""
        buffer.buffer("default", "svc", req)
        buffer._queues[("default", "svc")][0].created_at = time.monotonic() - 60
        expired = buffer.cleanup_expired()
        assert expired == 1
        assert buffer.queue_size("default", "svc") == 0

    def test_cleanup_mixed(self, buffer):
        req = Mock(spec=web.Request)
        req.method = "GET"
        req.path_qs = "/predict"
        req.headers = {"host": "test"}
        req.body = b""
        buffer.buffer("default", "svc", req)
        buffer._queues[("default", "svc")][0].created_at = time.monotonic() - 60
        buffer.buffer("default", "svc", req)
        expired = buffer.cleanup_expired()
        assert expired == 1
        assert buffer.queue_size("default", "svc") == 1