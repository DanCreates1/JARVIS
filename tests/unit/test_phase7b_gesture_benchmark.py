from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from jarvis.gestures.models import GestureKind


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase7b-gesture-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase7b_gesture_benchmark_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = _load_script()


def test_fixed_phase7b_targets_and_corpus_shape() -> None:
    assert BENCHMARK.CORPUS_SEQUENCES == 1_000
    assert BENCHMARK.NEGATIVE_SOAK_FRAMES == 36_000
    assert BENCHMARK.CLASSIFIER_FRAMES == 10_000
    assert BENCHMARK.MIN_MACRO_PRECISION == 0.95
    assert BENCHMARK.MIN_MACRO_RECALL == 0.95
    assert BENCHMARK.MIN_GESTURE_PRECISION == 0.90
    assert BENCHMARK.MIN_GESTURE_RECALL == 0.90
    assert BENCHMARK.MAX_FALSE_ACTIVATIONS_PER_HOUR == 0.1
    assert BENCHMARK.MAX_CLASSIFIER_P95_MS == 5.0
    assert BENCHMARK.MAX_RSS_GROWTH_MIB == 50.0
    corpus = BENCHMARK.run_corpus()
    assert corpus["sequences"] == 1_000
    assert set(corpus["per_gesture"]) == {gesture.value for gesture in GestureKind}


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
    output = runtime / "phase7b" / "result.json"
    BENCHMARK.write_result(output, json.dumps({"passed": True}))
    assert json.loads(output.read_text(encoding="utf-8")) == {"passed": True}
    with pytest.raises(FileExistsError, match="new"):
        BENCHMARK.write_result(output, json.dumps({"passed": False}))
