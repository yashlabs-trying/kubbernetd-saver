import time
import pytest
from kubbernetd.monitor.idle_detector import IdleDetector
from kubbernetd.common.types import OperatorConfig


@pytest.fixture
def detector():
    cfg = OperatorConfig(idle_timeout_seconds=60)
    return IdleDetector(cfg)


def test_touch_and_idle(detector):
    detector.watch("default", "test")
    detector.touch("default", "test")
    idle = detector.idle_seconds("default", "test")
    assert idle is not None and idle < 1


def test_no_request_returns_none(detector):
    detector.watch("default", "test")
    assert detector.idle_seconds("default", "test") is not None


def test_unwatched_returns_none(detector):
    assert detector.idle_seconds("default", "nonexistent") is None


def test_watch_then_unwatch(detector):
    detector.watch("ns", "app")
    detector.touch("ns", "app")
    assert detector.is_watched("ns", "app") is True
    detector.unwatch("ns", "app")
    assert detector.is_watched("ns", "app") is False
    assert detector.idle_seconds("ns", "app") is None


def test_all_idle_returns_all_watched(detector):
    detector.watch("ns1", "app1")
    detector.watch("ns2", "app2")
    detector.touch("ns1", "app1")
    results = detector.all_idle()
    assert len(results) == 2
    namespaces = {(ns, name) for ns, name, _ in results}
    assert ("ns1", "app1") in namespaces
    assert ("ns2", "app2") in namespaces


def test_cleanup_stale_removes_only_unwatched(detector):
    detector.watch("ns", "watched")
    detector._last_request[("ns", "unwatched_stale")] = time.monotonic() - 90000
    detector.cleanup_stale(max_age_seconds=86400)
    assert ("ns", "watched") in detector._last_request
    assert ("ns", "unwatched_stale") not in detector._last_request