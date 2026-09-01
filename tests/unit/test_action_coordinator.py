from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from jarvis.broker import LocalActionBroker
from jarvis.computer.actions import MediaControlArguments, MediaControlHandler, MediaOperation
from jarvis.computer.windows import MediaInputResult, MediaKey
from jarvis.permissions import (
    ActionCoordinator,
    ActionCoordinatorStatus,
    ApprovalDecision,
    ApprovalSource,
    ExecutionOutcome,
    GrantStatus,
    InteractionInterface,
    PermissionEngine,
    PolicyDisposition,
    SQLiteActionStore,
)
from tests.fakes.phase3 import FIXED_NOW, actor

POLICY_VERSION = "coordinator-policy-v1"


@dataclass
class MutableClock:
    value: datetime = FIXED_NOW

    def __call__(self) -> datetime:
        return self.value


class SequentialIds:
    def __init__(self) -> None:
        self._next = 0

    def __call__(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{self._next}"


class SequentialNonces:
    def __init__(self) -> None:
        self._next = 0

    def __call__(self) -> str:
        self._next += 1
        return f"nonce-{self._next}"


class FakeApprovalSurface:
    def __init__(
        self,
        clock: MutableClock,
        *,
        approved: bool = True,
        fingerprint: str | None = None,
    ) -> None:
        self.clock = clock
        self.approved = approved
        self.fingerprint = fingerprint
        self.calls = 0

    async def review(self, request: object) -> ApprovalDecision:
        from jarvis.permissions import ApprovalRequest

        exact = ApprovalRequest.model_validate(request)
        self.calls += 1
        return ApprovalDecision(
            approval_id=exact.approval_id,
            action_fingerprint=self.fingerprint or exact.action.fingerprint,
            approver=actor(
                session_id=exact.action.actor.session_id,
                device_id=exact.action.actor.device_id,
                interface=InteractionInterface.LOCAL_CLI,
                authenticated_at=self.clock(),
                capabilities=exact.action.actor.capabilities,
            ),
            approved=self.approved,
            decided_at=self.clock(),
            reason=None if self.approved else "User denied exact media operation.",
        )


def _media_handler(sent: list[MediaKey]) -> MediaControlHandler:
    def send(key: MediaKey) -> MediaInputResult:
        sent.append(key)
        return MediaInputResult(
            key=key,
            requested_count=2,
            accepted_count=2,
            last_error=None,
        )

    return MediaControlHandler(send_input=send)


def _media_actor(*, session_id: str = "session-1"):
    return actor(
        session_id=session_id,
        capabilities=("computer.media.control",),
    )


async def _coordinator(
    database_path: Path,
    *,
    clock: MutableClock,
    enable_level_one: bool = False,
    default_crypto: bool = False,
) -> tuple[ActionCoordinator, SQLiteActionStore, MediaControlHandler, list[MediaKey]]:
    sent: list[MediaKey] = []
    handler = _media_handler(sent)
    store = SQLiteActionStore(database_path, now=clock)
    await store.initialize()
    enabled = {handler.definition.dispatch_key} if enable_level_one else set()
    engine = PermissionEngine(
        policy_version=POLICY_VERSION,
        enabled_level_one_actions=enabled,
        now=clock,
    )
    broker_ids = SequentialIds()
    broker = LocalActionBroker(
        [handler],
        state_store=store,
        audit_store=store,
        policy_version=POLICY_VERSION,
        now=clock,
        id_factory=broker_ids,
    )
    kwargs = (
        {}
        if default_crypto
        else {
            "id_factory": SequentialIds(),
            "nonce_factory": SequentialNonces(),
        }
    )
    coordinator = ActionCoordinator(
        store=store,
        permission_engine=engine,
        broker=broker,
        now=clock,
        **kwargs,
    )
    return coordinator, store, handler, sent


async def test_propose_returns_exact_pending_request_even_when_level_one_is_allowed(
    tmp_path: Path,
) -> None:
    raw = MediaControlArguments(operation=MediaOperation.PLAY_PAUSE)
    current_actor = _media_actor()

    coordinator, store, handler, _ = await _coordinator(
        tmp_path / "approval-required.db",
        clock=MutableClock(),
    )
    required = await coordinator.propose(
        handler,
        raw,
        actor=current_actor,
        source=ApprovalSource.TEST,
        idempotency_key="media-required",
    )
    assert required.status is ActionCoordinatorStatus.PENDING
    assert required.request is not None
    assert required.decision is not None
    assert required.decision.disposition is PolicyDisposition.APPROVAL_REQUIRED
    assert required.request.action.normalized_arguments == {"operation": "play_pause"}
    await store.close()

    allowed_coordinator, allowed_store, allowed_handler, _ = await _coordinator(
        tmp_path / "allowed.db",
        clock=MutableClock(),
        enable_level_one=True,
    )
    allowed = await allowed_coordinator.propose(
        allowed_handler,
        raw,
        actor=current_actor,
        source=ApprovalSource.TEST,
        idempotency_key="media-allowed",
    )
    assert allowed.status is ActionCoordinatorStatus.PENDING
    assert allowed.decision is not None
    assert allowed.decision.disposition is PolicyDisposition.ALLOW
    assert allowed.grant_id is None
    await allowed_store.close()


async def test_proposal_idempotency_is_exact_and_policy_denial_creates_no_request(
    tmp_path: Path,
) -> None:
    coordinator, store, handler, _ = await _coordinator(
        tmp_path / "jarvis.db",
        clock=MutableClock(),
    )
    current_actor = _media_actor()
    first = await coordinator.propose(
        handler,
        MediaControlArguments(operation=MediaOperation.NEXT_TRACK),
        actor=current_actor,
        source=ApprovalSource.TEST,
        tool_call_id="call-1",
        idempotency_key="media-idempotent",
    )
    duplicate = await coordinator.propose(
        handler,
        MediaControlArguments(operation=MediaOperation.NEXT_TRACK),
        actor=current_actor,
        source=ApprovalSource.TEST,
        tool_call_id="call-1",
        idempotency_key="media-idempotent",
    )
    assert duplicate == first
    assert len(await store.list_pending_approval_requests()) == 1

    mutation = await coordinator.propose(
        handler,
        MediaControlArguments(operation=MediaOperation.STOP),
        actor=current_actor,
        source=ApprovalSource.TEST,
        tool_call_id="call-1",
        idempotency_key="media-idempotent",
    )
    assert mutation.status is ActionCoordinatorStatus.DENIED
    assert mutation.code == "idempotency_conflict"

    missing_capability = await coordinator.propose(
        handler,
        MediaControlArguments(operation=MediaOperation.PREVIOUS_TRACK),
        actor=actor(capabilities=()),
        source=ApprovalSource.TEST,
        idempotency_key="media-no-capability",
    )
    assert missing_capability.status is ActionCoordinatorStatus.DENIED
    assert missing_capability.code == "capability_missing"
    assert await store.get_approval_request_by_idempotency_key("media-no-capability") is None
    await store.close()


async def test_review_execute_cross_session_replay_and_durable_receipt(tmp_path: Path) -> None:
    clock = MutableClock()
    coordinator, store, handler, sent = await _coordinator(
        tmp_path / "jarvis.db",
        clock=clock,
    )
    current_actor = _media_actor()
    proposal = await coordinator.propose(
        handler,
        MediaControlArguments(operation=MediaOperation.PLAY_PAUSE),
        actor=current_actor,
        source=ApprovalSource.TEST,
        idempotency_key="media-execute",
    )
    assert proposal.approval_id is not None
    surface = FakeApprovalSurface(clock)
    approved = await coordinator.review(proposal.approval_id, surface)
    assert approved.status is ActionCoordinatorStatus.APPROVED
    assert approved.grant_id is not None
    assert surface.calls == 1
    assert await coordinator.review(proposal.approval_id, surface) == approved
    assert surface.calls == 1

    wrong_actor = await coordinator.execute(
        approved.grant_id,
        actor=_media_actor(session_id="other-session"),
    )
    assert wrong_actor.status is ActionCoordinatorStatus.DENIED
    assert wrong_actor.code == "actor_mismatch"
    assert sent == []

    executed = await coordinator.execute(approved.grant_id, actor=current_actor)
    assert executed.status is ActionCoordinatorStatus.EXECUTED
    assert executed.receipt is not None
    assert executed.receipt.outcome is ExecutionOutcome.SUCCEEDED
    assert sent == [MediaKey.PLAY_PAUSE]
    assert executed.action is not None
    events = await store.list_action_events(executed.action.request_id)
    assert [event.sequence for event in events] == [1, 2]

    replay = await coordinator.execute(approved.grant_id, actor=current_actor)
    assert replay.status is ActionCoordinatorStatus.DENIED
    assert replay.code == "grant_replayed"
    assert replay.receipt == executed.receipt
    assert sent == [MediaKey.PLAY_PAUSE]
    cross_session_replay = await coordinator.execute(
        approved.grant_id,
        actor=_media_actor(session_id="other-session"),
    )
    assert cross_session_replay.code == "actor_mismatch"
    assert cross_session_replay.receipt is None
    await store.close()


async def test_denied_mismatched_and_expired_reviews_never_issue_grants(tmp_path: Path) -> None:
    clock = MutableClock()
    coordinator, store, handler, _ = await _coordinator(
        tmp_path / "jarvis.db",
        clock=clock,
    )
    denied_proposal = await coordinator.propose(
        handler,
        MediaControlArguments(operation=MediaOperation.STOP),
        actor=_media_actor(),
        source=ApprovalSource.TEST,
        idempotency_key="media-denied",
    )
    assert denied_proposal.approval_id is not None
    denied = await coordinator.review(
        denied_proposal.approval_id,
        FakeApprovalSurface(clock, approved=False),
    )
    assert denied.status is ActionCoordinatorStatus.DENIED
    assert denied.code == "approval_denied"
    assert await store.get_grant_for_approval(denied_proposal.approval_id) is None

    mismatch_proposal = await coordinator.propose(
        handler,
        MediaControlArguments(operation=MediaOperation.NEXT_TRACK),
        actor=_media_actor(),
        source=ApprovalSource.TEST,
        idempotency_key="media-mismatch",
    )
    assert mismatch_proposal.approval_id is not None
    mismatch = await coordinator.review(
        mismatch_proposal.approval_id,
        FakeApprovalSurface(clock, fingerprint="sha256:" + "0" * 64),
    )
    assert mismatch.status is ActionCoordinatorStatus.DENIED
    assert mismatch.code == "approval_binding_mismatch"
    assert await store.get_grant_for_approval(mismatch_proposal.approval_id) is None

    expired_proposal = await coordinator.propose(
        handler,
        MediaControlArguments(operation=MediaOperation.PREVIOUS_TRACK),
        actor=_media_actor(),
        source=ApprovalSource.TEST,
        idempotency_key="media-expired",
    )
    assert expired_proposal.approval_id is not None
    expired_surface = FakeApprovalSurface(clock)
    clock.value += timedelta(minutes=2)
    expired = await coordinator.review(expired_proposal.approval_id, expired_surface)
    assert expired.status is ActionCoordinatorStatus.DENIED
    assert expired.code == "approval_expired"
    assert expired_surface.calls == 0
    await store.close()


async def test_default_ids_and_nonces_are_cryptographic_and_grant_expiry_is_enforced(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    coordinator, store, handler, sent = await _coordinator(
        tmp_path / "jarvis.db",
        clock=clock,
        default_crypto=True,
    )
    proposal = await coordinator.propose(
        handler,
        MediaControlArguments(operation=MediaOperation.PLAY_PAUSE),
        actor=_media_actor(),
        source=ApprovalSource.TEST,
    )
    assert proposal.request is not None
    assert re.fullmatch(r"request-[0-9a-f]{32}", proposal.request.action.request_id)
    assert re.fullmatch(r"approval-[0-9a-f]{32}", proposal.request.approval_id)
    approved = await coordinator.review(
        proposal.request.approval_id,
        FakeApprovalSurface(clock),
    )
    assert approved.grant_id is not None
    assert re.fullmatch(r"grant-[0-9a-f]{32}", approved.grant_id)
    grant = await store.get_grant(approved.grant_id)
    assert grant is not None
    assert re.fullmatch(r"nonce-[0-9a-f]{64}", grant.nonce)

    clock.value += timedelta(seconds=31)
    expired_review = await coordinator.review(
        proposal.request.approval_id,
        FakeApprovalSurface(clock),
    )
    assert expired_review.status is ActionCoordinatorStatus.DENIED
    assert expired_review.code == "grant_expired"
    expired = await coordinator.execute(approved.grant_id, actor=_media_actor())
    assert expired.status is ActionCoordinatorStatus.DENIED
    assert expired.code == "grant_expired"
    record = await store.get_grant_record(approved.grant_id)
    assert record is not None and record.status is GrantStatus.EXPIRED
    assert sent == []
    await store.close()


async def test_coordinator_rejects_invalid_ttl_and_naive_clock(tmp_path: Path) -> None:
    store = SQLiteActionStore(tmp_path / "jarvis.db", now=lambda: FIXED_NOW)
    engine = PermissionEngine(policy_version=POLICY_VERSION, now=lambda: FIXED_NOW)

    class NeverBroker:
        async def execute(self, grant, *, actor):  # type: ignore[no-untyped-def]
            raise AssertionError((grant, actor))

    with pytest.raises(ValueError, match="action_ttl"):
        ActionCoordinator(
            store=store,
            permission_engine=engine,
            broker=NeverBroker(),
            action_ttl=timedelta(0),
        )
    coordinator = ActionCoordinator(
        store=store,
        permission_engine=engine,
        broker=NeverBroker(),
        now=lambda: FIXED_NOW.replace(tzinfo=None),
    )
    handler = _media_handler([])
    with pytest.raises(ValueError, match="timezone-aware"):
        await coordinator.propose(
            handler,
            MediaControlArguments(operation=MediaOperation.STOP),
            actor=_media_actor(),
            source=ApprovalSource.TEST,
        )
