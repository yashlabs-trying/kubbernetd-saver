import time
import pytest
from kubbernetd.monitor.idle_detector import IdleDetector
from kubbernetd.common.config import OperatorConfig


@pytest.fixture
def detector():
    return IdleDetector(OperatorConfig(idle_timeout_seconds=60))


def test_touch_and_idle(detector):
    detector.touch("default", "test")
    assert detector.idle_seconds("default", "test") < 1


def test_no_request_returns_none(detector):
    assert detector.idle_seconds("default", "test") is None