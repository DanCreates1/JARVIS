from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from jarvis.core import SensitivityClass
from jarvis.llm import PrivacyGate


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase1-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase1_benchmark_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["phase1_benchmark_test_module"] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = _load_script()


def _arguments(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "profiles": ["deterministic", "local"],
        "samples": 20,
        "warmups": 1,
        "local_model": "qwen3:0.6b",
        "hosted_model": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "include_hosted": False,
        "confirm_public_fixtures": False,
        "hosted_min_interval_seconds": 2.1,
        "nvidia_reasoning_matrix": False,
        "nvidia_reasoning_budgets": [64, 128, 256],
        "nvidia_matrix_samples": 20,
        "enforce": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _sample(index: int, *, provider: str = "deterministic") -> dict[str, object]:
    return {
        "fixture_id": f"sample-{index:03d}",
        "successful_useful_response": True,
        "expected_route_success": provider == "deterministic",
        "first_useful_output_ms": float(index),
        "total_completion_ms": float(index + 1),
        "output_bytes": 10,
        "actual_provider": provider,
        "input_tokens": 1,
        "answer_quality_pass": True,
        "provider_latency_phases_ms": None,
    }


def test_nearest_rank_quantiles_are_not_interpolated() -> None:
    values = [float(index) for index in range(1, 21)]
    assert BENCHMARK.nearest_rank(values, 0.50) == 10.0
    assert BENCHMARK.nearest_rank(values, 0.95) == 19.0
    assert BENCHMARK.nearest_rank([], 0.95) is None
    with pytest.raises(ValueError, match="quantile"):
        BENCHMARK.nearest_rank(values, 0)


def test_validation_enforces_sample_floor_and_explicit_hosted_consent() -> None:
    BENCHMARK.validate_args(_arguments())
    with pytest.raises(ValueError, match="samples"):
        BENCHMARK.validate_args(_arguments(samples=19))
    with pytest.raises(ValueError, match="hosted profiles"):
        BENCHMARK.validate_args(_arguments(profiles=["hosted-complex"]))
    with pytest.raises(ValueError, match=r"2\.1-second"):
        BENCHMARK.validate_args(
            _arguments(
                profiles=["hosted-complex"],
                include_hosted=True,
                confirm_public_fixtures=True,
                hosted_min_interval_seconds=2.0,
            )
        )
    with pytest.raises(ValueError, match="exactly budgets"):
        BENCHMARK.validate_args(
            _arguments(
                nvidia_reasoning_matrix=True,
                nvidia_reasoning_budgets=[64, 256],
                include_hosted=True,
                confirm_public_fixtures=True,
            )
        )
    with pytest.raises(ValueError, match="matrix-samples"):
        BENCHMARK.validate_args(_arguments(nvidia_matrix_samples=0))


def test_paths_require_new_direct_runtime_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(BENCHMARK, "__file__", str(scripts / "phase1-benchmark.py"))

    with pytest.raises(ValueError, match="direct child"):
        BENCHMARK.resolve_paths(runtime / "nested" / "work", Path("report.json"))

    existing = runtime / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="already exist"):
        BENCHMARK.resolve_paths(existing, Path("report.json"))

    work_dir, output = BENCHMARK.resolve_paths(runtime / "fresh", Path("report.json"))
    assert work_dir == (runtime / "fresh").resolve(strict=True)
    assert output == work_dir / "report.json"


def test_state_summary_requires_all_samples_and_expected_route() -> None:
    passing = [_sample(index) for index in range(1, 21)]
    summary = BENCHMARK.summarize_state("deterministic", "steady", passing)
    assert summary["sample_count"] == 20
    assert summary["successful_response_count"] == 20
    assert summary["first_useful_output_ms"]["nearest_rank_p50"] == 10.0
    assert summary["first_useful_output_ms"]["nearest_rank_p95"] == 19.0
    assert summary["uncertainty"]["tail_observations_at_or_above_p95_rank"] == 2
    assert summary["threshold_pass"] is True

    fallback = [*passing[:-1], _sample(20, provider="ollama")]
    failed = BENCHMARK.summarize_state("deterministic", "steady", fallback)
    assert failed["failure_count"] == 1
    assert failed["actual_provider_counts"] == {"deterministic": 19, "ollama": 1}
    assert failed["threshold_pass"] is False


def test_state_summary_keeps_provider_ttft_and_visible_ttft_separate() -> None:
    samples = [_sample(index) for index in range(1, 21)]
    for index, sample in enumerate(samples, start=1):
        sample["provider_latency_phases_ms"] = {
            "request_start_ms": 0,
            "response_headers_ms": float(index * 10),
            "first_sse_frame_ms": float(index * 10 + 1),
            "first_visible_token_ms": float(index * 10 + 2),
            "completion_ms": float(index * 10 + 3),
        }
        sample["conversation_message_count"] = 2
        sample["supplied_tool_schema_count"] = index % 2
        sample["reasoning_budget_tokens"] = 64

    summary = BENCHMARK.summarize_state("deterministic", "steady", samples)

    assert summary["provider_ttft_ms"]["nearest_rank_p95"] == 191.0
    assert summary["provider_visible_ttft_ms"]["nearest_rank_p95"] == 192.0
    phases = summary["provider_latency_phase_summary_ms"]
    assert phases["response_headers_ms"]["nearest_rank_p95"] == 190.0
    assert phases["completion_ms"]["nearest_rank_p95"] == 193.0
    assert summary["reasoning_budget_tokens_observed"] == [64]


def test_fixed_fixtures_are_bounded_and_report_writer_is_exclusive(tmp_path: Path) -> None:
    fixture_groups = (
        BENCHMARK.DETERMINISTIC_PROMPTS,
        BENCHMARK.LOCAL_PROMPTS,
        BENCHMARK.HOSTED_SIMPLE_PROMPTS,
        BENCHMARK.HOSTED_COMPLEX_PROMPTS,
    )
    assert all(
        group and all(0 < len(prompt) <= 500 for prompt in group) for group in fixture_groups
    )
    gate = PrivacyGate()
    assert all(
        gate.classify(prompt) is SensitivityClass.PUBLIC
        for prompt in (*BENCHMARK.HOSTED_SIMPLE_PROMPTS, *BENCHMARK.HOSTED_COMPLEX_PROMPTS)
    )
    fixture = BENCHMARK._fixture(BENCHMARK.HOSTED_SIMPLE_PROMPTS, "public", 0)
    assert fixture.fixture_id == "public-001"
    assert len(BENCHMARK._prompt_hash(fixture.prompt)) == 64

    output = tmp_path / "report.json"
    BENCHMARK._write_report_exclusive(output, {"prompt_or_response_content_written": False})
    with pytest.raises(FileExistsError):
        BENCHMARK._write_report_exclusive(output, {})


def test_disposition_never_converts_routing_mitigation_into_nvidia_pass() -> None:
    passing_state = {
        "threshold_pass": True,
        "successful_response_count": 20,
        "failure_count": 0,
    }
    failing_state = {**passing_state, "threshold_pass": False}
    report = {
        "profiles": {
            "deterministic": {"states": [passing_state]},
            "local": {"states": [passing_state, passing_state]},
            "hosted-simple": {"states": [failing_state, failing_state]},
            "hosted-complex": {"states": [failing_state, failing_state]},
        }
    }

    assert (
        BENCHMARK.phase1_disposition(
            report,
            external_closure_permitted=False,
            jarvis_controlled_work_complete=True,
            product_responsiveness_protected=True,
        )
        == BENCHMARK.PHASE1_BLOCKED
    )
    assert (
        BENCHMARK.phase1_disposition(
            report,
            external_closure_permitted=True,
            jarvis_controlled_work_complete=True,
            product_responsiveness_protected=True,
        )
        == BENCHMARK.PHASE1_EXTERNAL_LIMITATION
    )
    for profile in report["profiles"].values():
        for state in profile["states"]:
            state["threshold_pass"] = True
    assert (
        BENCHMARK.phase1_disposition(
            report,
            external_closure_permitted=False,
            jarvis_controlled_work_complete=True,
            product_responsiveness_protected=True,
        )
        == BENCHMARK.PHASE1_PASS
    )

    del report["profiles"]["local"]
    assert (
        BENCHMARK.phase1_disposition(
            report,
            external_closure_permitted=True,
            jarvis_controlled_work_complete=True,
            product_responsiveness_protected=True,
        )
        == BENCHMARK.PHASE1_BLOCKED
    )
