import pytest
from kubbernetd.operator.optimizer import ColdStartProfiler


@pytest.fixture
def profiler():
    return ColdStartProfiler()


def test_profiler_starts_empty(profiler):
    assert profiler.stages == {}
    assert profiler.total_seconds == 0.0


def test_profiler_records_stages(profiler):
    import time
    profiler.start()
    time.sleep(0.01)
    profiler.end()
    total = profiler.total_seconds
    assert total > 0.0
    assert "total" in profiler.stages


def test_profiler_breakdown_format(profiler):
    import time
    profiler.start()
    profiler.begin_stage("weightLoading")
    time.sleep(0.01)
    profiler.end_stage("weightLoading")
    profiler.end()
    breakdown = profiler.breakdown
    assert "total:" in breakdown
    assert "weightLoading:" in breakdown


def test_optimization_suggestions(profiler):
    tips = profiler.suggests_optimizations({"weightLoading": 30.0, "cudaGraph": 15.0})
    assert len(tips) > 0
    assert any("NVMe" in t for t in tips)


def test_no_suggestions_for_fast_stages(profiler):
    tips = profiler.suggests_optimizations({"weightLoading": 2.0, "cudaGraph": 3.0})
    assert len(tips) == 0