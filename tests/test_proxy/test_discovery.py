import time
import pytest
from kubbernetd.proxy.discovery import EndpointDiscovery


@pytest.fixture
def discovery():
    return EndpointDiscovery(cache_ttl=5.0)


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


class TestRoundRobin:
    def test_next_ip_cycles(self, discovery):
        with discovery._lock:
            discovery._cache[("ns", "svc")] = (["10.0.0.1", "10.0.0.2"], time.monotonic())
            discovery._rr_index[("ns", "svc")] = 0
        assert discovery.next_ip("ns", "svc") == "10.0.0.1"
        assert discovery.next_ip("ns", "svc") == "10.0.0.2"
        assert discovery.next_ip("ns", "svc") == "10.0.0.1"

    def test_next_ip_returns_none_when_no_pods(self, discovery):
        with discovery._lock:
            discovery._cache[("ns", "svc")] = ([], time.monotonic())
        assert discovery.next_ip("ns", "svc") is None

    def test_has_ready_pods(self, discovery):
        with discovery._lock:
            discovery._cache[("ns", "svc")] = (["10.0.0.1"], time.monotonic())
        assert discovery.has_ready_pods("ns", "svc") is True
        discovery._cache[("ns", "empty")] = ([], time.monotonic())
        assert discovery.has_ready_pods("ns", "empty") is False

    def test_clear_cache(self, discovery):
        with discovery._lock:
            discovery._cache[("ns", "svc")] = (["10.0.0.1"], time.monotonic())
            discovery._rr_index[("ns", "svc")] = 3
        discovery.clear_cache("ns", "svc")
        assert discovery._from_cache("ns", "svc") is None
        assert ("ns", "svc") not in discovery._rr_index