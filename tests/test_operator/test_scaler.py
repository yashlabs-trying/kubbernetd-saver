import pytest
from unittest.mock import Mock
from kubbernetd.operator.scaler import Scaler


@pytest.fixture
def scaler():
    apps_api = Mock()
    return Scaler(apps_api)


def test_scale_to(scaler):
    scaler.scale_to("default", "test-deploy", 0)
    scaler.apps_api.patch_namespaced_deployment_scale.assert_called_once()