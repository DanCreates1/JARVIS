"""Explicit opt-in live Windows smoke for Phase 3 brokered adapters.

This is an acceptance harness, not a runtime approval surface. It refuses to run
unless the operator supplies an exact acknowledgement and a new disposable work
directory beneath repository ``runtime/``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from hmac import compare_digest
from pathlib import Path
from time import perf_counter
from typing import Final

from jarvis.computer.audio import get_master_volume_state
from jarvis.computer.config import (
    ApplicationPolicy,
    ComputerAccessConfigStore,
    ComputerAccessPolicy,
)
from jarvis.computer.runtime import ComputerRuntimeComponents, build_computer_runtime
from jarvis.config import Settings
from jarvis.core import PermissionLevel
from jarvis.permissions import (
    ActionCoordinatorStatus,
    ApprovalRequest,
    ApprovalSource,
    CanonicalAction,
    ExecutionReceipt,
    LocalCliApprovalSurface,
)

_ACKNOWLEDGEMENT: Final = "I AUTHORIZE DISPOSABLE PHASE 3 LIVE HOST EFFECTS"
_MEDIA_OPERATIONS: Final = ("stop",)
_ALLOWED_ACTION_IDS: Final = frozenset({"launch_application", "set_master_volume", "control_media"})
_FIXTURE_WAIT_SECONDS: Final = 8.0
_FIXTURE_MIN_SLEEP_SECONDS: Final = 1.95
_VOLUME_PRECONDITION_TOLERANCE: Final = 0.001
_VOLUME_NEAR_NOOP_MAX_DELTA: Final = 0.006


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Requires separate operator authorization and the exact acknowledgement: "
            f"{_ACKNOWLEDGEMENT}"
        ),
    )
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--acknowledgement", required=True)
    parser.add_argument("--app-fixture", action="store_true")
    parser.add_argument("--volume-current-rounded", action="store_true")
    parser.add_argument("--media-operation", choices=_MEDIA_OPERATIONS)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _repository_runtime() -> Path:
    repository = Path(__file__).resolve().parents[1]
    return (repository / "runtime").resolve(strict=True)


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    reparse_attribute = getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_attribute)


def _prepare_work_dir(path: Path) -> tuple[Path, Path]:
    runtime = _repository_runtime()
    repository = runtime.parent
    work_dir = (
        path.resolve(strict=False)
        if path.is_absolute()
        else (repository / path).resolve(strict=False)
    )
    if work_dir.parent != runtime:
        raise ValueError("work directory must be a new direct child of repository runtime/")
    if work_dir.exists():
        raise ValueError("work directory already exists; use a new disposable path")
    work_dir.mkdir(exist_ok=False)
    verified_work_dir = work_dir.resolve(strict=True)
    if verified_work_dir != work_dir or verified_work_dir.parent != runtime:
        raise ValueError("created work directory resolved outside repository runtime/")
    if not verified_work_dir.is_dir() or _is_reparse_point(verified_work_dir):
        raise ValueError("created work directory must be a normal local directory")
    controlled_root = work_dir / "controlled-files"
    controlled_root.mkdir(exist_ok=False)
    verified_controlled_root = controlled_root.resolve(strict=True)
    if (
        verified_controlled_root.parent != verified_work_dir
        or not verified_controlled_root.is_dir()
        or _is_reparse_point(verified_controlled_root)
    ):
        raise ValueError("controlled root must be a normal direct child of the work directory")
    return verified_work_dir, verified_controlled_root


def _prepare_output(work_dir: Path, requested: Path | None) -> Path:
    candidate = work_dir / "result.json" if requested is None else requested
    if not candidate.is_absolute():
        candidate = work_dir / candidate
    output = candidate.resolve(strict=False)
    if output.parent != work_dir or output.suffix.casefold() != ".json":
        raise ValueError("output must be one new JSON file directly beneath the work directory")
    if output.exists():
        raise ValueError("output already exists; refusing to overwrite evidence")
    return output


def _write_payload(output: Path, payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)


def _application_policy(controlled_root: Path) -> tuple[ApplicationPolicy, Path]:
    executable = Path(sys.executable).resolve(strict=True)
    if executable.suffix.casefold() != ".exe":
        raise RuntimeError("live application fixture requires a Windows Python .exe")
    marker = controlled_root / "app-fixture-marker.txt"
    code = (
        "import pathlib,time;"
        f"p=pathlib.Path({str(marker)!r});"
        "t=time.perf_counter();p.write_text('started',encoding='utf-8');time.sleep(2);"
        "p.write_text(f'completed:{time.perf_counter()-t:.6f}',encoding='utf-8')"
    )
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    return (
        ApplicationPolicy(
            executable=executable,
            sha256=digest,
            arguments=("-I", "-c", code),
            startup_timeout_seconds=5,
        ),
        marker,
    )


def _exact_phrase_matches(request: ApprovalRequest, phrase: str) -> bool:
    fingerprint = request.action.fingerprint
    if not fingerprint.startswith("sha256:"):
        return False
    expected = f"APPROVE {fingerprint.removeprefix('sha256:')[-16:]}"
    return compare_digest(phrase, expected)


def _sanitized_receipt(receipt: ExecutionReceipt) -> dict[str, object]:
    """Project only non-authority acceptance evidence into the harness output."""
    return {
        "outcome": receipt.outcome.value,
        "result_bytes": receipt.result_bytes,
        "postcondition_status": receipt.postcondition.status.value,
        "rollback_status": receipt.rollback.status.value,
    }


def _receipt_result(receipt: ExecutionReceipt) -> dict[str, object]:
    if not isinstance(receipt.result, dict):
        raise RuntimeError("live action returned a malformed result")
    return dict(receipt.result)


async def _run_action(
    components: ComputerRuntimeComponents,
    *,
    action_id: str,
    raw_arguments: dict[str, object],
    pre_dispatch_check: Callable[[CanonicalAction], None] | None = None,
) -> tuple[dict[str, object], float, ExecutionReceipt]:
    if action_id not in _ALLOWED_ACTION_IDS:
        raise RuntimeError("live harness action is outside its fixed acceptance scope")
    action = components.registry.action(action_id)
    if action is None:
        raise RuntimeError(f"fixed action is unavailable: {action_id}")
    arguments = action.input_model.model_validate(raw_arguments)
    proposal = await components.coordinator.propose(
        action,
        arguments,
        actor=components.actor,
        source=ApprovalSource.LOCAL_CLI,
        idempotency_key=f"live-{action_id}-{secrets.token_hex(12)}",
    )
    if proposal.status is not ActionCoordinatorStatus.PENDING or proposal.request is None:
        raise RuntimeError(f"proposal failed closed: {proposal.code or proposal.status.value}")
    if pre_dispatch_check is not None:
        pre_dispatch_check(proposal.request.action)
    exact_phrase_validated = False

    def explicitly_authorized(request: ApprovalRequest, phrase: str) -> bool:
        nonlocal exact_phrase_validated
        exact_phrase_validated = _exact_phrase_matches(request, phrase)
        return exact_phrase_validated

    surface = LocalCliApprovalSurface(
        approver=components.actor,
        prompt=explicitly_authorized,
    )
    approval = await components.coordinator.review(proposal.request.approval_id, surface)
    if approval.status is not ActionCoordinatorStatus.APPROVED or approval.grant_id is None:
        raise RuntimeError(f"approval failed closed: {approval.code or approval.status.value}")
    started = perf_counter()
    execution = await components.coordinator.execute(
        approval.grant_id,
        actor=components.actor,
    )
    latency_ms = (perf_counter() - started) * 1_000
    if execution.receipt is None:
        raise RuntimeError(f"execution produced no receipt: {execution.code or 'missing_receipt'}")
    receipt = execution.receipt
    if receipt.outcome.value != "succeeded":
        raise RuntimeError(
            f"live action failed closed: {receipt.error_code or receipt.outcome.value}"
        )
    return (
        {
            "action_id": action_id,
            "production_local_cli_surface_used": True,
            "exact_approval_phrase_validated": exact_phrase_validated,
            "receipt_evidence": _sanitized_receipt(receipt),
        },
        latency_ms,
        receipt,
    )


async def _wait_for_fixture_completion(marker: Path) -> float:
    deadline = asyncio.get_running_loop().time() + _FIXTURE_WAIT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        try:
            value = await asyncio.to_thread(marker.read_text, encoding="utf-8")
        except FileNotFoundError:
            value = ""
        if value.startswith("completed:"):
            try:
                elapsed = float(value.removeprefix("completed:"))
            except ValueError as error:
                raise RuntimeError("application fixture completion marker is malformed") from error
            if elapsed < _FIXTURE_MIN_SLEEP_SECONDS or elapsed > _FIXTURE_WAIT_SECONDS:
                raise RuntimeError("application fixture duration is outside its bounded window")
            return elapsed
        await asyncio.sleep(0.05)
    raise RuntimeError("application fixture did not complete within its bounded window")


def _requested_actions(args: argparse.Namespace) -> list[str]:
    requested: list[str] = []
    if args.app_fixture:
        requested.append("launch_application")
    if args.volume_current_rounded:
        requested.append("set_master_volume")
    if args.media_operation:
        requested.append("control_media")
    return requested


def _validate_authorization(args: argparse.Namespace) -> list[str]:
    if args.acknowledgement != _ACKNOWLEDGEMENT:
        raise ValueError(f"refusing host effects; exact acknowledgement is: {_ACKNOWLEDGEMENT}")
    requested = _requested_actions(args)
    if not requested:
        raise ValueError("select at least one explicit live action")
    if args.media_operation not in (None, "stop"):
        raise ValueError("live acceptance permits only one global media STOP input")
    return requested


async def _main() -> int:
    args = _arguments()
    if os.name != "nt":
        raise RuntimeError("live smoke requires Windows")
    requested_actions = _validate_authorization(args)

    work_dir, controlled_root = _prepare_work_dir(args.work_dir)
    output = _prepare_output(work_dir, args.output)
    applications: dict[str, ApplicationPolicy] = {}
    app_marker: Path | None = None
    if args.app_fixture:
        application, app_marker = _application_policy(controlled_root)
        applications["disposable_python_fixture"] = application

    policy = ComputerAccessPolicy(
        enabled=True,
        policy_version=f"phase3-live-{secrets.token_hex(12)}",
        maximum_permission_level=PermissionLevel.LEVEL_2,
        controlled_root=controlled_root,
        applications=applications,
        approval_ttl_seconds=120,
        grant_ttl_seconds=60,
    )
    ComputerAccessConfigStore(work_dir).save(policy)
    settings = Settings(data_dir=work_dir, computer_access_enabled=True)
    results: list[dict[str, object]] = []
    components: ComputerRuntimeComponents | None = None
    failed_action: str | None = None
    failure_type: str | None = None
    try:
        components = await build_computer_runtime(settings)
        if args.app_fixture:
            failed_action = "launch_application"
            result, latency, receipt = await _run_action(
                components,
                action_id="launch_application",
                raw_arguments={"application_id": "disposable_python_fixture"},
            )
            assert app_marker is not None
            effect = _receipt_result(receipt)
            if (
                effect.get("application_id") != "disposable_python_fixture"
                or effect.get("image_verified") is not True
            ):
                raise RuntimeError("application fixture image evidence did not match")
            fixture_duration = await _wait_for_fixture_completion(app_marker)
            result["latency_ms"] = round(latency, 3)
            result["fixture_image_verified"] = True
            result["fixture_completed"] = True
            result["fixture_duration_seconds"] = round(fixture_duration, 3)
            results.append(result)
            failed_action = None

        if args.volume_current_rounded:
            failed_action = "set_master_volume"
            before = get_master_volume_state()
            target_percent = round(before.scalar * 100)

            def require_near_noop_precondition(action: CanonicalAction) -> None:
                scalar = action.precondition.get("before_scalar")
                muted = action.precondition.get("before_muted")
                if isinstance(scalar, bool) or not isinstance(scalar, (int, float)):
                    raise RuntimeError("volume proposal precondition is malformed")
                proposal_scalar = float(scalar)
                if (
                    abs(proposal_scalar - before.scalar) > _VOLUME_PRECONDITION_TOLERANCE
                    or muted is not before.muted
                ):
                    raise RuntimeError("volume changed before approval; refusing live write")
                if abs(proposal_scalar - target_percent / 100) > 0.0050001:
                    raise RuntimeError("rounded volume target is not a near-no-op")

            result, latency, receipt = await _run_action(
                components,
                action_id="set_master_volume",
                raw_arguments={"percent": target_percent},
                pre_dispatch_check=require_near_noop_precondition,
            )
            after = get_master_volume_state()
            effect = _receipt_result(receipt)
            scalar_delta = abs(after.scalar - before.scalar)
            target_verified = abs(after.scalar - target_percent / 100) <= 0.001
            mute_unchanged = before.muted == after.muted
            if (
                effect.get("requested_percent") != target_percent
                or not target_verified
                or not mute_unchanged
                or scalar_delta > _VOLUME_NEAR_NOOP_MAX_DELTA
            ):
                raise RuntimeError("rounded volume postcondition evidence did not match")
            result["latency_ms"] = round(latency, 3)
            result["target_percent"] = target_percent
            result["absolute_scalar_delta"] = round(scalar_delta, 6)
            result["target_readback_verified"] = target_verified
            result["mute_unchanged"] = mute_unchanged
            results.append(result)
            failed_action = None

        if args.media_operation:
            failed_action = "control_media"
            result, latency, receipt = await _run_action(
                components,
                action_id="control_media",
                raw_arguments={"operation": "stop"},
            )
            effect = _receipt_result(receipt)
            input_pair_accepted = (
                effect.get("operation") == "stop"
                and effect.get("requested_count") == 2
                and effect.get("accepted_count") == 2
            )
            if not input_pair_accepted:
                raise RuntimeError("Windows did not accept the exact media STOP input pair")
            result["latency_ms"] = round(latency, 3)
            result["operation"] = "stop"
            result["windows_input_pair_accepted"] = input_pair_accepted
            result["playback_state_verified"] = False
            results.append(result)
            failed_action = None
    except Exception as error:
        failure_type = type(error).__name__
    finally:
        if components is not None:
            try:
                await components.close()
            except Exception as error:
                if failure_type is None:
                    failure_type = type(error).__name__
                    failed_action = "runtime_close"

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "passed" if failure_type is None else "failed",
        "operator_acknowledgement_validated": True,
        "requested_actions": requested_actions,
        "completed_action_count": len(results),
        "actions": results,
    }
    if failure_type is not None:
        payload["failure"] = {"action_id": failed_action, "type": failure_type}
    _write_payload(output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if failure_type is None else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
