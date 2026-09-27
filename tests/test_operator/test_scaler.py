import pytest
from unittest.mock import Mock, patch
from kubernetes import client
from kubbernetd.operator.scaler import Scaler


@pytest.fixture
def scaler():
    apps_api = Mock()
    return Scaler(apps_api)


class TestScaleTo:
    def test_scale_down(self, scaler):
        scaler.scale_to("default", "test-deploy", 0)
        scaler.apps_api.patch_namespaced_deployment_scale.assert_called_once_with(
            name="test-deploy", namespace="default", body={"spec": {"replicas": 0}}
        )

    def test_scale_up(self, scaler):
        scaler.scale_to("default", "test-deploy", 3)
        scaler.apps_api.patch_namespaced_deployment_scale.assert_called_once_with(
            name="test-deploy", namespace="default", body={"spec": {"replicas": 3}}
        )

    def test_api_error_propagates(self, scaler):
        scaler.apps_api.patch_namespaced_deployment_scale.side_effect = (
            client.exceptions.ApiException(status=500, reason="Internal error")
        )
        with pytest.raises(client.exceptions.ApiException):
            scaler.scale_to("default", "test", 0)


class TestCurrentReplicas:
    def test_returns_replicas(self, scaler):
        mock_deploy = Mock()
        mock_deploy.spec.replicas = 3
        scaler.apps_api.read_namespaced_deployment.return_value = mock_deploy
        assert scaler.current_replicas("default", "test") == 3

    def test_returns_one_when_replicas_none(self, scaler):
        mock_deploy = Mock()
        mock_deploy.spec.replicas = None
        scaler.apps_api.read_namespaced_deployment.return_value = mock_deploy
        assert scaler.current_replicas("default", "test") == 1

    def test_api_error_propagates(self, scaler):
        scaler.apps_api.read_namespaced_deployment.side_effect = (
            client.exceptions.ApiException(status=404, reason="Not found")
        )
        with pytest.raises(client.exceptions.ApiException):
            scaler.current_replicas("default", "nonexistent")