import pytest
from unittest.mock import patch
from kubbernetd.agent.warmer import ModelWarmer
from kubbernetd.common.config import AgentConfig


def test_warmup_noop_when_no_command():
    warmer = ModelWarmer(AgentConfig())
    warmer.warm_up()