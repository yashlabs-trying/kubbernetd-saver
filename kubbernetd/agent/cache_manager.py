import os
import structlog
from pathlib import Path
from typing import Optional

log = structlog.get_logger()


class CacheManager:
    def __init__(self, cache_path: str = "/cache/models"):
        self.cache_path = Path(cache_path)

    def has_model(self, model_name: str) -> bool:
        model_dir = self.cache_path / model_name
        return model_dir.is_dir() and any(model_dir.iterdir())

    def shard_path(self, model_name: str, rank: int, pattern: str = "model-rank-{rank}-part-*.safetensors") -> Optional[str]:
        model_dir = self.cache_path / model_name
        if not model_dir.is_dir():
            return None
        from glob import glob
        pat = pattern.replace("{rank}", str(rank))
        matches = list(model_dir.glob(pat))
        if matches:
            return str(matches[0])
        return None

    def all_shards_exist(self, model_name: str, num_shards: int, pattern: str = "model-rank-{rank}-part-*.safetensors") -> bool:
        for rank in range(num_shards):
            path = self.shard_path(model_name, rank, pattern)
            if path is None:
                log.warning("missing shard", model=model_name, rank=rank)
                return False
        log.info("all shards found", model=model_name, count=num_shards)
        return True

    def total_cache_size_gb(self) -> float:
        total = 0
        for f in self.cache_path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total / (1024 ** 3)

    def validate_cache(self, model_name: str, expected_files: int = 0) -> bool:
        model_dir = self.cache_path / model_name
        if not model_dir.is_dir():
            log.warning("cache directory missing", path=str(model_dir))
            return False
        files = list(model_dir.rglob("*.safetensors")) + list(model_dir.rglob("*.bin")) + list(model_dir.rglob("*.json"))
        if expected_files > 0 and len(files) < expected_files:
            log.warning("cache incomplete", model=model_name, found=len(files), expected=expected_files)
            return False
        log.info("cache validated", model=model_name, files=len(files))
        return True