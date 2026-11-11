from __future__ import annotations

import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "scripts/phase17-background-benchmark.py"


async def test_short_background_benchmark_cannot_claim_full_soak():
    spec = importlib.util.spec_from_file_location("phase17_benchmark", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = await module.measure(cycles=2, enforce=True)
    assert result["passed"] is False and result["minimums_met"] is False
    assert result["simulation"]["oracle_matches"] == 1_000
    assert result["worker_incidents"]["actual_denials"] == 400
    assert result["soak"]["inbox_items"] == 1
    assert result["on_demand_core_passed"]
    assert result["rule_and_worker_plan_removed"] and result["temporary_state_deleted"]
    assert set(result["zero_activity"].values()) == {0}
