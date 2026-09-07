from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase5-research-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase5_research_benchmark_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = _load_script()


def test_phase5_benchmark_bounds_work_directory_and_sample_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(BENCHMARK, "RUNTIME_ROOT", runtime.resolve())
    with pytest.raises(ValueError, match="child"):
        BENCHMARK.prepare_work_dir(tmp_path / "outside")
    with pytest.raises(SystemExit):
        BENCHMARK.parse_args(["--work-dir", "runtime/example", "--samples", "19"])
    assert BENCHMARK.prepare_work_dir(runtime / "fresh") == (runtime / "fresh").resolve()


def test_phase5_golden_fixture_has_fresh_stale_conflicting_and_diverse_evidence() -> None:
    fixture = json.loads(BENCHMARK.GOLDEN_PATH.read_text(encoding="utf-8"))
    statuses = {claim["status"] for task in fixture["tasks"] for claim in task["claims"]}
    assert {"verified", "likely", "stale", "conflicting"}.issubset(statuses)
    assert all(
        len({source["url"].split("/", 3)[2] for source in task["sources"]}) >= 2
        for task in fixture["tasks"]
    )
    assert any(
        "Ignore previous instructions" in source["text"]
        for task in fixture["tasks"]
        for source in task["sources"]
    )


@pytest.mark.asyncio
async def test_phase5_benchmark_enforces_all_declared_quality_targets() -> None:
    result = await BENCHMARK.run_benchmark(
        argparse.Namespace(samples=20, output="results.json", enforce=True)
    )
    assert result["passed"] is True
    assert result["metrics"]["samples_completed"] == 20
    assert result["metrics"]["failures"] == 0
    assert all(result["checks"].values())
