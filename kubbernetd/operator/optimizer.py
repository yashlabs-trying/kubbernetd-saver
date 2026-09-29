import structlog
from typing import Optional

log = structlog.get_logger()


def _format_seconds(seconds: float) -> str:
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m {int(seconds % 60)}s"


class ColdStartProfiler:
    def __init__(self):
        self._stages: dict[str, float] = {}
        self._current_stage: Optional[str] = None
        self._stage_start: float = 0.0
        self._started: bool = False

    def start(self):
        import time
        self._started = True
        self._current_stage = "total"
        self._stage_start = time.monotonic()

    def begin_stage(self, name: str):
        import time
        if self._current_stage and self._stage_start > 0:
            elapsed = time.monotonic() - self._stage_start
            self._stages[self._current_stage] = elapsed
        self._current_stage = name
        self._stage_start = time.monotonic()

    def end_stage(self, name: str):
        import time
        if self._current_stage == name:
            elapsed = time.monotonic() - self._stage_start
            self._stages[name] = elapsed
            self._current_stage = None

    def end(self):
        import time
        if self._current_stage:
            elapsed = time.monotonic() - self._stage_start
            if self._current_stage in self._stages:
                self._stages[self._current_stage] += elapsed
            else:
                self._stages[self._current_stage] = elapsed
        self._started = False

    @property
    def stages(self) -> dict:
        return dict(self._stages)

    @property
    def total_seconds(self) -> float:
        return sum(self._stages.values())

    @property
    def breakdown(self) -> str:
        total = self.total_seconds
        parts = [f"total: {_format_seconds(total)}"]
        for name, secs in self._stages.items():
            pct = (secs / total * 100) if total > 0 else 0
            parts.append(f"  {name}: {_format_seconds(secs)} ({pct:.0f}%)")
        return "\n".join(parts)

    def suggests_optimizations(self, stages: dict) -> list[str]:
        tips = []
        weight = stages.get("weightLoading", 0)
        if weight > 10:
            tips.append(f"Weight loading took {_format_seconds(weight)}. Enable node-local NVMe cache via weightCache.nodeNVMe=true")
        graph = stages.get("cudaGraph", 0)
        if graph > 10:
            tips.append(f"CUDA graph capture took {_format_seconds(graph)}. Try --enforce-eager on cold start, capture graphs asynchronously")
        warmup = stages.get("warmup", 0)
        if warmup > 5:
            tips.append(f"Warmup took {_format_seconds(warmup)}. Consider a bootstrap draft model for faster first-token")
        return tips