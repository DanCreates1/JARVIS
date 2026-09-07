from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase6-task-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase6_task_benchmark_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = _load_script()


def test_phase6_benchmark_bounds_work_directory_and_sample_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(BENCHMARK, "RUNTIME_ROOT", runtime.resolve())
    with pytest.raises(ValueError, match="child"):
        BENCHMARK.prepare_work_dir(tmp_path / "outside")
    with pytest.raises(SystemExit):
        BENCHMARK.parse_args(
            ["--work-dir", "runtime/example", "--samples", "99", "--golden-scenarios", "100"]
        )
    with pytest.raises(SystemExit):
        BENCHMARK.parse_args(
            ["--work-dir", "runtime/example", "--samples", "100", "--golden-scenarios", "99"]
        )
    assert BENCHMARK.prepare_work_dir(runtime / "fresh") == (runtime / "fresh").resolve()


@pytest.mark.asyncio
async def test_phase6_benchmark_reports_correctness_recovery_and_latency(tmp_path: Path) -> None:
    result = await BENCHMARK.run_benchmark(
        argparse.Namespace(
            work_dir=tmp_path,
            samples=5,
            golden_scenarios=5,
            output="results.json",
            enforce=False,
        )
    )
    assert result["metrics"]["performance_samples"] == 5
    assert result["metrics"]["golden_scenarios"] == 5
    assert result["metrics"]["duplicate_effects"] == 0
    assert result["metrics"]["failures"] == 0
    assert result["metrics"]["p95_ms"] > 0
    assert result["checks"]["terminal_correctness"] is True
