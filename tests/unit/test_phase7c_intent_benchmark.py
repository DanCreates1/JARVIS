from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase7c-intent-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase7c_intent_benchmark_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = _load_script()


def test_fixed_phase7c_targets_and_closed_mapping() -> None:
    assert BENCHMARK.MAPPING_GATE_EVALUATIONS == 10_000
    assert BENCHMARK.NEGATIVE_EVENTS == 36_000
    assert BENCHMARK.MAX_MAPPING_P95_MS == 5.0
    assert BENCHMARK.MAX_RSS_GROWTH_MIB == 25.0
    assert BENCHMARK.run_mapping_contract()["exact"] is True


def test_phase7c_synthetic_gate_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BENCHMARK, "MAPPING_GATE_EVALUATIONS", 50)
    monkeypatch.setattr(BENCHMARK, "NEGATIVE_EVENTS", 100)
    result = asyncio.run(BENCHMARK.run_benchmark())

    assert result["passed"] is True
    assert result["mapping_gate"]["proposals"] == 50
    assert result["mapping_gate"]["direct_effects"] == 0
    assert result["mapping_gate"]["authority_escalations"] == 0
    assert result["negative_gate"]["events"] == 100
    assert result["negative_gate"]["direct_effects"] == 0
    assert result["negative_gate"]["post_cancel_proposals"] == 0


def test_benchmark_output_is_bounded_and_exclusive(
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
    output = runtime / "phase7c" / "result.json"
    BENCHMARK.write_result(output, json.dumps({"passed": True}))
    assert json.loads(output.read_text(encoding="utf-8")) == {"passed": True}
    with pytest.raises(FileExistsError, match="exist"):
        BENCHMARK.write_result(output, json.dumps({"passed": False}))
