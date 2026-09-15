from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_benchmark() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase11d-long-duration-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase11d_long_duration_benchmark", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase11d_small_run_proves_oracle_incident_removal_and_core_boundaries() -> None:
    result = asyncio.run(
        _load_benchmark()._measure(
            virtual_days=2,
            decision_samples=20,
            incident_samples=12,
            soak_seconds=0,
            soak_cycles=5,
            soak_interval_seconds=0,
        )
    )

    assert result["passed"] is True
    assert result["simulation"]["oracle_agreement"] == 1.0
    assert result["simulation"]["useful_precision"] == 1.0
    assert result["simulation"]["useful_recall"] == 1.0
    assert result["simulation"]["false_proactivity"] == 0
    assert result["incidents_and_removal"]["incident_failures"] == 0
    assert result["incidents_and_removal"]["forbidden_explanation_fields"] == []
    assert result["incidents_and_removal"]["rule_state_removed"] is True
    assert result["incidents_and_removal"]["content_free_tombstone"] is True
    assert result["incidents_and_removal"]["on_demand_core_passed"] is True
    assert result["temporary_evaluation_state_deleted"] is True
    assert all(value == 0 for value in result["zero_activity"].values())


def test_phase11d_enforcement_cannot_pass_a_shortened_run() -> None:
    result = asyncio.run(
        _load_benchmark()._measure(
            virtual_days=2,
            decision_samples=20,
            incident_samples=12,
            soak_seconds=0,
            soak_cycles=5,
            soak_interval_seconds=0,
            enforce_minimums=True,
        )
    )

    assert result["minimums_met"] is False
    assert result["passed"] is False


def test_phase11d_output_is_confined_to_ignored_runtime() -> None:
    module = _load_benchmark()

    with pytest.raises(ValueError, match="runtime"):
        module._prepare_output_path(Path(__file__).resolve())
