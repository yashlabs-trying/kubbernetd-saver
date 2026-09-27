import pytest
from unittest.mock import Mock, patch
from kubbernetd.agent.warmer import ModelWarmer
from kubbernetd.common.types import AgentConfig


def test_warmup_noop_when_no_command():
    warmer = ModelWarmer(AgentConfig(warmup_command=None))
    result = warmer.warm_up()
    assert result is True
    assert warmer.is_ready is True


def test_warmup_runs_command():
    cfg = AgentConfig(warmup_command="echo 'warming up'")
    warmer = ModelWarmer(cfg)
    result = warmer.warm_up()
    assert result is True
    assert warmer.is_ready is True


def test_warmup_fails_on_bad_command():
    cfg = AgentConfig(warmup_command="exit 1")
    warmer = ModelWarmer(cfg)
    result = warmer.warm_up()
    assert result is False
    assert warmer.is_ready is False


def test_warmup_checks_model_path(caplog):
    cfg = AgentConfig(model_path="/nonexistent/path/model.bin")
    warmer = ModelWarmer(cfg)
    warmer.warm_up()