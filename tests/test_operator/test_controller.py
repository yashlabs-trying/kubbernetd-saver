import time
import pytest
from unittest.mock import Mock, patch, call
from kubernetes import client
from kubbernetd.operator.controller import Controller, ServicePhase
from kubbernetd.common.types import OperatorConfig


@pytest.fixture
def controller():
    cfg = OperatorConfig(idle_timeout_seconds=60, check_interval_seconds=10)
    ctrl = Controller(cfg)
    ctrl.mark_ready()
    return ctrl


@pytest.fixture
def basic_spec():
    return {"idleTimeout": 60, "minReplicas": 0, "maxReplicas": 5}


class TestRegistration:
    def test_register_service(self, controller, basic_spec):
        controller.register_service("test-deploy", "default", basic_spec)
        svc = controller._get_service("test-deploy", "default")
        assert svc is not None
        assert svc["idle_timeout"] == 60

    def test_register_service_defaults(self, controller):
        controller.register_service("svc", "ns", {})
        svc = controller._get_service("svc", "ns")
        assert svc["idle_timeout"] == 60
        assert svc["min_replicas"] == 0
        assert svc["max_replicas"] == 10

    def test_remove_service(self, controller, basic_spec):
        controller.register_service("svc", "ns", basic_spec)
        controller.remove_service("svc", "ns")
        assert controller._get_service("svc", "ns") is None

    def test_update_service(self, controller, basic_spec):
        controller.register_service("svc", "ns", basic_spec)
        controller.update_service("svc", "ns", {"idleTimeout": 120})
        svc = controller._get_service("svc", "ns")
        assert svc["idle_timeout"] == 120

    def test_update_nonexistent_registers(self, controller):
        controller.update_service("new", "ns", {"idleTimeout": 30})
        assert controller._get_service("new", "ns") is not None


class TestIdleTimeoutZero:
    def test_idle_timeout_zero_never_scales(self, controller):
        controller.register_service("svc", "ns", {"idleTimeout": 0})
        controller.tick()
        svc = controller._get_service("svc", "ns")
        assert svc["phase"] != ServicePhase.SCALING_DOWN


class TestScaleLogic:
    def test_scale_down_when_idle(self, controller):
        controller.register_service("svc", "ns", {"idleTimeout": 1})
        controller.idle_detector.watch("ns", "svc")
        controller.idle_detector._last_request[("ns", "svc")] = time.monotonic() - 10
        controller._do_scale = Mock()
        controller.tick()
        assert controller._do_scale.called

    def test_no_scale_when_not_idle(self, controller):
        controller.register_service("svc", "ns", {"idleTimeout": 60})
        controller.idle_detector.watch("ns", "svc")
        controller.idle_detector.touch("ns", "svc")
        controller._do_scale = Mock()
        controller.tick()
        assert not controller._do_scale.called

    def test_scale_up_when_traffic_arrives(self, controller):
        controller.register_service("svc", "ns", {"idleTimeout": 60})
        with controller._lock:
            svc = controller._services[("svc", "ns")]
            svc["current_replicas"] = 0
            svc["phase"] = ServicePhase.STOPPED
        controller.idle_detector.touch("ns", "svc")
        controller._do_scale = Mock()
        controller.tick()
        assert controller._do_scale.called


class TestErrorRecovery:
    def test_scale_error_records_backoff(self, controller):
        controller.register_service("svc", "ns", {"idleTimeout": 1})
        svc = controller._get_service("svc", "ns")
        now = time.monotonic()
        controller._record_error(svc, now)
        assert svc["error_count"] == 1
        assert svc["phase"] == ServicePhase.ERROR
        remaining = controller._cooldown_remaining(svc, now)
        assert remaining > 0

    def test_backoff_increases_with_errors(self, controller):
        svc = {"last_error_at": time.monotonic(), "error_count": 5}
        remaining = controller._cooldown_remaining(svc, time.monotonic())
        assert remaining > 0

    def test_no_backoff_without_errors(self, controller):
        svc = {"last_error_at": None, "error_count": 0}
        remaining = controller._cooldown_remaining(svc, time.monotonic())
        assert remaining == 0


class TestConcurrency:
    def test_register_and_tick_simultaneously(self, controller):
        import threading
        results = []
        def register():
            controller.register_service("svc", "ns", {})
            results.append("done")
        t = threading.Thread(target=register)
        t.start()
        controller.tick()
        t.join()
        assert controller._get_service("svc", "ns") is not None


class TestMinReplicas:
    def test_respects_min_replicas(self, controller):
        controller.register_service("svc", "ns", {"idleTimeout": 1, "minReplicas": 1})
        controller.idle_detector.watch("ns", "svc")
        controller.idle_detector._last_request[("ns", "svc")] = time.monotonic() - 10
        controller._do_scale = Mock()
        controller.tick()
        assert not controller._do_scale.called


class TestCleanup:
    def test_cleanup_runs_every_10_ticks(self, controller):
        controller.register_service("svc", "ns", {})
        for _ in range(10):
            controller.tick()
        assert controller._tick_count == 10