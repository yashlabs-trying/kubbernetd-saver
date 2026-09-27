import pytest
from unittest.mock import Mock, patch
from kubbernetd.operator.scaler import Scaler


@pytest.fixture
def scaler():
    apps_api = Mock()
    return Scaler(apps_api)


def test_scale_to(scaler):
    scaler.scale_to("default", "test-deploy", 0)
    scaler.apps_api.patch_namespaced_deployment_scale.assert_called_once()


def test_scale_to_zero_passes_correct_body(scaler):
    scaler.scale_to("default", "test-deploy", 0)
    args, kwargs = scaler.apps_api.patch_namespaced_deployment_scale.call_args
    assert kwargs["name"] == "test-deploy"
    assert kwargs["namespace"] == "default"
    assert kwargs["body"]["spec"]["replicas"] == 0


def test_current_replicas(scaler):
    mock_deploy = Mock()
    mock_deploy.spec.replicas = 3
    scaler.apps_api.read_namespaced_deployment.return_value = mock_deploy
    result = scaler.current_replicas("default", "test-deploy")
    assert result == 3