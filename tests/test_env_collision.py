"""Regression test: ProxyConfig must survive Kubernetes Service env collisions.

A Service named ``kubbernetd-proxy`` causes Kubernetes to inject
``KUBBERNETD_PROXY_PORT=tcp://<ip>:<port>`` into every pod in the namespace.
``ProxyConfig.listen_port`` read that variable as an int and crashed the operator
at import time (ValueError: invalid literal for int()). The env var is renamed to
``KUBBERNETD_PROXY_LISTEN_PORT`` and int parsing falls back to the default.
"""
from __future__ import annotations

import importlib

import kubbernetd.common.types as types


def test_proxy_config_survives_k8s_service_env_collision(monkeypatch):
    monkeypatch.setenv("KUBBERNETD_PROXY_PORT", "tcp://10.96.0.1:8080")
    importlib.reload(types)
    assert types.ProxyConfig().listen_port == 8080


def test_proxy_listen_port_env_override(monkeypatch):
    monkeypatch.setenv("KUBBERNETD_PROXY_LISTEN_PORT", "9090")
    importlib.reload(types)
    assert types.ProxyConfig().listen_port == 9090


def test_env_int_falls_back_on_malformed(monkeypatch):
    monkeypatch.setenv("KUBBERNETD_METRICS_PORT", "tcp://10.96.0.1:8080")
    importlib.reload(types)
    assert types.OperatorConfig().metrics_port == 8080
