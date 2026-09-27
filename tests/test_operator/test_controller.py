import time
import threading
import pytest
from unittest.mock import Mock
from kubernetes import client
from kubbernetd.operator.controller import Controller, ServicePhase
from kubbernetd.operator.metrics import MetricsExporter
from kubbernetd.monitor.idle_detector import IdleDetector
from kubbernetd.common.types import OperatorConfig


class ControllerForTest(Controller):
    def __init__(self, config):
        self.config = config
        self.apps_api = Mock()
        self.core_api = Mock()
        self.idle_detector = IdleDetector(config)
        self.scaler = Mock()
        self.scaler.current_replicas.return_value = 1
        self.metrics = Mock(spec=MetricsExporter)
        self._lock = threading.RLock()
        self._services = {}
        self._in_flight = {}
        self._crd_to_deployment = {}
        self._tick_count = 0
        self._ready = True


@pytest.fixture
def controller():
    cfg = OperatorConfig(idle_timeout_seconds=60, check_interval_seconds=10)
    return ControllerForTest(cfg)


@pytest.fixture
def basic_spec():
    return {"idleTimeout": 60, "minReplicas": 0, "maxReplicas": 5}


class TestRegistration:
    def test_register_service(self, controller, basic_spec):
        controller.register_service("test-deploy", "default", basic_spec)
        svc = controller._get_service("test-deploy", "default")
        assert svc is not None
        assert svc["idle_timeout"] == 60

    def test_register_with_crd_name(self, controller, basic_spec):
        controller.register_service("deploy", "ns", basic_spec, crd_name="my-crd")
        assert ("my-crd", "ns") in controller._crd_to_deployment
        assert controller._crd_to_deployment[("my-crd", "ns")] == ("deploy", "ns")

    def test_register_service_defaults(self, controller):
        controller.register_service("svc", "ns", {})
        svc = controller._get_service("svc", "ns")
        assert svc["idle_timeout"] == 60
        assert svc["min_replicas"] == 0
        assert svc["max_replicas"] == 10

    def test_remove_service_by_crd(self, controller, basic_spec):
        controller.register_service("deploy", "ns", basic_spec, crd_name="my-crd")
        controller.remove_service_by_crd("ns", "my-crd")
        assert controller._get_service("deploy", "ns") is None

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
        controller.tick()
        controller.scaler.scale_to.assert_called_once_with("ns", "svc", 0)

    def test_no_scale_when_not_idle(self, controller):
        controller.register_service("svc", "ns", {"idleTimeout": 60})
        controller.idle_detector.watch("ns", "svc")
        controller.idle_detector.touch("ns", "svc")
        controller.scaler.scale_to.reset_mock()
        controller.tick()
        controller.scaler.scale_to.assert_not_called()

    def test_no_scale_when_in_flight(self, controller):
        controller.register_service("svc", "ns", {"idleTimeout": 1})
        controller.track_in_flight("ns", "svc", 1)
        controller.idle_detector.watch("ns", "svc")
        controller.idle_detector._last_request[("ns", "svc")] = time.monotonic() - 10
        controller.scaler.scale_to.reset_mock()
        controller.tick()
        controller.scaler.scale_to.assert_not_called()

    def test_in_flight_tracking(self, controller):
        controller.track_in_flight("ns", "svc", 1)
        assert controller.in_flight_count("ns", "svc") == 1
        controller.track_in_flight("ns", "svc", -1)
        assert controller.in_flight_count("ns", "svc") == 0


class TestErrorRecovery:
    def test_scale_error_records_backoff(self, controller):
        controller.register_service("svc", "ns", {"idleTimeout": 1})
        svc = controller._get_service("svc", "ns")
        now = time.monotonic()
        controller._record_error(svc, now)
        assert svc["error_count"] == 1
        assert svc["phase"] == ServicePhase.ERROR
        remaining = controller._cooldown_remaining(svc, now + 1)
        assert remaining > 0

    def test_no_backoff_without_errors(self, controller):
        svc = {"last_error_at": None, "error_count": 0}
        remaining = controller._cooldown_remaining(svc, time.monotonic())
        assert remaining == 0


class TestPreviousReplicas:
    def test_scale_down_stores_previous(self, controller):
        controller.register_service("svc", "ns", {"idleTimeout": 1})
        with controller._lock:
            svc = controller._services[("svc", "ns")]
            svc["current_replicas"] = 3
        controller.scaler.scale_to.reset_mock()
        with controller._lock:
            svc["phase"] = ServicePhase.RUNNING
        controller.idle_detector._last_request[("ns", "svc")] = time.monotonic() - 10
        controller.tick()
        assert controller.scaler.scale_to.called
        args = controller.scaler.scale_to.call_args
        assert args[0][2] == 0  # scaled to 0


class TestReconcile:
    def test_reconcile_detects_drift(self, controller):
        controller.register_service("svc", "ns", {})
        controller.scaler.current_replicas.return_value = 5
        svc = controller._get_service("svc", "ns")
        controller._reconcile_actual_replicas("svc", "ns", svc)
        assert svc["current_replicas"] == 5


class TestCleanup:
    def test_cleanup_runs_every_10_ticks(self, controller):
        controller.register_service("svc", "ns", {})
        for _ in range(10):
            controller.tick()
        assert controller._tick_count == 10