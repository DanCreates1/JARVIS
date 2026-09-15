from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType


def _load_benchmark() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase11c-device-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase11c_device_benchmark", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase11c_benchmark_small_run_has_one_owner_and_no_effect() -> None:
    result = asyncio.run(_load_benchmark()._measure(valid_samples=20, abuse_samples=20))

    assert result["passed"] is True
    assert result["valid_failures"] == 0
    assert result["false_claims"] == 0
    assert result["single_owner"] is True
    assert result["ownership_events"] == 3
    assert result["duplicate_deliveries"] == 0
    assert result["effects_executed"] == 0
    assert result["retained_private_content"] == 0
