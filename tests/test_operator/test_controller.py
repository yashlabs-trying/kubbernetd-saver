import pytest
from unittest.mock import Mock, patch
from kubbernetd.operator.controller import Controller
from kubbernetd.common.config import OperatorConfig


@pytest.fixture
def controller():
    cfg = OperatorConfig(idle_timeout_seconds=60, check_interval_seconds=10)
    return Controller(cfg)


def test_register_service(controller):
    controller.register_service("test-deploy", "default", {"idleTimeout": 120})
    assert ("test-deploy", "default") in controller.services


def test_remove_service(controller):
    controller.register_service("test-deploy", "default", {})
    controller.remove_service("test-deploy", "default")
    assert ("test-deploy", "default") not in controller.services