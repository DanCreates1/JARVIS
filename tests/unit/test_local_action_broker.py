from __future__ import annotations

import asyncio
import os
import threading
from datetime import timedelta
from pathlib import Path

import pytest

from jarvis.broker import LocalActionBroker
from jarvis.computer.actions import ReversibleMoveHandler, prepare_action
from jarvis.computer.config import ComputerAccessPolicy
from jarvis.computer.windows import (
    AllowedRootGuard,
    FileIdentity,
    RenamePostconditionError,
    RenameReceipt,
    rollback_rename,
)
from jarvis.core import PermissionLevel, ToolConcurrency, count_json_leaf_items
from jarvis.permissions import (
    ActionAuditEvent,
    ActionAuditEventType,
    ActionAuditSequenceConflictError,
    ActionEffect,
    AuthenticationAssurance,
    CanonicalAction,
    ExecutionOutcome,
    InteractionInterface,
    PostconditionEvidence,
    PostconditionStatus,
    RollbackStatus,
)
from tests.fakes.phase3 import (
    FIXED_NOW,
    POLICY_VERSION,
    FakeActionHandler,
    InMemoryActionAudit,
    InMemoryActionState,
    action_definition,
    actor,
    approval_grant,
    canonical_action,
)


def broker(
    handler: FakeActionHandler,
    *,
    state: InMemoryActionState | None = None,
    audit: InMemoryActionAudit | None = None,
    policy_version: str = POLICY_VERSION,
) -> tuple[LocalActionBroker, InMemoryActionState, InMemoryActionAudit]:
    state = state or InMemoryActionState()
    audit = audit or InMemoryActionAudit()
    return (
        LocalActionBroker(
            [handler],
            state_store=state,
            audit_store=audit,
            policy_version=policy_version,
            now=lambda: FIXED_NOW,
        ),
        state,
        audit,
    )


def test_result_item_quota_counts_recursive_scalar_leaves_only() -> None:
    value = {"nested": ["one", {"two": 2}], "three": True, "ignored": None}

    assert count_json_leaf_items(value) == 3
    assert count_json_leaf_items(value, stop_after=2) == 3
    assert count_json_leaf_items({"empty": [], "nothing": None}) == 0
    with pytest.raises(ValueError, match="non-negative"):
        count_json_leaf_items(value, stop_after=-1)


@pytest.mark.asyncio
async def test_broker_executes_fixed_handler_and_returns_idempotent_receipt() -> None:
    definition = action_definition()
    handler = FakeActionHandler(definition, result={"status": "done"})
    service, state, audit = broker(handler)
    grant = approval_grant(canonical_action(definition))

    first = await service.execute(grant, actor=grant.action.actor)
    second = await service.execute(grant, actor=grant.action.actor)

    assert first.outcome is ExecutionOutcome.SUCCEEDED
    assert second == first
    assert first.result == {"status": "done"}
    assert first.postcondition.status is PostconditionStatus.PASSED
    assert first.rollback.status is RollbackStatus.NOT_NEEDED
    assert handler.execute_calls == handler.verify_calls == 1
    assert handler.rollback_calls == 0
    assert state.claim_count == state.complete_count == 1
    assert [event.type for event in audit.events] == [
        ActionAuditEventType.EXECUTION_STARTED,
        ActionAuditEventType.EXECUTION_FINISHED,
    ]
    assert all(event.detail.keys() <= {"result_bytes"} for event in audit.events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("action", "action_fingerprint_mismatch"),
        ("grant", "grant_fingerprint_mismatch"),
        ("actor", "actor_mismatch"),
        ("policy", "policy_version_mismatch"),
        ("version", "unknown_action"),
    ],
)
async def test_broker_rejects_mutation_cross_session_policy_and_unregistered_version(
    mutation: str,
    expected_code: str,
) -> None:
    definition = action_definition()
    handler = FakeActionHandler(definition)
    service, state, _audit = broker(handler)
    action = canonical_action(definition)
    grant = approval_grant(action)
    executing_actor = action.actor
    if mutation == "action":
        grant = grant.model_copy(
            update={
                "action": action.model_copy(update={"normalized_arguments": {"value": "injected"}})
            }
        )
    elif mutation == "grant":
        grant = grant.model_copy(update={"nonce": "mutated"})
    elif mutation == "actor":
        executing_actor = actor(session_id="cross-session")
    elif mutation == "policy":
        action = canonical_action(definition, policy_version="old-policy")
        grant = approval_grant(action)
        executing_actor = action.actor
    elif mutation == "version":
        action = canonical_action(definition, action_version="2")
        grant = approval_grant(action)
        executing_actor = action.actor

    receipt = await service.execute(grant, actor=executing_actor)
    assert receipt.outcome is ExecutionOutcome.DENIED
    assert receipt.error_code == expected_code
    assert handler.execute_calls == 0
    assert state.claim_count == 0


@pytest.mark.asyncio
async def test_broker_rejects_expired_level_four_unknown_and_state_claim_failures() -> None:
    definition = action_definition()
    handler = FakeActionHandler(definition)
    service, state, _audit = broker(handler)

    expired_service = LocalActionBroker(
        [handler],
        state_store=InMemoryActionState(),
        audit_store=InMemoryActionAudit(),
        policy_version=POLICY_VERSION,
        now=lambda: FIXED_NOW + timedelta(minutes=3),
    )
    expired = await expired_service.execute(
        approval_grant(canonical_action(definition)),
        actor=actor(),
    )
    assert expired.error_code == "grant_expired"

    level_four = action_definition(PermissionLevel.LEVEL_4, supports_rollback=False)
    level_four_handler = FakeActionHandler(level_four)
    level_four_service, _, _ = broker(level_four_handler)
    level_four_grant = approval_grant(canonical_action(level_four))
    denied = await level_four_service.execute(level_four_grant, actor=level_four_grant.action.actor)
    assert denied.error_code == "level_4_disabled"
    assert level_four_handler.execute_calls == 0

    unknown_action = canonical_action(definition, action_id="unknown_action")
    unknown_grant = approval_grant(unknown_action)
    unknown = await service.execute(unknown_grant, actor=unknown_action.actor)
    assert unknown.error_code == "unknown_action"

    state.fail_claim = True
    unavailable_grant = approval_grant(
        canonical_action(definition, idempotency_key="claim-failure"),
        grant_id="grant-claim-failure",
    )
    unavailable = await service.execute(unavailable_grant, actor=unavailable_grant.action.actor)
    assert unavailable.error_code == "action_state_unavailable"
    assert handler.execute_calls == 0


@pytest.mark.asyncio
async def test_one_use_claim_blocks_concurrent_and_mutated_replay() -> None:
    definition = action_definition(concurrency=ToolConcurrency.PARALLEL)
    handler = FakeActionHandler(definition, block=True)
    service, state, _audit = broker(handler)
    grant = approval_grant(canonical_action(definition))

    first_task = asyncio.create_task(service.execute(grant, actor=grant.action.actor))
    await asyncio.wait_for(handler.execute_started.wait(), timeout=1)
    concurrent = await service.execute(grant, actor=grant.action.actor)
    assert concurrent.outcome is ExecutionOutcome.DENIED
    assert concurrent.error_code == "grant_replayed"
    handler.release_execute.set()
    first = await asyncio.wait_for(first_task, timeout=1)
    assert first.outcome is ExecutionOutcome.SUCCEEDED
    assert handler.execute_calls == 1

    replay_action = canonical_action(definition, idempotency_key="different-idempotency")
    replay_grant = approval_grant(replay_action, grant_id=grant.grant_id)
    replay = await service.execute(replay_grant, actor=replay_action.actor)
    assert replay.outcome is ExecutionOutcome.DENIED
    assert replay.error_code == "grant_replayed"
    assert state.claim_count == 1


@pytest.mark.asyncio
async def test_serial_global_dispatch_key_serializes_different_sessions() -> None:
    definition = action_definition(
        name="serial_global",
        concurrency=ToolConcurrency.SERIAL_GLOBAL,
    )
    handler = FakeActionHandler(definition, block=True)
    service, state, _audit = broker(handler)
    first_actor = actor(session_id="global-session-1", device_id="global-device-1")
    second_actor = actor(session_id="global-session-2", device_id="global-device-2")
    first_grant = approval_grant(
        canonical_action(
            definition,
            action_actor=first_actor,
            idempotency_key="serial-global-1",
        ),
        grant_id="grant-serial-global-1",
    )
    second_grant = approval_grant(
        canonical_action(
            definition,
            action_actor=second_actor,
            idempotency_key="serial-global-2",
        ),
        grant_id="grant-serial-global-2",
    )

    first_task = asyncio.create_task(service.execute(first_grant, actor=first_actor))
    await asyncio.wait_for(handler.execute_started.wait(), timeout=1)
    second_task = asyncio.create_task(service.execute(second_grant, actor=second_actor))
    await asyncio.sleep(0)

    assert handler.execute_calls == 1
    assert state.claim_count == 1
    handler.release_execute.set()
    first, second = await asyncio.gather(first_task, second_task)
    assert first.outcome is second.outcome is ExecutionOutcome.SUCCEEDED
    assert handler.execute_calls == 2


@pytest.mark.asyncio
async def test_serial_per_session_serializes_exact_same_session() -> None:
    definition = action_definition(
        name="serial_session",
        concurrency=ToolConcurrency.SERIAL_PER_SESSION,
    )
    handler = FakeActionHandler(definition, block=True)
    service, state, _audit = broker(handler)
    session_actor = actor(session_id="same-session", device_id="same-device")
    first_grant = approval_grant(
        canonical_action(
            definition,
            action_actor=session_actor,
            idempotency_key="serial-session-1",
        ),
        grant_id="grant-serial-session-1",
    )
    second_grant = approval_grant(
        canonical_action(
            definition,
            action_actor=session_actor,
            idempotency_key="serial-session-2",
        ),
        grant_id="grant-serial-session-2",
    )

    first_task = asyncio.create_task(service.execute(first_grant, actor=session_actor))
    await asyncio.wait_for(handler.execute_started.wait(), timeout=1)
    second_task = asyncio.create_task(service.execute(second_grant, actor=session_actor))
    await asyncio.sleep(0)

    assert handler.execute_calls == 1
    assert state.claim_count == 1
    handler.release_execute.set()
    first, second = await asyncio.gather(first_task, second_task)
    assert first.outcome is second.outcome is ExecutionOutcome.SUCCEEDED
    assert handler.execute_calls == 2


@pytest.mark.asyncio
async def test_serial_per_session_allows_different_sessions_to_overlap() -> None:
    definition = action_definition(
        name="different_sessions",
        concurrency=ToolConcurrency.SERIAL_PER_SESSION,
    )
    handler = FakeActionHandler(definition, block=True)
    service, state, _audit = broker(handler)
    first_actor = actor(session_id="overlap-session-1", device_id="overlap-device-1")
    second_actor = actor(session_id="overlap-session-2", device_id="overlap-device-2")
    first_grant = approval_grant(
        canonical_action(
            definition,
            action_actor=first_actor,
            idempotency_key="different-session-1",
        ),
        grant_id="grant-different-session-1",
    )
    second_grant = approval_grant(
        canonical_action(
            definition,
            action_actor=second_actor,
            idempotency_key="different-session-2",
        ),
        grant_id="grant-different-session-2",
    )

    first_task = asyncio.create_task(service.execute(first_grant, actor=first_actor))
    await asyncio.wait_for(handler.execute_started.wait(), timeout=1)
    second_task = asyncio.create_task(service.execute(second_grant, actor=second_actor))
    await asyncio.wait_for(handler.second_execute_started.wait(), timeout=1)

    assert state.claim_count == 2
    handler.release_execute.set()
    first, second = await asyncio.gather(first_task, second_task)
    assert first.outcome is second.outcome is ExecutionOutcome.SUCCEEDED


@pytest.mark.asyncio
async def test_parallel_definition_allows_same_session_overlap() -> None:
    definition = action_definition(
        name="parallel_action",
        concurrency=ToolConcurrency.PARALLEL,
    )
    handler = FakeActionHandler(definition, block=True)
    service, state, _audit = broker(handler)
    session_actor = actor(session_id="parallel-session", device_id="parallel-device")
    first_grant = approval_grant(
        canonical_action(
            definition,
            action_actor=session_actor,
            idempotency_key="parallel-1",
        ),
        grant_id="grant-parallel-1",
    )
    second_grant = approval_grant(
        canonical_action(
            definition,
            action_actor=session_actor,
            idempotency_key="parallel-2",
        ),
        grant_id="grant-parallel-2",
    )

    first_task = asyncio.create_task(service.execute(first_grant, actor=session_actor))
    await asyncio.wait_for(handler.execute_started.wait(), timeout=1)
    second_task = asyncio.create_task(service.execute(second_grant, actor=session_actor))
    await asyncio.wait_for(handler.second_execute_started.wait(), timeout=1)

    assert state.claim_count == 2
    handler.release_execute.set()
    first, second = await asyncio.gather(first_task, second_task)
    assert first.outcome is second.outcome is ExecutionOutcome.SUCCEEDED


@pytest.mark.asyncio
async def test_cancelled_serial_waiter_has_zero_claim_or_effect_and_releases_key() -> None:
    definition = action_definition(
        name="cancelled_waiter",
        concurrency=ToolConcurrency.SERIAL_GLOBAL,
    )
    handler = FakeActionHandler(definition, block=True)
    service, state, _audit = broker(handler)
    first_actor = actor(session_id="wait-session-1", device_id="wait-device-1")
    second_actor = actor(session_id="wait-session-2", device_id="wait-device-2")
    first_grant = approval_grant(
        canonical_action(
            definition,
            action_actor=first_actor,
            idempotency_key="waiter-1",
        ),
        grant_id="grant-waiter-1",
    )
    second_grant = approval_grant(
        canonical_action(
            definition,
            action_actor=second_actor,
            idempotency_key="waiter-2",
        ),
        grant_id="grant-waiter-2",
    )

    first_task = asyncio.create_task(service.execute(first_grant, actor=first_actor))
    await asyncio.wait_for(handler.execute_started.wait(), timeout=1)
    second_task = asyncio.create_task(service.execute(second_grant, actor=second_actor))
    await asyncio.sleep(0)
    second_task.cancel()
    cancelled = await asyncio.wait_for(second_task, timeout=1)

    assert cancelled.outcome is ExecutionOutcome.CANCELLED
    assert cancelled.error_code == "execution_cancelled_before_claim"
    assert handler.execute_calls == 1
    assert state.claim_count == 1
    handler.release_execute.set()
    first = await asyncio.wait_for(first_task, timeout=1)
    assert first.outcome is ExecutionOutcome.SUCCEEDED
    assert service._concurrency_gate._entries == {}


@pytest.mark.asyncio
async def test_cooperative_timeout_and_cancellation_attempt_registered_recovery() -> None:
    timeout_definition = action_definition(timeout_seconds=0.01)
    timeout_handler = FakeActionHandler(timeout_definition, execute_delay=1)
    timeout_service, _, _ = broker(timeout_handler)
    timeout_grant = approval_grant(canonical_action(timeout_definition))
    timed_out = await timeout_service.execute(timeout_grant, actor=timeout_grant.action.actor)
    assert timed_out.outcome is ExecutionOutcome.TIMED_OUT
    assert timed_out.error_code == "execution_timed_out"
    assert timed_out.rollback.status is RollbackStatus.SUCCEEDED
    assert timeout_handler.rollback_calls == 1

    cancel_definition = action_definition(name="cancel_action")
    cancel_handler = FakeActionHandler(cancel_definition, block=True)
    cancel_service, _, _ = broker(cancel_handler)
    cancel_grant = approval_grant(canonical_action(cancel_definition))
    task = asyncio.create_task(
        cancel_service.execute(cancel_grant, actor=cancel_grant.action.actor)
    )
    await asyncio.wait_for(cancel_handler.execute_started.wait(), timeout=1)
    task.cancel()
    cancelled = await asyncio.wait_for(task, timeout=1)
    assert cancelled.outcome is ExecutionOutcome.CANCELLED
    assert cancelled.error_code == "execution_cancelled"
    assert cancelled.rollback.status is RollbackStatus.SUCCEEDED
    assert cancel_handler.rollback_calls == 1


@pytest.mark.asyncio
async def test_result_cap_postcondition_mismatch_and_handler_error_fail_with_rollback() -> None:
    capped_definition = action_definition(max_result_bytes=8)
    capped_handler = FakeActionHandler(capped_definition, result={"large": "x" * 100})
    capped_service, _, _ = broker(capped_handler)
    capped_grant = approval_grant(canonical_action(capped_definition))
    capped = await capped_service.execute(capped_grant, actor=capped_grant.action.actor)
    assert capped.outcome is ExecutionOutcome.FAILED
    assert capped.error_code == "result_limit_exceeded"
    assert capped.rollback.status is RollbackStatus.SUCCEEDED

    item_definition = action_definition(name="item_cap", max_result_items=2)
    item_handler = FakeActionHandler(
        item_definition,
        result={"nested": ["one", {"two": 2}], "three": True, "ignored": None},
    )
    item_service, _, _ = broker(item_handler)
    item_grant = approval_grant(canonical_action(item_definition))
    item_capped = await item_service.execute(item_grant, actor=item_grant.action.actor)
    assert item_capped.outcome is ExecutionOutcome.FAILED
    assert item_capped.error_code == "result_item_limit_exceeded"
    assert item_capped.rollback.status is RollbackStatus.SUCCEEDED
    assert item_handler.verify_calls == 1

    mismatch_definition = action_definition(name="mismatch_action")
    mismatch_handler = FakeActionHandler(
        mismatch_definition,
        verify_status=PostconditionStatus.MISMATCH,
    )
    mismatch_service, _, _ = broker(mismatch_handler)
    mismatch_grant = approval_grant(canonical_action(mismatch_definition))
    mismatch = await mismatch_service.execute(mismatch_grant, actor=mismatch_grant.action.actor)
    assert mismatch.outcome is ExecutionOutcome.POSTCONDITION_MISMATCH
    assert mismatch.error_code == "postcondition_mismatch"
    assert mismatch.rollback.status is RollbackStatus.SUCCEEDED

    error_definition = action_definition(name="error_action")
    error_handler = FakeActionHandler(
        error_definition,
        execute_error=RuntimeError("private detail"),
    )
    error_service, _, _ = broker(error_handler)
    error_grant = approval_grant(canonical_action(error_definition))
    failed = await error_service.execute(error_grant, actor=error_grant.action.actor)
    assert failed.outcome is ExecutionOutcome.FAILED
    assert failed.error_code == "handler_failed"
    assert "private detail" not in (failed.error_message or "")
    assert error_handler.rollback_calls == 1


@pytest.mark.skipif(os.name != "nt", reason="requires guarded Win32 move paths")
@pytest.mark.asyncio
async def test_broker_preserves_uncertain_move_rollback_reconciliation_state(
    tmp_path: Path,
) -> None:
    controlled = tmp_path / "controlled"
    inbox = controlled / "inbox"
    archive = controlled / "archive"
    inbox.mkdir(parents=True)
    archive.mkdir()
    source = inbox / "note.txt"
    destination = archive / "note.txt"
    source.write_text("approved content", encoding="utf-8")

    def complete_then_report_uncertain(
        guard: AllowedRootGuard,
        rename_receipt: RenameReceipt,
    ) -> FileIdentity:
        restored = rollback_rename(guard, rename_receipt)
        recovery = RenameReceipt(
            source=rename_receipt.destination,
            destination=rename_receipt.source,
            identity=restored,
            postcondition_verified=False,
            postcondition_error="postcondition_probe_failed",
        )
        raise RenamePostconditionError("private rollback detail", recovery)

    class MismatchMoveHandler(ReversibleMoveHandler):
        async def verify(
            self,
            action: CanonicalAction,
            effect: ActionEffect | None,
        ) -> PostconditionEvidence:
            del action, effect
            return PostconditionEvidence(
                status=PostconditionStatus.MISMATCH,
                summary="Forced broker reconciliation path.",
            )

    handler = MismatchMoveHandler(
        ComputerAccessPolicy(
            enabled=True,
            policy_version=POLICY_VERSION,
            maximum_permission_level=PermissionLevel.LEVEL_2,
            controlled_root=controlled,
        ),
        rollback_operation=complete_then_report_uncertain,
    )
    prepared = prepare_action(
        handler,
        {"source": "inbox/note.txt", "destination": "archive/note.txt"},
    )
    move_actor = actor(capabilities=handler.definition.tool.required_capabilities)
    action = CanonicalAction.create(
        request_id="request-move-uncertain-rollback",
        action_id=handler.definition.action_id,
        action_version=handler.definition.version,
        actor=move_actor,
        normalized_arguments=prepared.normalized_arguments,
        permission_level=handler.definition.tool.permission_level,
        approval_rule=handler.definition.tool.approval_rule,
        policy_version=POLICY_VERSION,
        idempotency_key="move-uncertain-rollback",
        human_effect=prepared.human_effect,
        recovery_limits=prepared.recovery_limits,
        precondition=prepared.precondition,
        created_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(minutes=2),
    )
    grant = approval_grant(action, grant_id="grant-move-uncertain-rollback")
    state = InMemoryActionState()
    service = LocalActionBroker(
        [handler],
        state_store=state,
        audit_store=InMemoryActionAudit(),
        policy_version=POLICY_VERSION,
        now=lambda: FIXED_NOW,
    )

    execution = await service.execute(grant, actor=move_actor)

    assert execution.outcome is ExecutionOutcome.POSTCONDITION_MISMATCH
    assert execution.rollback.status is RollbackStatus.FAILED
    assert execution.rollback.detail["effect_may_have_completed"] is True
    assert execution.rollback.detail["reconciliation_required"] is True
    assert execution.rollback.detail["recovery_evidence_bound"] is True
    assert execution.rollback.detail["primitive_postcondition_verified"] is False
    assert "private rollback detail" not in execution.rollback.summary
    assert str(controlled) not in str(execution.rollback.model_dump(mode="json"))
    assert source.read_text(encoding="utf-8") == "approved content"
    assert not destination.exists()
    assert state.complete_count == 1


@pytest.mark.asyncio
async def test_required_start_audit_fails_closed_and_terminal_audit_is_supplementary() -> None:
    definition = action_definition()
    handler = FakeActionHandler(definition)
    start_failure_audit = InMemoryActionAudit(fail_calls={1})
    service, state, _ = broker(handler, audit=start_failure_audit)
    grant = approval_grant(canonical_action(definition))
    failed = await service.execute(grant, actor=grant.action.actor)
    assert failed.outcome is ExecutionOutcome.FAILED
    assert failed.error_code == "audit_unavailable"
    assert handler.execute_calls == 0
    assert state.complete_count == 1

    terminal_definition = action_definition(name="terminal_audit_action")
    terminal_handler = FakeActionHandler(terminal_definition)
    terminal_audit = InMemoryActionAudit(fail_calls={2})
    terminal_service, terminal_state, _ = broker(terminal_handler, audit=terminal_audit)
    terminal_grant = approval_grant(canonical_action(terminal_definition))
    terminal = await terminal_service.execute(terminal_grant, actor=terminal_grant.action.actor)
    assert terminal.outcome is ExecutionOutcome.SUCCEEDED
    assert terminal.error_code is None
    assert terminal.rollback.status is RollbackStatus.NOT_NEEDED
    assert terminal_handler.rollback_calls == 0
    assert terminal_state.receipts[terminal.idempotency_key] == terminal


class _StrictSequenceAudit(InMemoryActionAudit):
    async def append_action_event(self, event: ActionAuditEvent) -> None:
        sequences = [
            existing.sequence for existing in self.events if existing.request_id == event.request_id
        ]
        expected = max(sequences, default=0) + 1
        if event.sequence != expected:
            raise ActionAuditSequenceConflictError(
                "audit sequence must be the exact next request sequence"
            )
        await super().append_action_event(event)


@pytest.mark.asyncio
async def test_preclaim_rejection_does_not_poison_valid_retry_start_audit() -> None:
    definition = action_definition(name="authority_retry")
    handler = FakeActionHandler(definition)
    state = InMemoryActionState()
    audit = _StrictSequenceAudit()
    authority = {"enabled": False}
    service = LocalActionBroker(
        [handler],
        state_store=state,
        audit_store=audit,
        policy_version=POLICY_VERSION,
        now=lambda: FIXED_NOW,
        authority_guard=lambda _grant: authority["enabled"],
    )
    grant = approval_grant(canonical_action(definition))

    rejected = await service.execute(grant, actor=grant.action.actor)
    authority["enabled"] = True
    retried = await service.execute(grant, actor=grant.action.actor)

    assert rejected.error_code == "authority_disabled"
    assert retried.outcome is ExecutionOutcome.SUCCEEDED
    assert state.claim_count == 1
    assert handler.execute_calls == 1
    assert [event.sequence for event in audit.events] == [1, 2, 3]
    assert [event.type for event in audit.events] == [
        ActionAuditEventType.BROKER_REJECTED,
        ActionAuditEventType.EXECUTION_STARTED,
        ActionAuditEventType.EXECUTION_FINISHED,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "executing_actor",
    [
        actor(interface=InteractionInterface.LOCAL_CLI),
        actor(
            assurance=AuthenticationAssurance.UNAUTHENTICATED,
            authenticated_at=None,
        ),
        actor(capabilities=()),
    ],
)
async def test_execution_requires_same_interface_assurance_and_capability_superset(
    executing_actor,
) -> None:  # type: ignore[no-untyped-def]
    definition = action_definition()
    handler = FakeActionHandler(definition)
    service, state, _audit = broker(handler)
    grant = approval_grant(canonical_action(definition))

    receipt = await service.execute(grant, actor=executing_actor)

    assert receipt.outcome is ExecutionOutcome.DENIED
    assert receipt.error_code == "actor_mismatch"
    assert state.claim_count == 0
    assert handler.execute_calls == 0


@pytest.mark.asyncio
async def test_same_session_restart_may_refresh_authentication_timestamp() -> None:
    definition = action_definition()
    handler = FakeActionHandler(definition)
    service, state, _audit = broker(handler)
    origin = actor(authenticated_at=FIXED_NOW - timedelta(seconds=30))
    grant = approval_grant(canonical_action(definition, action_actor=origin))
    restarted = actor(authenticated_at=FIXED_NOW, capabilities=("computer.test", "extra"))

    receipt = await service.execute(grant, actor=restarted)

    assert receipt.outcome is ExecutionOutcome.SUCCEEDED
    assert state.claim_count == 1


class _NativeBlockingHandler(FakeActionHandler):
    def __init__(self) -> None:
        super().__init__(
            action_definition(
                name="native_block",
                timeout_seconds=0.01,
                effect_may_outlive_cancellation=True,
            )
        )
        self.native_release = threading.Event()
        self.native_finished = threading.Event()

    def _native_effect(self) -> None:
        self.native_release.wait(timeout=2)
        self.native_finished.set()

    async def execute(self, action) -> ActionEffect:  # type: ignore[no-untyped-def]
        del action
        self.execute_calls += 1
        self.execute_started.set()
        await asyncio.to_thread(self._native_effect)
        return ActionEffect(result={"ok": True}, rollback_context={"changed": True})


@pytest.mark.asyncio
async def test_native_dispatch_timeout_is_uncertain_until_manual_reconciliation() -> None:
    handler = _NativeBlockingHandler()
    service, state, audit = broker(handler)
    grant = approval_grant(canonical_action(handler.definition))

    receipt = await service.execute(grant, actor=grant.action.actor)
    handler.native_release.set()
    native_finished = await asyncio.to_thread(handler.native_finished.wait, 1)

    assert native_finished is True
    assert receipt.outcome is ExecutionOutcome.UNCERTAIN
    assert receipt.error_code == "execution_timed_out_effect_uncertain"
    assert receipt.postcondition.status is PostconditionStatus.UNKNOWN
    assert receipt.rollback.status is RollbackStatus.UNAVAILABLE
    assert "manually" in (receipt.error_message or "")
    assert state.receipts[receipt.idempotency_key] == receipt
    assert audit.events[-1].outcome is ExecutionOutcome.UNCERTAIN


class _BlockingCompletionState(InMemoryActionState):
    def __init__(self) -> None:
        super().__init__()
        self.completion_started = asyncio.Event()
        self.release_completion = asyncio.Event()

    async def complete_grant(self, grant, receipt) -> None:  # type: ignore[no-untyped-def]
        self.completion_started.set()
        await self.release_completion.wait()
        await super().complete_grant(grant, receipt)


@pytest.mark.asyncio
async def test_cancellation_during_finalize_waits_for_durable_terminal_receipt() -> None:
    definition = action_definition(name="cancel_finalize")
    handler = FakeActionHandler(definition)
    state = _BlockingCompletionState()
    service, _, _audit = broker(handler, state=state)
    grant = approval_grant(canonical_action(definition))

    task = asyncio.create_task(service.execute(grant, actor=grant.action.actor))
    await asyncio.wait_for(state.completion_started.wait(), timeout=1)
    task.cancel()
    state.release_completion.set()
    receipt = await asyncio.wait_for(task, timeout=1)

    assert receipt.outcome is ExecutionOutcome.SUCCEEDED
    assert state.receipts[receipt.idempotency_key] == receipt
    assert state.complete_count == 1


class _FailFirstCompletionState(InMemoryActionState):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def complete_grant(self, grant, receipt) -> None:  # type: ignore[no-untyped-def]
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("forced first completion failure")
        await super().complete_grant(grant, receipt)


@pytest.mark.asyncio
async def test_success_is_never_audited_before_recovery_receipt_is_persisted() -> None:
    definition = action_definition(name="state_ordering")
    handler = FakeActionHandler(definition)
    state = _FailFirstCompletionState()
    service, _, audit = broker(handler, state=state)
    grant = approval_grant(canonical_action(definition))

    receipt = await service.execute(grant, actor=grant.action.actor)

    assert receipt.outcome is ExecutionOutcome.FAILED
    assert receipt.error_code == "action_state_unavailable"
    assert receipt.rollback.status is RollbackStatus.SUCCEEDED
    assert state.receipts[receipt.idempotency_key] == receipt
    assert audit.events[-1].outcome is ExecutionOutcome.FAILED
    assert all(event.outcome is not ExecutionOutcome.SUCCEEDED for event in audit.events)


def test_broker_registry_is_fixed_nonempty_and_rejects_duplicate_dispatch() -> None:
    definition = action_definition()
    handler = FakeActionHandler(definition)
    with pytest.raises(ValueError, match="at least one"):
        LocalActionBroker(
            [],
            state_store=InMemoryActionState(),
            audit_store=InMemoryActionAudit(),
            policy_version=POLICY_VERSION,
        )
    with pytest.raises(ValueError, match="duplicate"):
        LocalActionBroker(
            [handler, handler],
            state_store=InMemoryActionState(),
            audit_store=InMemoryActionAudit(),
            policy_version=POLICY_VERSION,
        )


@pytest.mark.asyncio
async def test_runtime_authority_kill_switch_denies_before_claim_or_effect() -> None:
    definition = action_definition(PermissionLevel.LEVEL_1)
    handler = FakeActionHandler(definition)
    state = InMemoryActionState()
    audit = InMemoryActionAudit()
    current_actor = actor()
    grant = approval_grant(canonical_action(definition, action_actor=current_actor))
    broker = LocalActionBroker(
        [handler],
        state_store=state,
        audit_store=audit,
        policy_version=POLICY_VERSION,
        now=lambda: FIXED_NOW,
        authority_guard=lambda _grant: False,
    )

    receipt = await broker.execute(grant, actor=current_actor)

    assert receipt.outcome is ExecutionOutcome.DENIED
    assert receipt.error_code == "authority_disabled"
    assert handler.execute_calls == 0
    assert state.claim_count == 0
    assert audit.events[-1].type is ActionAuditEventType.BROKER_REJECTED
