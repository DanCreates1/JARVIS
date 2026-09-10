from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase7-recorded-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase7_recorded_benchmark_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = _load_script()


def test_recorded_fixture_contract_is_fixed() -> None:
    assert len(BENCHMARK.GESTURE_GRID_SHA256) == 64
    assert len(BENCHMARK.DIVERSITY_GRID_SHA256) == 64
    assert set(BENCHMARK.GESTURE_CROPS) == {
        "fist",
        "ok",
        "stop",
        "one",
        "call",
        "peace",
        "rock",
    }
    assert len(BENCHMARK.DIVERSITY_CROPS) == 25


def test_recorded_paths_are_confined_to_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(BENCHMARK, "RUNTIME_ROOT", runtime.resolve())
    assert BENCHMARK._runtime_path(str(runtime / "result.json")) == runtime / "result.json"
    with pytest.raises(argparse.ArgumentTypeError, match="runtime"):
        BENCHMARK._runtime_path(str(tmp_path / "outside.json"))
    with pytest.raises(ValueError, match="child"):
        BENCHMARK.prepare_output_path(runtime)
    with pytest.raises(ValueError, match="JSON"):
        BENCHMARK.prepare_output_path(runtime / "result.txt")
    output = BENCHMARK.prepare_output_path(runtime / "phase7" / "result.json")
    BENCHMARK.write_result(output, json.dumps({"passed": True}))
    assert json.loads(output.read_text(encoding="utf-8")) == {"passed": True}
    with pytest.raises(FileExistsError):
        BENCHMARK.write_result(output, json.dumps({"passed": False}))
