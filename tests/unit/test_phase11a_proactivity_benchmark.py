from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_benchmark() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase11a-proactivity-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase11a_proactivity_benchmark", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase11a_benchmark_small_run_passes_and_retains_no_authority() -> None:
    result = _load_benchmark()._measure(valid_samples=20, abuse_samples=20)

    assert result["passed"] is True
    assert result["valid_failures"] == 0
    assert result["false_accepts"] == 0
    assert result["duplicate_candidates"] == 0
    assert result["retained_candidate_content"] == 0
    assert result["task_executions"] == 0
    assert result["notifications_sent"] == 0
