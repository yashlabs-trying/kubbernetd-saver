"""Regression test: `kubbernetd install` must not crash on subprocess input.

The k8s-e2e job failed with ``TypeError: memoryview: a bytes-like object is
required, not 'str'`` because ``install`` piped a ``str`` into ``subprocess.run``
without ``text=True``. This test reproduces that exact subprocess semantics.
"""
from __future__ import annotations

import subprocess


class _Result:
    returncode = 0
    stdout = "ok"
    stderr = ""


def test_install_does_not_crash_on_str_input(monkeypatch):
    def fake_run(args, **kwargs):
        # Reproduce real subprocess semantics: str input requires text=True.
        if "input" in kwargs and isinstance(kwargs["input"], str) and not kwargs.get("text"):
            raise TypeError("memoryview: a bytes-like object is required, not 'str'")
        return _Result()

    monkeypatch.setattr(subprocess, "run", fake_run)

    from kubbernetd.cli.install import install

    # Should complete without raising TypeError.
    install(namespace="kubbernetd")
