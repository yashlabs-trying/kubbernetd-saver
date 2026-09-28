import time
import threading
import pytest
from unittest.mock import Mock, patch
from kubernetes import client
from kubbernetd.operator.rg_controller import ReplicaGroupController, GroupPhase
from kubbernetd.operator.metrics import MetricsExporter
from kubbernetd.common.types import OperatorConfig


class ControllerForTest(ReplicaGroupController):
    def __init__(self, config):
        self.config = config
        self.apps_api = Mock()
        self.core_api = Mock()
        self.custom_api = Mock()
        self.metrics = Mock(spec=MetricsExporter)
        self._lock = threading.RLock()
        self._groups = {}
        self._tick_count = 0


@pytest.fixture
def controller():
    cfg = OperatorConfig(idle_timeout_seconds=60, check_interval_seconds=10)
    return ControllerForTest(cfg)


@pytest.fixture
def qwen_spec():
    return {
        "model": {
            "name": "Qwen/Qwen2.5-70B",
            "engine": "vLLM",
            "tensorParallel": 8,
            "workers": 8,
            "weightShards": 8,
        },
        "targetRef": {"kind": "Deployment", "name": "qwen-worker"},
        "sleepPolicy": {"idleTimeout": 60, "sleepDepth": "full"},
        "wakeSLO": 30,
    }


class TestRegistration:
    def test_register_group(self, controller, qwen_spec):
        controller.register_group("qwen-70b", "default", qwen_spec)
        state = controller.get_group("qwen-70b", "default")
        assert state is not None
        assert state.name == "qwen-70b"
        assert state.namespace == "default"
        assert state.phase == GroupPhase.RUNNING

    def test_register_then_remove(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        controller.remove_group("svc", "ns")
        assert controller.get_group("svc", "ns") is None

    def test_update_group(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        controller.update_group("svc", "ns", {"model": {"name": "new-model", "workers": 4}})
        state = controller.get_group("svc", "ns")
        assert state.spec["model"]["name"] == "new-model"


class TestStateMachine:
    def test_initial_phase_is_running(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        state = controller.get_group("svc", "ns")
        assert state.phase == GroupPhase.RUNNING

    def test_valid_transition(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        state = controller.get_group("svc", "ns")
        controller._transition("svc", "ns", state, GroupPhase.DRAINING)
        assert state.phase == GroupPhase.DRAINING

    def test_invalid_transition_logs_warning(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        state = controller.get_group("svc", "ns")
        controller._transition("svc", "ns", state, GroupPhase.SLEEPING)
        assert state.phase == GroupPhase.RUNNING

    def test_full_cycle(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        state = controller.get_group("svc", "ns")
        controller._transition("svc", "ns", state, GroupPhase.DRAINING)
        controller._transition("svc", "ns", state, GroupPhase.SCALING_DOWN)
        controller._transition("svc", "ns", state, GroupPhase.SLEEPING)
        controller._transition("svc", "ns", state, GroupPhase.ALLOCATING)
        controller._transition("svc", "ns", state, GroupPhase.STARTING)
        controller._transition("svc", "ns", state, GroupPhase.LOADING_WEIGHTS)
        controller._transition("svc", "ns", state, GroupPhase.INITIALIZING)
        controller._transition("svc", "ns", state, GroupPhase.WARMING)
        controller._transition("svc", "ns", state, GroupPhase.RUNNING)
        assert state.phase == GroupPhase.RUNNING

    def test_tick_does_not_crash(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        controller.tick()
        assert controller._tick_count == 1


class TestScalingDown:
    def test_scale_down_sets_workers_to_zero(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        state = controller.get_group("svc", "ns")
        controller._transition("svc", "ns", state, GroupPhase.DRAINING)
        controller._transition("svc", "ns", state, GroupPhase.SCALING_DOWN)
        controller._handle_scaling_down("svc", "ns", state, time.monotonic())
        assert state.current_workers == 0
        assert state.phase == GroupPhase.SLEEPING

    def test_scale_down_calls_api(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        state = controller.get_group("svc", "ns")
        controller._transition("svc", "ns", state, GroupPhase.DRAINING)
        controller._transition("svc", "ns", state, GroupPhase.SCALING_DOWN)
        controller._handle_scaling_down("svc", "ns", state, time.monotonic())
        controller.apps_api.patch_namespaced_deployment_scale.assert_called_once()


class TestAllocating:
    def test_allocate_sets_workers(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        state = controller.get_group("svc", "ns")
        controller._transition("svc", "ns", state, GroupPhase.DRAINING)
        controller._transition("svc", "ns", state, GroupPhase.SCALING_DOWN)
        controller._transition("svc", "ns", state, GroupPhase.SLEEPING)
        controller._transition("svc", "ns", state, GroupPhase.ALLOCATING)
        controller._handle_allocating("svc", "ns", state, time.monotonic())
        assert state.current_workers == 8
        assert state.phase == GroupPhase.STARTING


class TestError:
    def test_error_backoff_increases(self, controller, qwen_spec):
        controller.register_group("svc", "ns", qwen_spec)
        state = controller.get_group("svc", "ns")
        controller._transition("svc", "ns", state, GroupPhase.ERROR)
        state.error_count = 1
        state.last_error_at = time.monotonic() - 5
        controller._handle_error("svc", "ns", state, time.monotonic())
        assert state.error_count == 2