"""Regression test: CRD openAPIV3Schema defaults must match their declared types.

The k8s-e2e job previously failed because ``config/crd.yaml`` declared
``bootstrap.cpuRAM`` as ``type: string`` with ``default: 0`` (integer), which the
Kubernetes API server rejects as an invalid CRD.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CRD_FILES = [
    REPO_ROOT / "config" / "crd.yaml",
    REPO_ROOT / "deploy" / "kubbernetd" / "crd.yaml",
]


def _type_matches(type_name: str, value) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object":
        return isinstance(value, dict)
    return True


def _walk(node, path, issues):
    if not isinstance(node, dict):
        return
    type_name = node.get("type")
    if type_name is not None and "default" in node:
        if not _type_matches(type_name, node["default"]):
            issues.append(f"{path}: type={type_name} default={node['default']!r}")
    for name, child in (node.get("properties") or {}).items():
        _walk(child, f"{path}.{name}", issues)
    if isinstance(node.get("items"), dict):
        _walk(node["items"], f"{path}[]", issues)


@pytest.mark.parametrize("crd_path", CRD_FILES, ids=lambda p: p.name)
def test_crd_defaults_match_types(crd_path):
    docs = [d for d in yaml.safe_load_all(crd_path.read_text()) if d]
    crds = [d for d in docs if d.get("kind") == "CustomResourceDefinition"]
    assert crds, f"no CRD found in {crd_path}"
    for crd in crds:
        for version in crd["spec"]["versions"]:
            issues: list[str] = []
            _walk(version["schema"]["openAPIV3Schema"], "openAPIV3Schema", issues)
            assert issues == [], f"{crd_path.name} [{version['name']}]: {issues}"
