import pytest
from kubbernetd.proxy.buffer import RequestBuffer


@pytest.fixture
def buffer():
    return RequestBuffer()


def test_not_ready_initially(buffer):
    assert buffer.is_ready("test-svc") is False


def test_mark_ready(buffer):
    buffer.mark_ready("test-svc")
    assert buffer.is_ready("test-svc") is True