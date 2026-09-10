from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase8b-browser-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase8b_browser_benchmark", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmark_output_is_restricted_to_runtime() -> None:
    module = _load_script()
    allowed = module.RUNTIME_ROOT / "phase8b-test" / "benchmark.json"
    assert module._prepare_output_path(allowed) == allowed.resolve()
    with pytest.raises(ValueError, match="repository runtime"):
        module._prepare_output_path(module.RUNTIME_ROOT.parent / "outside.json")


def test_percentile_uses_fixed_nearest_rank() -> None:
    module = _load_script()
    assert module._percentile([5.0, 1.0, 4.0, 2.0, 3.0], 0.95) == 4.0
