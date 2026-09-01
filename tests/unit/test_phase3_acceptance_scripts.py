from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def _load_script(module_name: str, filename: str) -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


LIVE = _load_script("phase3_live_smoke_test_module", "phase3-live-smoke.py")
BENCHMARK = _load_script("phase3_benchmark_test_module", "phase3-benchmark.py")


def _fake_repository(monkeypatch: pytest.MonkeyPatch, module: ModuleType, tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(module, "__file__", str(scripts / "script.py"))
    return runtime


def _live_arguments(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "acknowledgement": LIVE._ACKNOWLEDGEMENT,
        "app_fixture": False,
        "volume_current_rounded": False,
        "media_operation": "stop",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_live_authorization_is_exact_and_stop_only() -> None:
    assert LIVE._validate_authorization(_live_arguments()) == ["control_media"]
    with pytest.raises(ValueError, match="exact acknowledgement"):
        LIVE._validate_authorization(_live_arguments(acknowledgement="approve"))
    with pytest.raises(ValueError, match="only one global media STOP"):
        LIVE._validate_authorization(_live_arguments(media_operation="play_pause"))
    with pytest.raises(ValueError, match="at least one"):
        LIVE._validate_authorization(_live_arguments(media_operation=None))


def test_live_paths_require_new_direct_runtime_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _fake_repository(monkeypatch, LIVE, tmp_path)
    with pytest.raises(ValueError, match="direct child"):
        LIVE._prepare_work_dir(runtime / "nested" / "work")

    existing = runtime / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        LIVE._prepare_work_dir(existing)

    work_dir, controlled_root = LIVE._prepare_work_dir(runtime / "fresh")
    assert work_dir == (runtime / "fresh").resolve(strict=True)
    assert controlled_root == (work_dir / "controlled-files").resolve(strict=True)

    output = LIVE._prepare_output(work_dir, None)
    LIVE._write_payload(output, {"status": "passed"})
    with pytest.raises(FileExistsError):
        LIVE._write_payload(output, {"status": "overwritten"})
    with pytest.raises(ValueError, match="directly beneath"):
        LIVE._prepare_output(work_dir, Path("nested/result.json"))


def test_live_exact_phrase_and_receipt_projection_omit_authority() -> None:
    fingerprint = "sha256:" + "a" * 64
    request = SimpleNamespace(action=SimpleNamespace(fingerprint=fingerprint))
    assert LIVE._exact_phrase_matches(request, f"APPROVE {'a' * 16}")
    assert not LIVE._exact_phrase_matches(request, f"APPROVE {'b' * 16}")

    receipt = SimpleNamespace(
        outcome=SimpleNamespace(value="succeeded"),
        result_bytes=12,
        postcondition=SimpleNamespace(status=SimpleNamespace(value="passed")),
        rollback=SimpleNamespace(status=SimpleNamespace(value="not_needed")),
        actor={"private": "actor"},
        action_fingerprint=fingerprint,
        result={"pid": 123},
    )
    projection = LIVE._sanitized_receipt(receipt)
    assert projection == {
        "outcome": "succeeded",
        "result_bytes": 12,
        "postcondition_status": "passed",
        "rollback_status": "not_needed",
    }
    assert not {"actor", "action_fingerprint", "result"}.intersection(projection)


@pytest.mark.asyncio
async def test_fixture_completion_requires_bounded_two_second_evidence(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    marker.write_text("completed:2.001", encoding="utf-8")
    assert await LIVE._wait_for_fixture_completion(marker) == pytest.approx(2.001)
    marker.write_text("completed:0.100", encoding="utf-8")
    with pytest.raises(RuntimeError, match="bounded window"):
        await LIVE._wait_for_fixture_completion(marker)


def test_benchmark_paths_and_counts_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _fake_repository(monkeypatch, BENCHMARK, tmp_path)
    args = argparse.Namespace(
        validation_samples=700,
        dispatch_samples=250,
        move_round_trips=24,
    )
    BENCHMARK.validate_counts(args)
    for field, value in (
        ("validation_samples", 10_001),
        ("dispatch_samples", 5_001),
        ("move_round_trips", 201),
    ):
        invalid = argparse.Namespace(**vars(args))
        setattr(invalid, field, value)
        with pytest.raises(ValueError, match="between"):
            BENCHMARK.validate_counts(invalid)

    rejected_work_dir = runtime / "rejected-output"
    with pytest.raises(ValueError, match="directly beneath"):
        BENCHMARK.resolve_disposable_paths(
            rejected_work_dir,
            Path("nested/evidence.json"),
        )
    assert not rejected_work_dir.exists()

    work_dir, output = BENCHMARK.resolve_disposable_paths(
        runtime / "benchmark-fresh",
        Path("evidence.json"),
    )
    assert work_dir.parent == runtime
    assert output == work_dir / "evidence.json"
    BENCHMARK._write_report_exclusive(output, b"{}\n")
    with pytest.raises(FileExistsError):
        BENCHMARK._write_report_exclusive(output, b"{}\n")

    assert BENCHMARK.benchmark_definition().tool.max_result_items == 2


def test_benchmark_thresholds_require_complete_sample_accounting() -> None:
    permission = {
        "samples": 700,
        "measured_samples": 700,
        "p95_ms": 1.0,
        "invalid_false_accept_count": 0,
        "valid_control_failures": 0,
        "unexpected_effect_count": 0,
    }
    dispatch = {
        "samples": 250,
        "measured_samples": 250,
        "p95_ms": 1.0,
        "expected_effect_count": 250,
        "observed_effect_count": 250,
        "duplicate_effect_count": 0,
        "duplicate_receipt_failures": 0,
        "audit_event_count": 500,
    }
    moves = {
        "samples": 24,
        "completed_round_trips": 24,
        "successful_broker_moves": 24,
        "verified_postconditions": 24,
        "successful_rollbacks": 24,
        "escape_attempt_refused": True,
        "remaining_destination_files": 0,
        "unauthorized_effect_count": 0,
    }
    failures = BENCHMARK.FailureLog()
    assert all(BENCHMARK.thresholds(permission, dispatch, moves, failures).values())

    dispatch["measured_samples"] = 249
    checks = BENCHMARK.thresholds(permission, dispatch, moves, failures)
    assert not checks["dispatch_complete_accounting"]
