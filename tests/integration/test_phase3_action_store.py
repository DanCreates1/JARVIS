from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest

from jarvis.core import ApprovalRule, PermissionLevel, ToolRisk
from jarvis.permissions import (
    ActionAuditEvent,
    ActionAuditEventType,
    ActionLifecycleEventType,
    ActionStoreConflictError,
    ActionStoreStateError,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalSource,
    ApprovalStatus,
    AuthenticationAssurance,
    CanonicalAction,
    ControlIntentEvent,
    ControlIntentOutcome,
    ExecutionOutcome,
    ExecutionReceipt,
    GrantStatus,
    InteractionInterface,
    PostconditionEvidence,
    PostconditionStatus,
    RollbackReceipt,
    RollbackStatus,
    SQLiteActionStore,
    canonical_json_bytes,
)
from tests.fakes.phase3 import FIXED_NOW, POLICY_VERSION, action_definition, actor


def _approval_request(
    suffix: str, *, expires_in: timedelta = timedelta(minutes=1)
) -> ApprovalRequest:
    definition = action_definition(PermissionLevel.LEVEL_2)
    action = CanonicalAction.create(
        request_id=f"request-{suffix}",
        action_id=definition.action_id,
        action_version=definition.version,
        actor=actor(),
        normalized_arguments={"target": f"item-{suffix}"},
        permission_level=definition.tool.permission_level,
        approval_rule=ApprovalRule.EXACT_RECENT_AUTH,
        policy_version=POLICY_VERSION,
        idempotency_key=f"idempotency-{suffix}",
        human_effect=f"Change item {suffix} once.",
        recovery_limits="Rollback only the exact fake state change.",
        created_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(minutes=2),
        tool_call_id=f"tool-call-{suffix}",
        precondition={"state": "before"},
    )
    return ApprovalRequest(
        approval_id=f"approval-{suffix}",
        action=action,
        requested_at=FIXED_NOW,
        expires_at=FIXED_NOW + expires_in,
    )


def _decision(request: ApprovalRequest, *, approved: bool = True) -> ApprovalDecision:
    return ApprovalDecision(
        approval_id=request.approval_id,
        action_fingerprint=request.action.fingerprint,
        approver=actor(interface=InteractionInterface.LOCAL_CLI),
        approved=approved,
        decided_at=FIXED_NOW + timedelta(seconds=1),
        reason=None if approved else "User denied exact operation.",
    )


def _receipt(grant_id: str, request: ApprovalRequest) -> ExecutionReceipt:
    result = {"changed": True}
    return ExecutionReceipt(
        receipt_id=f"receipt-{request.action.request_id}",
        grant_id=grant_id,
        request_id=request.action.request_id,
        action_id=request.action.action_id,
        action_version=request.action.action_version,
        action_fingerprint=request.action.fingerprint,
        actor=request.action.actor,
        policy_version=request.action.policy_version,
        idempotency_key=request.action.idempotency_key,
        outcome=ExecutionOutcome.SUCCEEDED,
        started_at=FIXED_NOW + timedelta(seconds=3),
        finished_at=FIXED_NOW + timedelta(seconds=4),
        result=result,
        result_bytes=len(canonical_json_bytes(result)),
        postcondition=PostconditionEvidence(
            status=PostconditionStatus.PASSED,
            summary="Exact fake state observed.",
        ),
        rollback=RollbackReceipt(
            status=RollbackStatus.NOT_NEEDED,
            summary="Postcondition passed.",
        ),
    )


def _audit_event(
    request: ApprovalRequest,
    *,
    grant_id: str,
    sequence: int,
    event_type: ActionAuditEventType,
    detail: dict[str, object] | None = None,
) -> ActionAuditEvent:
    return ActionAuditEvent(
        event_id=f"audit-{request.action.request_id}-{sequence}",
        sequence=sequence,
        type=event_type,
        request_id=request.action.request_id,
        grant_id=grant_id,
        action_id=request.action.action_id,
        action_version=request.action.action_version,
        action_fingerprint=request.action.fingerprint,
        occurred_at=FIXED_NOW + timedelta(seconds=sequence + 2),
        outcome=(ExecutionOutcome.SUCCEEDED if sequence > 1 else None),
        detail=detail or {},  # type: ignore[arg-type]
    )


async def _create_grant(
    store: SQLiteActionStore,
    suffix: str,
    *,
    grant_expires_in: timedelta = timedelta(seconds=30),
) -> tuple[ApprovalRequest, ApprovalDecision, str]:
    request = _approval_request(suffix)
    await store.create_approval_request(
        request,
        source=ApprovalSource.TEST,
        risk=ToolRisk.REVERSIBLE,
        rule_id="level_2_exact_approval",
    )
    decision = _decision(request)
    grant_id = f"grant-{suffix}"
    await store.issue_grant(
        decision,
        grant_id=grant_id,
        nonce=f"nonce-{suffix}",
        issued_at=FIXED_NOW + timedelta(seconds=2),
        expires_at=FIXED_NOW + grant_expires_in,
    )
    return request, decision, grant_id


async def test_pending_approval_metadata_denial_expiry_and_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "state" / "jarvis.db"
    request = _approval_request("pending")
    async with SQLiteActionStore(database_path, now=lambda: FIXED_NOW) as store:
        record = await store.create_approval_request(
            request,
            source=ApprovalSource.VOICE,
            risk=ToolRisk.SENSITIVE,
            rule_id="level_2_exact_approval",
        )
        assert record.request == request
        assert record.source is ApprovalSource.VOICE
        assert record.risk is ToolRisk.SENSITIVE
        assert record.status is ApprovalStatus.PENDING
        assert (
            await store.create_approval_request(
                request,
                source=ApprovalSource.VOICE,
                risk=ToolRisk.SENSITIVE,
                rule_id="level_2_exact_approval",
            )
            == record
        )
        assert await store.list_pending_approval_requests() == [record]

    async with SQLiteActionStore(database_path, now=lambda: FIXED_NOW) as reopened:
        assert await reopened.get_approval_request(request.approval_id) == record
        denied = await reopened.record_denial(_decision(request, approved=False))
        assert denied.status is ApprovalStatus.DENIED
        assert denied.decision is not None and not denied.decision.approved
        assert await reopened.record_denial(_decision(request, approved=False)) == denied
        with pytest.raises(ValueError, match="denied decision"):
            await reopened.issue_grant(
                _decision(request, approved=False),
                grant_id="grant-denied",
                nonce="nonce-denied",
                issued_at=FIXED_NOW + timedelta(seconds=2),
                expires_at=FIXED_NOW + timedelta(seconds=30),
            )

        expiring = _approval_request("expiring", expires_in=timedelta(seconds=20))
        await reopened.create_approval_request(
            expiring,
            source=ApprovalSource.TEST,
            risk=ToolRisk.REVERSIBLE,
            rule_id="level_2_exact_approval",
        )
        with pytest.raises(ValueError, match="before its stored expiry"):
            await reopened.expire_approval(
                expiring.approval_id,
                expired_at=FIXED_NOW + timedelta(seconds=19),
            )
        assert await reopened.expire_approval(
            expiring.approval_id,
            expired_at=FIXED_NOW + timedelta(seconds=20),
        )
        expired = await reopened.get_approval_request(expiring.approval_id)
        assert expired is not None and expired.status is ApprovalStatus.EXPIRED


async def test_issue_requires_exact_decision_and_revoke_survives_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "jarvis.db"
    async with SQLiteActionStore(database_path, now=lambda: FIXED_NOW) as store:
        request = _approval_request("grant")
        await store.create_approval_request(
            request,
            source=ApprovalSource.LOCAL_WEB,
            risk=ToolRisk.REVERSIBLE,
            rule_id="level_2_exact_approval",
        )
        wrong = _decision(request).model_copy(update={"action_fingerprint": "sha256:" + "0" * 64})
        with pytest.raises(ActionStoreConflictError, match="fingerprint"):
            await store.issue_grant(
                wrong,
                grant_id="grant-wrong",
                nonce="nonce-wrong",
                issued_at=FIXED_NOW + timedelta(seconds=2),
                expires_at=FIXED_NOW + timedelta(seconds=30),
            )

        decision = _decision(request)
        grant = await store.issue_grant(
            decision,
            grant_id="grant-exact",
            nonce="nonce-exact",
            issued_at=FIXED_NOW + timedelta(seconds=2),
            expires_at=FIXED_NOW + timedelta(seconds=30),
        )
        assert await store.load_grant(grant.grant_id) == grant
        assert (
            await store.issue_grant(
                decision,
                grant_id="grant-exact",
                nonce="nonce-exact",
                issued_at=FIXED_NOW + timedelta(seconds=2),
                expires_at=FIXED_NOW + timedelta(seconds=30),
            )
            == grant
        )
        with pytest.raises(ActionStoreConflictError, match="different exact grant"):
            await store.issue_grant(
                decision,
                grant_id="grant-changed",
                nonce="nonce-changed",
                issued_at=FIXED_NOW + timedelta(seconds=2),
                expires_at=FIXED_NOW + timedelta(seconds=30),
            )

    async with SQLiteActionStore(database_path, now=lambda: FIXED_NOW) as reopened:
        assert await reopened.revoke_grant(
            "grant-exact", revoked_at=FIXED_NOW + timedelta(seconds=3)
        )
        grant_record = await reopened.get_grant_record("grant-exact")
        assert grant_record is not None and grant_record.status is GrantStatus.REVOKED
        assert not await reopened.claim_grant(
            grant_record.grant,
            claimed_at=FIXED_NOW + timedelta(seconds=4),
        )


async def test_atomic_claim_receipt_idempotency_and_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "jarvis.db"
    first = SQLiteActionStore(database_path, now=lambda: FIXED_NOW)
    await first.initialize()
    request, _, grant_id = await _create_grant(first, "claim")
    grant = await first.get_grant(grant_id)
    assert grant is not None

    second = SQLiteActionStore(database_path, now=lambda: FIXED_NOW)
    await second.initialize()
    claims = await asyncio.gather(
        first.claim_grant(grant, claimed_at=FIXED_NOW + timedelta(seconds=3)),
        second.claim_grant(grant, claimed_at=FIXED_NOW + timedelta(seconds=3)),
    )
    assert sorted(claims) == [False, True]
    assert not await second.claim_grant(
        grant.model_copy(update={"nonce": "mutated"}),
        claimed_at=FIXED_NOW + timedelta(seconds=4),
    )

    receipt = _receipt(grant_id, request)
    owner = first if claims[0] else second
    await owner.complete_grant(grant, receipt)
    await owner.complete_grant(grant, receipt)
    assert await second.get_receipt(request.action.idempotency_key) == receipt
    assert await second.list_receipts() == [receipt]
    with pytest.raises(ActionStoreConflictError, match="different exact data"):
        await second.complete_grant(
            grant,
            receipt.model_copy(update={"receipt_id": "receipt-conflict"}),
        )
    await first.close()
    await second.close()

    async with SQLiteActionStore(database_path, now=lambda: FIXED_NOW) as reopened:
        assert await reopened.get_receipt(request.action.idempotency_key) == receipt
        record = await reopened.get_approval_request(request.approval_id)
        assert record is not None and record.status is ApprovalStatus.COMPLETED


async def test_audit_is_sanitized_sequenced_capped_append_only_and_durable(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jarvis.db"
    store = SQLiteActionStore(
        database_path,
        now=lambda: FIXED_NOW,
        max_audit_events_per_request=2,
        max_audit_detail_bytes=64,
    )
    await store.initialize()
    request, _, grant_id = await _create_grant(store, "audit")
    start = _audit_event(
        request,
        grant_id=grant_id,
        sequence=1,
        event_type=ActionAuditEventType.EXECUTION_STARTED,
    )
    await store.append_action_event(start)
    with pytest.raises(ValueError, match="non-sanitized"):
        await store.append_action_event(
            _audit_event(
                request,
                grant_id=grant_id,
                sequence=2,
                event_type=ActionAuditEventType.EXECUTION_FINISHED,
                detail={"secret": "do-not-store"},
            )
        )
    with pytest.raises(ValueError, match="size limit"):
        await store.append_action_event(
            _audit_event(
                request,
                grant_id=grant_id,
                sequence=2,
                event_type=ActionAuditEventType.EXECUTION_FINISHED,
                detail={"reason_code": "x" * 100},
            )
        )
    with pytest.raises(ActionStoreConflictError, match="exact next"):
        await store.append_action_event(
            _audit_event(
                request,
                grant_id=grant_id,
                sequence=2,
                event_type=ActionAuditEventType.EXECUTION_STARTED,
            ).model_copy(update={"sequence": 1})
        )
    finish = _audit_event(
        request,
        grant_id=grant_id,
        sequence=2,
        event_type=ActionAuditEventType.EXECUTION_FINISHED,
        detail={"result_bytes": 16},
    )
    await store.append_action_event(finish)
    with pytest.raises(ValueError, match="per-request limit"):
        await store.append_action_event(
            _audit_event(
                request,
                grant_id=grant_id,
                sequence=3,
                event_type=ActionAuditEventType.EXECUTION_FINISHED,
            )
        )
    assert await store.list_action_events(request.action.request_id) == [start, finish]
    await store.close()

    async with SQLiteActionStore(database_path, now=lambda: FIXED_NOW) as reopened:
        assert await reopened.list_action_events(request.action.request_id) == [start, finish]
    with closing(sqlite3.connect(database_path)) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE action_audit_events SET error_code = 'tampered' WHERE id = ?",
                (start.event_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM action_audit_events WHERE id = ?", (start.event_id,))


async def test_expiry_cleanup_and_intent_event_deduplication(tmp_path: Path) -> None:
    database_path = tmp_path / "jarvis.db"
    async with SQLiteActionStore(database_path, now=lambda: FIXED_NOW) as store:
        request, _, grant_id = await _create_grant(
            store,
            "expiry",
            grant_expires_in=timedelta(seconds=30),
        )
        first_expiry = await store.expire_stale(now=FIXED_NOW + timedelta(seconds=31))
        assert first_expiry.grants == 1
        assert first_expiry.approval_requests == 0
        grant_record = await store.get_grant_record(grant_id)
        assert grant_record is not None and grant_record.status is GrantStatus.EXPIRED
        second_expiry = await store.expire_stale(now=FIXED_NOW + timedelta(minutes=1))
        assert second_expiry.approval_requests == 1
        approval = await store.get_approval_request(request.approval_id)
        assert approval is not None and approval.status is ApprovalStatus.EXPIRED

        event = ControlIntentEvent(
            event_id="intent-event-1",
            actor_id=request.action.actor.host_id,
            session_id=request.action.actor.session_id,
            source=ApprovalSource.VOICE,
            intent="media.pause",
            outcome=ControlIntentOutcome.PROPOSED,
            created_at=FIXED_NOW,
        )
        assert await store.record_control_intent(event)
        assert not await store.record_control_intent(event)
        with pytest.raises(ActionStoreConflictError, match="different exact data"):
            await store.record_control_intent(
                event.model_copy(update={"outcome": ControlIntentOutcome.DENIED})
            )


def test_action_store_rejects_invalid_operational_bounds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="busy_timeout_ms"):
        SQLiteActionStore(tmp_path / "jarvis.db", busy_timeout_ms=-1)
    with pytest.raises(ValueError, match="max_list_items"):
        SQLiteActionStore(tmp_path / "jarvis.db", max_list_items=0)
    with pytest.raises(ValueError, match="max_audit_events"):
        SQLiteActionStore(tmp_path / "jarvis.db", max_audit_events_per_request=1)
    with pytest.raises(ValueError, match="max_audit_detail_bytes"):
        SQLiteActionStore(tmp_path / "jarvis.db", max_audit_detail_bytes=63)
    with pytest.raises(ValueError, match="max_receipt_bytes"):
        SQLiteActionStore(tmp_path / "jarvis.db", max_receipt_bytes=1_000)


async def test_expired_or_wrong_state_grants_never_claim(tmp_path: Path) -> None:
    async with SQLiteActionStore(tmp_path / "jarvis.db", now=lambda: FIXED_NOW) as store:
        request, decision, grant_id = await _create_grant(
            store,
            "expired-claim",
            grant_expires_in=timedelta(seconds=10),
        )
        grant = await store.get_grant(grant_id)
        assert grant is not None
        assert not await store.claim_grant(
            grant,
            claimed_at=FIXED_NOW + timedelta(seconds=10),
        )
        record = await store.get_grant_record(grant_id)
        assert record is not None and record.status is GrantStatus.EXPIRED
        with pytest.raises(ActionStoreStateError, match="state"):
            await store.issue_grant(
                decision,
                grant_id="grant-after-expiry",
                nonce="nonce-after-expiry",
                issued_at=FIXED_NOW + timedelta(seconds=11),
                expires_at=FIXED_NOW + timedelta(seconds=20),
            )
        assert await store.get_receipt(request.action.idempotency_key) is None


async def test_approval_store_requires_exact_trusted_cli_authority(tmp_path: Path) -> None:
    request = _approval_request("trusted-approval")
    decision = _decision(request)
    async with SQLiteActionStore(tmp_path / "jarvis.db", now=lambda: FIXED_NOW) as store:
        await store.create_approval_request(
            request,
            source=ApprovalSource.TEST,
            risk=ToolRisk.REVERSIBLE,
            rule_id="level_2_exact_approval",
        )
        invalid_approvers = (
            actor(),
            actor(
                interface=InteractionInterface.LOCAL_CLI,
                assurance=AuthenticationAssurance.UNAUTHENTICATED,
                authenticated_at=None,
            ),
            actor(interface=InteractionInterface.LOCAL_CLI, capabilities=()),
            actor(interface=InteractionInterface.LOCAL_CLI, session_id="other-session"),
        )
        for invalid in invalid_approvers:
            with pytest.raises(ActionStoreConflictError):
                await store.record_approval_decision(
                    decision.model_copy(update={"approver": invalid})
                )

        approved = await store.record_approval_decision(decision)
        assert approved.status is ApprovalStatus.APPROVED


async def test_lifecycle_audit_is_sanitized_bounded_append_only_and_complete(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "jarvis.db"
    async with SQLiteActionStore(database_path, now=lambda: FIXED_NOW) as store:
        request, _decision_record, grant_id = await _create_grant(store, "private-lifecycle")
        grant = await store.get_grant(grant_id)
        assert grant is not None
        assert await store.claim_grant(
            grant,
            claimed_at=FIXED_NOW + timedelta(seconds=3),
        )
        await store.append_action_event(
            _audit_event(
                request,
                grant_id=grant_id,
                sequence=1,
                event_type=ActionAuditEventType.EXECUTION_STARTED,
            )
        )
        receipt = _receipt(grant_id, request)
        await store.complete_grant(grant, receipt)
        await store.append_action_event(
            _audit_event(
                request,
                grant_id=grant_id,
                sequence=2,
                event_type=ActionAuditEventType.EXECUTION_FINISHED,
                detail={"result_bytes": receipt.result_bytes},
            )
        )

        lifecycle = sorted(
            (
                event
                for event in await store.list_lifecycle_events(limit=100)
                if event.request_id == request.action.request_id
            ),
            key=lambda event: event.sequence,
        )
        assert [event.type for event in lifecycle] == [
            ActionLifecycleEventType.PROPOSED,
            ActionLifecycleEventType.APPROVED,
            ActionLifecycleEventType.GRANT_ISSUED,
            ActionLifecycleEventType.GRANT_CLAIMED,
            ActionLifecycleEventType.EXECUTION_STARTED,
            ActionLifecycleEventType.EXECUTION_COMPLETED,
        ]
        serialized = "\n".join(event.model_dump_json() for event in lifecycle)
        assert "item-private-lifecycle" not in serialized
        assert request.action.fingerprint not in serialized
        assert request.action.actor.host_id not in serialized

        receipt_summaries = await store.list_receipt_summaries(limit=1)
        event_summaries = await store.list_action_event_summaries(limit=2)
        assert receipt_summaries[0].receipt_id == receipt.receipt_id
        assert {event.type for event in event_summaries} == {
            ActionAuditEventType.EXECUTION_STARTED,
            ActionAuditEventType.EXECUTION_FINISHED,
        }
        with pytest.raises(ValueError, match="limit"):
            await store.list_lifecycle_events(limit=501)
        with pytest.raises(ValueError, match="limit"):
            await store.list_receipt_summaries(limit=501)
        with pytest.raises(ValueError, match="limit"):
            await store.list_action_event_summaries(limit=501)

    connection = sqlite3.connect(database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE action_lifecycle_events SET reason_code = 'tampered'")
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM action_lifecycle_events")
    finally:
        connection.close()


async def test_uncertain_native_outcome_is_durable_and_visible_in_lifecycle(
    tmp_path: Path,
) -> None:
    async with SQLiteActionStore(tmp_path / "jarvis.db", now=lambda: FIXED_NOW) as store:
        request, _decision_record, grant_id = await _create_grant(store, "uncertain")
        grant = await store.get_grant(grant_id)
        assert grant is not None
        assert await store.claim_grant(grant, claimed_at=FIXED_NOW + timedelta(seconds=3))
        receipt = ExecutionReceipt(
            receipt_id="receipt-uncertain",
            grant_id=grant_id,
            request_id=request.action.request_id,
            action_id=request.action.action_id,
            action_version=request.action.action_version,
            action_fingerprint=request.action.fingerprint,
            actor=request.action.actor,
            policy_version=request.action.policy_version,
            idempotency_key=request.action.idempotency_key,
            outcome=ExecutionOutcome.UNCERTAIN,
            started_at=FIXED_NOW + timedelta(seconds=3),
            finished_at=FIXED_NOW + timedelta(seconds=4),
            result=None,
            result_bytes=0,
            postcondition=PostconditionEvidence(
                status=PostconditionStatus.UNKNOWN,
                summary="Native effect did not return a receipt.",
            ),
            rollback=RollbackReceipt(
                status=RollbackStatus.UNAVAILABLE,
                summary="Manual reconciliation required.",
            ),
            error_code="execution_timed_out_effect_uncertain",
            error_message="Native work may still complete; recover manually.",
        )

        await store.complete_grant(grant, receipt)

        stored = await store.get_receipt(request.action.idempotency_key)
        record = await store.get_approval_request(request.approval_id)
        lifecycle = await store.list_lifecycle_events(limit=100)
        assert stored == receipt
        assert record is not None and record.status is ApprovalStatus.UNCERTAIN
        assert any(
            event.type is ActionLifecycleEventType.EXECUTION_UNCERTAIN
            and event.outcome is ExecutionOutcome.UNCERTAIN
            for event in lifecycle
        )
