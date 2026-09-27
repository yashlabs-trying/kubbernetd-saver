import pytest
from unittest.mock import Mock, patch
from kubbernetd.operator.controller import Controller
from kubbernetd.common.types import OperatorConfig


@pytest.fixture
def controller():
    cfg = OperatorConfig(idle_timeout_seconds=60, check_interval_seconds=10)
    return Controller(cfg)


def test_register_service(controller):
    controller.register_service("test-deploy", "default", {"idleTimeout": 120})
    assert ("test-deploy", "default") in controller.services
    assert controller.idle_detector.is_watched("default", "test-deploy") is True


def test_remove_service(controller):
    controller.register_service("test-deploy", "default", {})
    controller.remove_service("test-deploy", "default")
    assert ("test-deploy", "default") not in controller.services
    assert controller.idle_detector.is_watched("default", "test-deploy") is False


def test_tick_triggers_cleanup_every_10(controller):
    controller.idle_detector.watch("ns", "app")
    for _ in range(10):
        controller.tick()
    assert controller._tick_count == 10


def test_service_removal_also_unwatches(controller):
    controller.register_service("svc", "ns", {})
    assert controller.idle_detector.is_watched("ns", "svc") is True
    controller.remove_service("svc", "ns")
    assert controller.idle_detector.is_watched("ns", "svc") is False


def test_update_service_changes_timeout(controller):
    controller.register_service("svc", "ns", {"idleTimeout": 300})
    assert controller.services[("svc", "ns")]["idle_timeout"] == 300
    controller.update_service("svc", "ns", {"idleTimeout": 600})
    assert controller.services[("svc", "ns")]["idle_timeout"] == 600