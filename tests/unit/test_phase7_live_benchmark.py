from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase7-live-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase7_live_benchmark_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = _load_script()


def test_fixed_live_targets_and_quantile() -> None:
    assert BENCHMARK.SOAK_SECONDS == 1_800
    assert BENCHMARK.TARGET_FPS == 10.0
    assert BENCHMARK.MAX_DETECTOR_P95_MS == 100.0
    assert BENCHMARK.MAX_PIPELINE_P50_MS == 75.0
    assert BENCHMARK.MAX_PIPELINE_P95_MS == 150.0
    assert BENCHMARK.MIN_PROCESSED_FPS == 9.0
    assert BENCHMARK.MAX_TOTAL_CPU_PERCENT == 35.0
    assert BENCHMARK.MAX_RSS_GROWTH_MIB == 50.0
    assert BENCHMARK.MAX_FALSE_ACTIVATIONS_PER_HOUR == 0.1
    assert BENCHMARK._quantile([1.0, 3.0, 2.0], 0.95) == 3.0
    assert BENCHMARK._quantile([], 0.95) is None


def test_live_output_is_runtime_bounded_json_and_exclusive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(BENCHMARK, "RUNTIME_ROOT", runtime.resolve())
    with pytest.raises(ValueError, match="child"):
        BENCHMARK.prepare_output_path(tmp_path / "outside.json")
    with pytest.raises(ValueError, match="JSON"):
        BENCHMARK.prepare_output_path(runtime / "result.txt")
    output = BENCHMARK.prepare_output_path(runtime / "phase7" / "result.json")
    BENCHMARK.write_result(output, json.dumps({"passed": True}))
    assert json.loads(output.read_text(encoding="utf-8")) == {"passed": True}
    with pytest.raises(FileExistsError):
        BENCHMARK.write_result(output, json.dumps({"passed": False}))
