import pytest
from unittest.mock import Mock, patch
from kubbernetd.agent.cache_manager import CacheManager


@pytest.fixture
def manager(tmp_path):
    return CacheManager(cache_path=str(tmp_path))


def test_cache_empty(manager):
    assert manager.has_model("nonexistent") is False


def test_cache_detected(manager, tmp_path):
    model_dir = tmp_path / "test-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}")
    assert manager.has_model("test-model") is True


def test_shard_path_returns_none_for_missing(manager):
    path = manager.shard_path("test-model", 0)
    assert path is None


def test_shard_path_found(manager, tmp_path):
    model_dir = tmp_path / "test-model"
    model_dir.mkdir()
    shard = model_dir / "model-rank-0-part-0.safetensors"
    shard.write_text("data")
    path = manager.shard_path("test-model", 0, "model-rank-{rank}-part-*.safetensors")
    assert path is not None
    assert "model-rank-0" in path


def test_all_shards_exist(manager, tmp_path):
    model_dir = tmp_path / "sharded-model"
    model_dir.mkdir()
    for rank in range(4):
        (model_dir / f"model-rank-{rank}-part-0.safetensors").write_text("data")
    assert manager.all_shards_exist("sharded-model", 4) is True
    assert manager.all_shards_exist("sharded-model", 5) is False


def test_validate_cache(manager, tmp_path):
    model_dir = tmp_path / "valid-model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}")
    (model_dir / "model.safetensors").write_text("data")
    assert manager.validate_cache("valid-model") is True