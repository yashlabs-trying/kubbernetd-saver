"""Regression test: the operator must be allowed to *watch* CRDs.

Without ``watch`` on ``apiextensions.k8s.io/customresourcedefinitions``, kopf
disables resource watching and only notices ReplicaGroups on operator restart,
so newly created groups are never woken (k8s-e2e E2E 4/9).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RBAC_FILES = [
    REPO_ROOT / "config" / "operator-rbac.yaml",
    REPO_ROOT / "deploy" / "kubbernetd" / "rbac.yaml",
]


def _cluster_roles(path: Path):
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d]
    return [d for d in docs if d.get("kind") == "ClusterRole"]


@pytest.mark.parametrize("path", RBAC_FILES, ids=lambda p: p.parent.name + "/" + p.name)
def test_operator_can_watch_crds(path):
    rules = []
    for role in _cluster_roles(path):
        rules.extend(role.get("rules", []))
    crd_rules = [
        r
        for r in rules
        if "apiextensions.k8s.io" in r.get("apiGroups", [])
        and "customresourcedefinitions" in r.get("resources", [])
    ]
    assert crd_rules, f"{path}: no customresourcedefinitions rule"
    assert any("watch" in r.get("verbs", []) for r in crd_rules), (
        f"{path}: customresourcedefinitions rule must include 'watch'"
    )
