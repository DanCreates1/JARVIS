from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase9b-migration-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase9b_migration_benchmark", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase9b_benchmark_has_frozen_full_rehearsal_targets() -> None:
    module = _load_script()

    assert module.CYCLES == 100
    assert module.CAPACITY_BYTES == 64 * 1_024 * 1_024
    assert module.BACKUP_P95_LIMIT_MS == 2_000.0
    assert module.RESTORE_P95_LIMIT_MS == 2_000.0
    assert module.SHADOW_P95_LIMIT_MS == 1_000.0
    assert module.TRANSITION_P95_LIMIT_MS == 100.0
    assert module.RSS_GROWTH_LIMIT_MIB == 100.0


def test_phase9b_benchmark_output_is_restricted_to_runtime() -> None:
    module = _load_script()
    allowed = module.RUNTIME_ROOT / "phase9b-test" / "benchmark.json"
    allowed.parent.mkdir(parents=True, exist_ok=True)
    assert module._prepare_output_path(allowed) == allowed.resolve()
    with pytest.raises(ValueError, match="repository runtime"):
        module._prepare_output_path(module.RUNTIME_ROOT.parent / "outside.json")


def test_phase9b_benchmark_percentile_uses_fixed_nearest_rank() -> None:
    module = _load_script()
    assert module._percentile([5.0, 1.0, 4.0, 2.0, 3.0], 0.95) == 4.0
