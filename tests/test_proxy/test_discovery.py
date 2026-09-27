import time
import pytest
from kubbernetd.proxy.discovery import ServiceDiscovery


@pytest.fixture
def discovery():
    return ServiceDiscovery()


class TestCache:
    def test_cache_returns_none_for_unknown(self, discovery):
        assert discovery._from_cache("ns", "unknown") is None

    def test_cache_returns_cached_value(self, discovery):
        with discovery._lock:
            discovery._cache[("ns", "svc")] = (["10.0.0.1"], time.monotonic())
        result = discovery._from_cache("ns", "svc")
        assert result == ["10.0.0.1"]

    def test_cache_expires(self, discovery):
        with discovery._lock:
            discovery._cache[("ns", "svc")] = (["10.0.0.1"], time.monotonic() - 10)
        result = discovery._from_cache("ns", "svc")
        assert result is None

    def test_clear_all_cache(self, discovery):
        with discovery._lock:
            discovery._cache[("ns", "svc")] = (["10.0.0.1"], time.monotonic())
        discovery.clear_cache()
        assert discovery._from_cache("ns", "svc") is None

    def test_clear_specific_cache(self, discovery):
        with discovery._lock:
            discovery._cache[("ns1", "svc1")] = (["10.0.0.1"], time.monotonic())
            discovery._cache[("ns2", "svc2")] = (["10.0.0.2"], time.monotonic())
        discovery.clear_cache(namespace="ns1", name="svc1")
        assert discovery._from_cache("ns1", "svc1") is None
        assert discovery._from_cache("ns2", "svc2") is not None


class TestHasReadyPods:
    def test_no_pods_returns_false(self, discovery):
        with discovery._lock:
            discovery._cache[("ns", "svc")] = ([], time.monotonic())
        assert discovery.has_ready_pods("ns", "svc") is False

    def test_has_pods_returns_true(self, discovery):
        with discovery._lock:
            discovery._cache[("ns", "svc")] = (["10.0.0.1"], time.monotonic())
        assert discovery.has_ready_pods("ns", "svc") is True