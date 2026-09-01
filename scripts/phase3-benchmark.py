"""Bounded local benchmark for Phase 3 permission, broker, and reversible-file paths."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import secrets
import stat
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ValidationError

from jarvis.broker import LocalActionBroker
from jarvis.computer.actions import (
    PreparedAction,
    ReversibleMoveArguments,
    ReversibleMoveHandler,
    prepare_action,
)
from jarvis.computer.config import ComputerAccessPolicy
from jarvis.core import (
    ApprovalRule,
    PermissionLevel,
    SensitivityClass,
    ToolConcurrency,
    ToolDefinition,
    ToolIdempotency,
    ToolRetryPolicy,
    ToolRisk,
    ToolSideEffect,
)
from jarvis.permissions import (
    ActionAuditEvent,
    ActionDefinition,
    ActionEffect,
    ActorContext,
    ApprovalDecision,
    ApprovalGrant,
    ApprovalRequest,
    ApprovalSource,
    AuthenticationAssurance,
    CanonicalAction,
    ExecutionOutcome,
    ExecutionReceipt,
    InteractionInterface,
    PermissionEngine,
    PolicyDisposition,
    PostconditionEvidence,
    PostconditionStatus,
    RollbackReceipt,
    RollbackStatus,
    SQLiteActionStore,
)

POLICY_VERSION: Final = "phase3-benchmark-v1"
PERMISSION_P95_TARGET_MS: Final = 25.0
BROKER_P95_TARGET_MS: Final = 50.0
MAX_OUTPUT_BYTES: Final = 100 * 1024
MAX_FAILURES: Final = 50
MAX_VALIDATION_SAMPLES: Final = 10_000
MAX_DISPATCH_SAMPLES: Final = 5_000
MAX_MOVE_ROUND_TRIPS: Final = 200


class FailureLog:
    def __init__(self) -> None:
        self._items: list[dict[str, str | int]] = []
        self.total = 0

    def add(self, stage: str, sample: int, error: BaseException | str) -> None:
        self.total += 1
        if len(self._items) >= MAX_FAILURES:
            return
        self._items.append(
            {
                "stage": stage,
                "sample": sample,
                "error": error if isinstance(error, str) else type(error).__name__,
            }
        )

    @property
    def items(self) -> list[dict[str, str | int]]:
        return list(self._items)


class MemoryActionState:
    """Minimal in-process production-port implementation for overhead isolation."""

    def __init__(self, *, reject_claims: bool = False) -> None:
        self.reject_claims = reject_claims
        self.receipts: dict[str, ExecutionReceipt] = {}
        self.claimed_grants: set[str] = set()
        self.claimed_keys: set[str] = set()
        self.claim_calls = 0
        self._lock = asyncio.Lock()

    async def get_receipt(self, idempotency_key: str) -> ExecutionReceipt | None:
        return self.receipts.get(idempotency_key)

    async def claim_grant(self, grant: ApprovalGrant, *, claimed_at: datetime) -> bool:
        del claimed_at
        async with self._lock:
            self.claim_calls += 1
            if self.reject_claims:
                return False
            if (
                grant.grant_id in self.claimed_grants
                or grant.action.idempotency_key in self.claimed_keys
            ):
                return False
            self.claimed_grants.add(grant.grant_id)
            self.claimed_keys.add(grant.action.idempotency_key)
            return True

    async def complete_grant(
        self,
        grant: ApprovalGrant,
        receipt: ExecutionReceipt,
    ) -> None:
        self.receipts[grant.action.idempotency_key] = receipt


class MemoryActionAudit:
    def __init__(self) -> None:
        self.events: list[ActionAuditEvent] = []

    async def append_action_event(self, event: ActionAuditEvent) -> None:
        self.events.append(event)


class FakeBenchmarkHandler:
    def __init__(self, definition: ActionDefinition) -> None:
        self._definition = definition
        self.execute_count = 0

    @property
    def definition(self) -> ActionDefinition:
        return self._definition

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        self.execute_count += 1
        return ActionEffect(
            result={"request_id": action.request_id, "accepted": True},
            rollback_context=None,
        )

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        passed = (
            effect is not None
            and isinstance(effect.result, dict)
            and effect.result.get("request_id") == action.request_id
        )
        return PostconditionEvidence(
            status=PostconditionStatus.PASSED if passed else PostconditionStatus.MISMATCH,
            summary="Fake fixed-adapter postcondition was checked.",
        )

    async def rollback(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
        *,
        reason: str,
    ) -> RollbackReceipt:
        del action, effect, reason
        return RollbackReceipt(
            status=RollbackStatus.UNAVAILABLE,
            summary="Fake benchmark adapter has no external effect to roll back.",
        )


class CapturingMoveHandler:
    """Delegate to the production move handler while retaining isolated rollback evidence."""

    def __init__(self, handler: ReversibleMoveHandler) -> None:
        self._handler = handler
        self.effects: dict[str, ActionEffect] = {}

    @property
    def definition(self) -> ActionDefinition:
        return self._handler.definition

    @property
    def input_model(self) -> type[BaseModel]:
        return self._handler.input_model

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        return self._handler.prepare(arguments)

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        effect = await self._handler.execute(action)
        self.effects[action.request_id] = effect
        return effect

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        return await self._handler.verify(action, effect)

    async def rollback(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
        *,
        reason: str,
    ) -> RollbackReceipt:
        return await self._handler.rollback(action, effect, reason=reason)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run bounded Phase 3 local permission and reversible-action benchmarks."
    )
    parser.add_argument("--work-dir", type=Path, default=Path("runtime/phase3-benchmark"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-samples", type=int, default=700)
    parser.add_argument("--dispatch-samples", type=int, default=250)
    parser.add_argument("--move-round-trips", type=int, default=24)
    parser.add_argument("--enforce", action="store_true")
    return parser.parse_args()


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def resolve_disposable_paths(work_dir_arg: Path, output_arg: Path) -> tuple[Path, Path]:
    repository = _repository_root()
    runtime_root = (repository / "runtime").resolve(strict=True)
    work_dir = (
        work_dir_arg.resolve(strict=False)
        if work_dir_arg.is_absolute()
        else (repository / work_dir_arg).resolve(strict=False)
    )
    if work_dir.parent != runtime_root:
        raise ValueError("--work-dir must be a new direct child of repository runtime/")
    output = (
        output_arg.resolve(strict=False)
        if output_arg.is_absolute()
        else (work_dir / output_arg).resolve(strict=False)
    )
    if output.parent != work_dir or output.suffix.casefold() != ".json":
        raise ValueError("--output must be one JSON file directly beneath --work-dir")
    if work_dir.exists():
        raise ValueError("--work-dir must not already exist")
    work_dir.mkdir(exist_ok=False)
    verified_work_dir = work_dir.resolve(strict=True)
    if (
        verified_work_dir != work_dir
        or verified_work_dir.parent != runtime_root
        or not verified_work_dir.is_dir()
        or _is_reparse_point(verified_work_dir)
    ):
        raise ValueError("created work directory is not a normal repository runtime child")

    if output.parent != verified_work_dir:
        raise ValueError("verified output escaped the disposable work directory")
    if output.exists():
        raise ValueError("--output must not already exist")
    return verified_work_dir, output


def validate_counts(args: argparse.Namespace) -> None:
    if not 500 <= args.validation_samples <= MAX_VALIDATION_SAMPLES:
        raise ValueError(f"--validation-samples must be between 500 and {MAX_VALIDATION_SAMPLES}")
    if not 200 <= args.dispatch_samples <= MAX_DISPATCH_SAMPLES:
        raise ValueError(f"--dispatch-samples must be between 200 and {MAX_DISPATCH_SAMPLES}")
    if not 20 <= args.move_round_trips <= MAX_MOVE_ROUND_TRIPS:
        raise ValueError(f"--move-round-trips must be between 20 and {MAX_MOVE_ROUND_TRIPS}")


def benchmark_definition() -> ActionDefinition:
    return ActionDefinition(
        tool=ToolDefinition(
            name="benchmark_fixed_action",
            version="1",
            description="In-process fixed adapter used only to measure broker overhead.",
            input_schema={
                "type": "object",
                "properties": {"sample": {"type": "integer"}},
                "required": ["sample"],
                "additionalProperties": False,
            },
            permission_level=PermissionLevel.LEVEL_2,
            approval_rule=ApprovalRule.POLICY_OR_EXPLICIT,
            risk=ToolRisk.REVERSIBLE,
            side_effect=ToolSideEffect.REVERSIBLE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.benchmark",),
            timeout_seconds=1,
            max_result_bytes=2_048,
            max_result_items=2,
            idempotency=ToolIdempotency.IDEMPOTENCY_KEY,
            retry_policy=ToolRetryPolicy.RECONCILE_FIRST,
            concurrency=ToolConcurrency.SERIAL_PER_SESSION,
            postcondition="The fake adapter returns the exact request identifier.",
            recovery="No external effect exists; reconciliation checks the fake receipt.",
        ),
        supports_rollback=False,
        rollback_timeout_seconds=1,
    )


def benchmark_actor(
    now: datetime, *, host: str = "benchmark-host", session: str = "session-1"
) -> ActorContext:
    return ActorContext(
        host_id=host,
        session_id=session,
        device_id="device-1",
        interface=InteractionInterface.TEST,
        assurance=AuthenticationAssurance.LOCAL_SESSION,
        authenticated_at=now,
        capabilities=("computer.benchmark",),
    )


def build_action(
    definition: ActionDefinition,
    actor: ActorContext,
    now: datetime,
    sample: int,
    *,
    action_id: str | None = None,
    expired: bool = False,
) -> CanonicalAction:
    created_at = now - timedelta(minutes=4) if expired else now
    expires_at = now - timedelta(minutes=1) if expired else now + timedelta(minutes=10)
    return CanonicalAction.create(
        request_id=f"request-{sample}",
        action_id=action_id or definition.action_id,
        action_version=definition.version,
        actor=actor,
        normalized_arguments={"sample": sample},
        permission_level=definition.tool.permission_level,
        approval_rule=definition.tool.approval_rule,
        policy_version=POLICY_VERSION,
        idempotency_key=f"idempotency-{sample}",
        human_effect="Apply one in-process benchmark effect.",
        recovery_limits="No external resource is touched by the fake benchmark adapter.",
        precondition={"sample": sample},
        created_at=created_at,
        expires_at=expires_at,
    )


def build_grant(
    action: CanonicalAction, now: datetime, sample: int, *, expired: bool = False
) -> ApprovalGrant:
    issued_at = now - timedelta(minutes=2) if expired else now
    expires_at = now - timedelta(minutes=1) if expired else now + timedelta(minutes=5)
    return ApprovalGrant.create(
        grant_id=f"grant-{sample}",
        approval_id=f"approval-{sample}",
        action=action,
        approved_by=action.actor,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=f"nonce-{sample}",
    )


async def benchmark_permission_validation(
    samples: int,
    *,
    failures: FailureLog,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    definition = benchmark_definition()
    current_actor = benchmark_actor(now)
    state = MemoryActionState(reject_claims=True)
    audit = MemoryActionAudit()
    handler = FakeBenchmarkHandler(definition)
    broker = LocalActionBroker(
        [handler],
        state_store=state,
        audit_store=audit,
        policy_version=POLICY_VERSION,
        now=lambda: now,
    )
    engine = PermissionEngine(policy_version=POLICY_VERSION, now=lambda: now)
    categories = (
        "valid_control",
        "expired",
        "replay",
        "cross_session",
        "wrong_host",
        "mutated",
        "wrong_action",
    )
    cases: list[tuple[str, ApprovalGrant, ActorContext]] = []
    for sample in range(samples + 20):
        category = categories[sample % len(categories)]
        expired = category == "expired"
        action = build_action(definition, current_actor, now, sample, expired=expired)
        grant = build_grant(action, now, sample, expired=expired)
        execution_actor = current_actor
        if category == "cross_session":
            execution_actor = benchmark_actor(now, session="session-other")
        elif category == "wrong_host":
            execution_actor = benchmark_actor(now, host="benchmark-host-other")
        elif category == "mutated":
            mutated_action = action.model_copy(
                update={"normalized_arguments": {"sample": sample + 1}}
            )
            grant = grant.model_copy(update={"action": mutated_action})
        elif category == "wrong_action":
            wrong_action = build_action(
                definition,
                current_actor,
                now,
                sample,
                action_id="benchmark_unregistered_action",
            )
            grant = build_grant(wrong_action, now, sample)
        cases.append((category, grant, execution_actor))

    for _category, grant, execution_actor in cases[:20]:
        await engine.decide(
            action=grant.action,
            definition=definition,
            actor=execution_actor,
        )
        await broker.execute(grant, actor=execution_actor)

    latencies: list[float] = []
    by_category: dict[str, list[float]] = defaultdict(list)
    false_accepts: dict[str, int] = {
        category: 0 for category in categories if category != "valid_control"
    }
    valid_control_failures = 0
    handler_baseline = handler.execute_count
    for index, (category, grant, execution_actor) in enumerate(cases[20:], start=1):
        before_claims = state.claim_calls
        before_effects = handler.execute_count
        started = time.perf_counter_ns()
        try:
            policy = await engine.decide(
                action=grant.action,
                definition=definition,
                actor=execution_actor,
            )
            receipt = await broker.execute(grant, actor=execution_actor)
        except Exception as error:
            failures.add("permission_validation", index, error)
            continue
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000
        latencies.append(latency_ms)
        by_category[category].append(latency_ms)
        effect_delta = handler.execute_count - before_effects
        if category == "valid_control":
            reached_exact_claim = state.claim_calls == before_claims + 1
            if (
                policy.disposition is PolicyDisposition.DENY
                or receipt.error_code != "grant_replayed"
                or not reached_exact_claim
                or effect_delta != 0
            ):
                valid_control_failures += 1
        elif receipt.outcome is not ExecutionOutcome.DENIED or effect_delta != 0:
            false_accepts[category] += 1

    return {
        "samples": samples,
        "measured_samples": len(latencies),
        "warmup_samples": 20,
        "p50_ms": rounded_percentile(latencies, 0.50),
        "p95_ms": rounded_percentile(latencies, 0.95),
        "p95_target_ms": PERMISSION_P95_TARGET_MS,
        "category_p95_ms": {
            category: rounded_percentile(values, 0.95)
            for category, values in sorted(by_category.items())
        },
        "invalid_false_accepts": false_accepts,
        "invalid_false_accept_count": sum(false_accepts.values()),
        "valid_control_failures": valid_control_failures,
        "unexpected_effect_count": handler.execute_count - handler_baseline,
    }


async def benchmark_fake_dispatch(
    samples: int,
    *,
    failures: FailureLog,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    definition = benchmark_definition()
    current_actor = benchmark_actor(now)
    state = MemoryActionState()
    audit = MemoryActionAudit()
    handler = FakeBenchmarkHandler(definition)
    broker = LocalActionBroker(
        [handler],
        state_store=state,
        audit_store=audit,
        policy_version=POLICY_VERSION,
        now=lambda: now,
    )
    grants = [
        build_grant(
            build_action(definition, current_actor, now, 100_000 + sample),
            now,
            100_000 + sample,
        )
        for sample in range(samples + 10)
    ]
    for grant in grants[:10]:
        await broker.execute(grant, actor=current_actor)
        await broker.execute(grant, actor=current_actor)

    baseline_effects = handler.execute_count
    latencies: list[float] = []
    duplicate_receipt_failures = 0
    for index, grant in enumerate(grants[10:], start=1):
        started = time.perf_counter_ns()
        try:
            receipt = await broker.execute(grant, actor=current_actor)
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            duplicate = await broker.execute(grant, actor=current_actor)
        except Exception as error:
            failures.add("fake_broker_dispatch", index, error)
            continue
        latencies.append(latency_ms)
        if receipt.outcome is not ExecutionOutcome.SUCCEEDED or duplicate != receipt:
            duplicate_receipt_failures += 1

    expected_effects = samples
    observed_effects = handler.execute_count - baseline_effects
    return {
        "samples": samples,
        "measured_samples": len(latencies),
        "warmup_samples": 10,
        "p50_ms": rounded_percentile(latencies, 0.50),
        "p95_ms": rounded_percentile(latencies, 0.95),
        "p95_target_ms": BROKER_P95_TARGET_MS,
        "expected_effect_count": expected_effects,
        "observed_effect_count": observed_effects,
        "duplicate_effect_count": max(0, observed_effects - expected_effects),
        "duplicate_receipt_failures": duplicate_receipt_failures,
        "audit_event_count": max(0, len(audit.events) - 20),
    }


async def benchmark_reversible_moves(
    work_dir: Path,
    samples: int,
    *,
    failures: FailureLog,
) -> dict[str, Any]:
    controlled_root = (work_dir / "controlled-files").resolve(strict=False)
    incoming = controlled_root / "incoming"
    archive = controlled_root / "archive"
    incoming.mkdir(parents=True, exist_ok=False)
    archive.mkdir()
    policy = ComputerAccessPolicy(
        enabled=True,
        policy_version=POLICY_VERSION,
        maximum_permission_level=PermissionLevel.LEVEL_2,
        controlled_root=controlled_root,
        max_file_bytes=1_048_576,
    )
    handler = CapturingMoveHandler(ReversibleMoveHandler(policy))
    actor = ActorContext(
        host_id="benchmark-host",
        session_id="move-session",
        device_id="benchmark-device",
        interface=InteractionInterface.LOCAL_CLI,
        assurance=AuthenticationAssurance.LOCAL_SESSION,
        authenticated_at=datetime.now(UTC),
        capabilities=("computer.files.move",),
    )
    database_path = work_dir / "phase3-benchmark.db"
    store = SQLiteActionStore(database_path)
    await store.initialize()
    broker = LocalActionBroker(
        [handler],
        state_store=store,
        audit_store=store,
        policy_version=POLICY_VERSION,
    )
    latencies: list[float] = []
    successful_moves = 0
    verified_postconditions = 0
    successful_rollbacks = 0
    escape_refused = False
    unauthorized_effects = 0
    try:
        try:
            prepare_action(
                handler,
                {"source": "../escape.txt", "destination": "archive/escape.txt"},
            )
        except (ValidationError, ValueError):
            escape_refused = True
        if (work_dir / "escape.txt").exists():
            unauthorized_effects += 1

        for index in range(samples):
            source_relative = f"incoming/sample-{index:03d}.txt"
            destination_relative = f"archive/sample-{index:03d}.txt"
            source = controlled_root / source_relative
            destination = controlled_root / destination_relative
            content = f"Phase 3 reversible benchmark sample {index}.\n".encode()
            source.write_bytes(content)
            action: CanonicalAction | None = None
            effect: ActionEffect | None = None
            started = time.perf_counter_ns()
            try:
                prepared = prepare_action(
                    handler,
                    ReversibleMoveArguments(
                        source=source_relative,
                        destination=destination_relative,
                    ),
                )
                now = datetime.now(UTC)
                action = CanonicalAction.create(
                    request_id=f"move-request-{index}-{secrets.token_hex(8)}",
                    action_id=handler.definition.action_id,
                    action_version=handler.definition.version,
                    actor=actor,
                    normalized_arguments=prepared.normalized_arguments,
                    permission_level=handler.definition.tool.permission_level,
                    approval_rule=handler.definition.tool.approval_rule,
                    policy_version=POLICY_VERSION,
                    idempotency_key=f"move-idempotency-{index}-{secrets.token_hex(8)}",
                    human_effect=prepared.human_effect,
                    recovery_limits=prepared.recovery_limits,
                    precondition=prepared.precondition,
                    created_at=now,
                    expires_at=now + timedelta(minutes=5),
                )
                request = ApprovalRequest(
                    approval_id=f"move-approval-{index}-{secrets.token_hex(8)}",
                    action=action,
                    requested_at=now,
                    expires_at=now + timedelta(minutes=2),
                )
                await store.create_approval_request(
                    request,
                    source=ApprovalSource.LOCAL_CLI,
                    risk=handler.definition.tool.risk,
                    rule_id="benchmark_exact_approval",
                )
                decision = ApprovalDecision(
                    approval_id=request.approval_id,
                    action_fingerprint=action.fingerprint,
                    approver=actor,
                    approved=True,
                    decided_at=now,
                )
                grant = await store.issue_grant(
                    decision,
                    grant_id=f"move-grant-{index}-{secrets.token_hex(8)}",
                    nonce=f"move-nonce-{index}-{secrets.token_hex(16)}",
                    issued_at=now,
                    expires_at=now + timedelta(minutes=1),
                )
                receipt = await broker.execute(grant, actor=actor)
                effect = handler.effects.pop(action.request_id, None)
                if receipt.outcome is ExecutionOutcome.SUCCEEDED:
                    successful_moves += 1
                if receipt.postcondition.status is PostconditionStatus.PASSED:
                    verified_postconditions += 1
                if (
                    effect is None
                    or not destination.exists()
                    or source.exists()
                    or destination.read_bytes() != content
                ):
                    unauthorized_effects += 1
                    raise RuntimeError("move postcondition mismatch")
                rollback = await handler.rollback(
                    action,
                    effect,
                    reason="phase3_benchmark_round_trip",
                )
                if rollback.status is RollbackStatus.SUCCEEDED:
                    successful_rollbacks += 1
                if not source.exists() or destination.exists() or source.read_bytes() != content:
                    unauthorized_effects += 1
                    raise RuntimeError("move rollback mismatch")
                if not source.resolve().is_relative_to(controlled_root):
                    unauthorized_effects += 1
                    raise RuntimeError("move escaped controlled root")
                latencies.append((time.perf_counter_ns() - started) / 1_000_000)
            except Exception as error:
                failures.add("reversible_move", index + 1, error)
            finally:
                if (
                    action is not None
                    and effect is not None
                    and destination.exists()
                    and not source.exists()
                ):
                    try:
                        await handler.rollback(
                            action,
                            effect,
                            reason="phase3_benchmark_final_recovery",
                        )
                    except Exception as error:
                        failures.add("reversible_move_recovery", index + 1, error)
    finally:
        await store.close()

    remaining_destinations = sum(1 for path in archive.iterdir() if path.is_file())
    if remaining_destinations:
        unauthorized_effects += remaining_destinations
    return {
        "samples": samples,
        "completed_round_trips": len(latencies),
        "p50_ms": rounded_percentile(latencies, 0.50),
        "p95_ms": rounded_percentile(latencies, 0.95),
        "successful_broker_moves": successful_moves,
        "verified_postconditions": verified_postconditions,
        "successful_rollbacks": successful_rollbacks,
        "escape_attempt_refused": escape_refused,
        "remaining_destination_files": remaining_destinations,
        "unauthorized_effect_count": unauthorized_effects,
        "fixture_bytes_per_file": len(b"Phase 3 reversible benchmark sample 000.\n"),
        "rollback_mode": "production handler rollback after broker-verified move",
    }


def rounded_percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 3)


def thresholds(
    permission: dict[str, Any],
    dispatch: dict[str, Any],
    moves: dict[str, Any],
    failures: FailureLog,
) -> dict[str, bool]:
    return {
        "permission_sample_count": permission["measured_samples"] >= 500,
        "permission_complete_accounting": permission["measured_samples"] == permission["samples"],
        "permission_p95": permission["p95_ms"] <= PERMISSION_P95_TARGET_MS,
        "permission_zero_false_accepts": permission["invalid_false_accept_count"] == 0,
        "permission_valid_controls": permission["valid_control_failures"] == 0,
        "permission_zero_effects": permission["unexpected_effect_count"] == 0,
        "dispatch_sample_count": dispatch["measured_samples"] >= 200,
        "dispatch_complete_accounting": dispatch["measured_samples"] == dispatch["samples"],
        "dispatch_p95": dispatch["p95_ms"] <= BROKER_P95_TARGET_MS,
        "dispatch_effect_count": dispatch["observed_effect_count"]
        == dispatch["expected_effect_count"],
        "dispatch_zero_duplicate_effects": dispatch["duplicate_effect_count"] == 0,
        "dispatch_receipt_idempotency": dispatch["duplicate_receipt_failures"] == 0,
        "dispatch_audit_accounting": dispatch["audit_event_count"] == dispatch["samples"] * 2,
        "move_sample_count": moves["completed_round_trips"] >= 20,
        "move_complete_accounting": moves["completed_round_trips"] == moves["samples"],
        "move_broker_success": moves["successful_broker_moves"] == moves["samples"],
        "move_postconditions": moves["verified_postconditions"] == moves["samples"],
        "move_rollbacks": moves["successful_rollbacks"] == moves["samples"],
        "move_no_escape": moves["escape_attempt_refused"],
        "move_no_destination_remnants": moves["remaining_destination_files"] == 0,
        "move_zero_unauthorized_effects": moves["unauthorized_effect_count"] == 0,
        "no_failures": failures.total == 0,
    }


async def run(args: argparse.Namespace, work_dir: Path, output: Path) -> dict[str, Any]:
    failures = FailureLog()
    permission = await benchmark_permission_validation(
        args.validation_samples,
        failures=failures,
    )
    dispatch = await benchmark_fake_dispatch(args.dispatch_samples, failures=failures)
    try:
        moves = await benchmark_reversible_moves(
            work_dir,
            args.move_round_trips,
            failures=failures,
        )
    except Exception as error:
        failures.add("reversible_move_setup", 0, error)
        moves = {
            "samples": args.move_round_trips,
            "completed_round_trips": 0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "successful_broker_moves": 0,
            "verified_postconditions": 0,
            "successful_rollbacks": 0,
            "escape_attempt_refused": False,
            "remaining_destination_files": 0,
            "unauthorized_effect_count": 0,
            "fixture_bytes_per_file": 0,
            "rollback_mode": "setup failed before any authorized move",
        }
    checks = thresholds(permission, dispatch, moves, failures)
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "platform": {
            "os": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "settings": {
            "work_dir": str(work_dir.relative_to(_repository_root())),
            "output": str(output.relative_to(_repository_root())),
            "validation_samples": args.validation_samples,
            "dispatch_samples": args.dispatch_samples,
            "move_round_trips": args.move_round_trips,
            "permission_p95_target_ms": PERMISSION_P95_TARGET_MS,
            "broker_p95_target_ms": BROKER_P95_TARGET_MS,
            "network_used": False,
            "real_input_sent": False,
            "media_used": False,
            "audio_used": False,
            "clipboard_used": False,
            "printing_used": False,
            "application_launch_used": False,
            "file_scope": "caller-supplied disposable controlled root only",
        },
        "permission_and_grant_validation": permission,
        "fake_broker_dispatch": dispatch,
        "reversible_move_round_trips": moves,
        "thresholds": checks,
        "threshold_pass": all(checks.values()),
        "failure_count": failures.total,
        "failures": failures.items,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise RuntimeError("benchmark report exceeds 100 KiB output cap")
    await asyncio.to_thread(_write_report_exclusive, output, encoded + b"\n")
    return report


def _write_report_exclusive(output: Path, encoded: bytes) -> None:
    with output.open("xb") as stream:
        stream.write(encoded)


def main() -> None:
    if os.name != "nt":
        raise SystemExit("phase3 benchmark requires Windows")
    args = parse_args()
    try:
        validate_counts(args)
        work_dir, output = resolve_disposable_paths(args.work_dir, args.output)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    report = asyncio.run(run(args, work_dir, output))
    summary = {
        "output": str(output),
        "permission_p50_ms": report["permission_and_grant_validation"]["p50_ms"],
        "permission_p95_ms": report["permission_and_grant_validation"]["p95_ms"],
        "permission_false_accepts": report["permission_and_grant_validation"][
            "invalid_false_accept_count"
        ],
        "broker_p50_ms": report["fake_broker_dispatch"]["p50_ms"],
        "broker_p95_ms": report["fake_broker_dispatch"]["p95_ms"],
        "duplicate_effects": report["fake_broker_dispatch"]["duplicate_effect_count"],
        "move_round_trips": report["reversible_move_round_trips"]["completed_round_trips"],
        "move_p50_ms": report["reversible_move_round_trips"]["p50_ms"],
        "move_p95_ms": report["reversible_move_round_trips"]["p95_ms"],
        "failure_count": report["failure_count"],
        "threshold_pass": report["threshold_pass"],
    }
    print(json.dumps(summary, indent=2))
    if args.enforce and not report["threshold_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
