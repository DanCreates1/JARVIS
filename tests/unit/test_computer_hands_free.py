from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from jarvis.computer.config import (
    AppGroupPolicy,
    ApplicationPolicy,
    ComputerAccessPolicy,
)
from jarvis.computer.hands_free import (
    BoundedHandsFreeReplayCache,
    HandsFreeDecisionReason,
    HandsFreeDecisionRecord,
    HandsFreeDisposition,
    HandsFreeProposal,
    HandsFreeProposalGate,
    HandsFreeRequest,
    ReplayClaim,
)
from jarvis.core import PermissionLevel
from jarvis.permissions import (
    ActorContext,
    AuthenticationAssurance,
    InteractionInterface,
)
from jarvis.voice.models import (
    AcousticEventType,
    HandsFreeIntent,
    HandsFreeIntentType,
)

FIXED_NOW = datetime(2026, 8, 22, 15, 30, tzinfo=UTC)
SOURCE_SESSION = "voice-session-1"


def local_voice_actor(**changes: object) -> ActorContext:
    values: dict[str, object] = {
        "host_id": "host-1",
        "session_id": "actor-session-1",
        "device_id": "device-1",
        "interface": InteractionInterface.VOICE,
        "assurance": AuthenticationAssurance.LOCAL_SESSION,
        "authenticated_at": FIXED_NOW,
        "capabilities": (),
    }
    values.update(changes)
    return ActorContext(**values)  # type: ignore[arg-type]


def access_policy(
    tmp_path: Path,
    *,
    enabled: bool = True,
    maximum_permission_level: PermissionLevel = PermissionLevel.LEVEL_2,
    hands_free_app_group: str | None = "main",
) -> ComputerAccessPolicy:
    application = ApplicationPolicy(
        executable=tmp_path / "fixture.exe",
        sha256="a" * 64,
    )
    return ComputerAccessPolicy(
        enabled=enabled,
        maximum_permission_level=maximum_permission_level,
        controlled_root=tmp_path / "controlled-files",
        applications={"fixture": application},
        app_groups={"main": AppGroupPolicy(applications=("fixture",))},
        hands_free_app_group=hands_free_app_group,
    )


def request(
    actor: ActorContext,
    *,
    sequence: int = 1,
    detected_at: datetime = FIXED_NOW,
    confidence: float = 0.95,
    source_session_id: str = SOURCE_SESSION,
    mapped_permission_level: PermissionLevel = PermissionLevel.LEVEL_1,
    nonce: str | None = None,
) -> HandsFreeRequest:
    return HandsFreeRequest(
        intent=HandsFreeIntent(
            session_id=source_session_id,
            source=AcousticEventType.DOUBLE_CLAP,
            intent=HandsFreeIntentType.LAUNCH_APP_GROUP,
            confidence=confidence,
            detected_at=detected_at,
            event_id=f"acoustic-event-{sequence}",
        ),
        actor=actor,
        nonce=nonce or f"nonce-{sequence:010d}",
        mapped_permission_level=mapped_permission_level,
    )


class GateHarness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        policy: ComputerAccessPolicy | None = None,
        actor: ActorContext | None = None,
        replay_store: BoundedHandsFreeReplayCache | None = None,
        **gate_options: Any,
    ) -> None:
        self.now = FIXED_NOW
        self.actor = actor or local_voice_actor()
        self.proposals: list[HandsFreeProposal] = []
        self.decisions: list[HandsFreeDecisionRecord] = []
        self.order: list[str] = []
        ids = count(1)

        def proposal_callback(proposal: HandsFreeProposal) -> None:
            self.order.append("proposal")
            self.proposals.append(proposal)

        def decision_sink(decision: HandsFreeDecisionRecord) -> None:
            self.order.append("decision")
            self.decisions.append(decision)

        self.gate = HandsFreeProposalGate(
            policy=policy or access_policy(tmp_path),
            actor=self.actor,
            active_source_session_id=SOURCE_SESSION,
            proposal_callback=proposal_callback,
            decision_sink=decision_sink,
            replay_store=replay_store,
            now=lambda: self.now,
            id_factory=lambda: f"{next(ids):016d}",
            **gate_options,
        )


@pytest.mark.parametrize(
    "policy_level",
    [PermissionLevel.LEVEL_1, PermissionLevel.LEVEL_2],
)
def test_exact_fresh_high_confidence_intent_emits_only_level_one_proposal(
    tmp_path: Path,
    policy_level: PermissionLevel,
) -> None:
    harness = GateHarness(
        tmp_path,
        policy=access_policy(tmp_path, maximum_permission_level=policy_level),
    )
    item = request(harness.actor, confidence=0.90)

    decision = harness.gate.evaluate(item)

    assert decision.disposition is HandsFreeDisposition.PROPOSE
    assert decision.reason is HandsFreeDecisionReason.PROPOSAL_READY
    assert decision.proposed is True
    assert harness.decisions == [decision]
    assert harness.order == ["decision", "proposal"]
    assert len(harness.proposals) == 1
    proposal = harness.proposals[0]
    assert proposal.event_id == item.intent.event_id
    assert proposal.nonce == item.nonce
    assert proposal.actor == harness.actor
    assert proposal.source_session_id == SOURCE_SESSION
    assert proposal.action_id == "launch_app_group"
    assert proposal.arguments.group_id == "main"
    assert proposal.policy_version == harness.gate.policy.policy_version
    assert proposal.permission_level is PermissionLevel.LEVEL_1
    assert proposal.app_group_id == "main"
    assert proposal.requires_trusted_review is True
    assert proposal.approval_granted is False
    assert proposal.execution_authorized is False
    assert proposal.expires_at - proposal.created_at == timedelta(seconds=30)


@pytest.mark.parametrize(
    ("policy_changes", "reason"),
    [
        ({"enabled": False}, HandsFreeDecisionReason.POLICY_DISABLED),
        (
            {"maximum_permission_level": PermissionLevel.LEVEL_0},
            HandsFreeDecisionReason.POLICY_LEVEL_DISALLOWED,
        ),
        (
            {"hands_free_app_group": None},
            HandsFreeDecisionReason.APP_GROUP_NOT_CONFIGURED,
        ),
    ],
)
def test_policy_must_enable_and_configure_level_one_mapping(
    tmp_path: Path,
    policy_changes: dict[str, object],
    reason: HandsFreeDecisionReason,
) -> None:
    policy = access_policy(tmp_path, **policy_changes)  # type: ignore[arg-type]
    harness = GateHarness(tmp_path, policy=policy)

    decision = harness.gate.evaluate(request(harness.actor))

    assert decision.disposition is HandsFreeDisposition.DENY
    assert decision.reason is reason
    assert harness.proposals == []
    assert harness.decisions == [decision]


@pytest.mark.parametrize(
    "mapped_level",
    [
        PermissionLevel.LEVEL_0,
        PermissionLevel.LEVEL_2,
        PermissionLevel.LEVEL_3,
        PermissionLevel.LEVEL_4,
    ],
)
def test_mapping_cannot_resolve_outside_fixed_level_one(
    tmp_path: Path,
    mapped_level: PermissionLevel,
) -> None:
    harness = GateHarness(tmp_path)

    decision = harness.gate.evaluate(request(harness.actor, mapped_permission_level=mapped_level))

    assert decision.disposition is HandsFreeDisposition.DENY
    assert decision.reason is HandsFreeDecisionReason.MAPPING_PERMISSION_DENIED
    assert harness.proposals == []


def test_actor_and_source_session_are_bound_exactly(tmp_path: Path) -> None:
    harness = GateHarness(tmp_path)
    cross_actor = local_voice_actor(session_id="actor-session-2")

    actor_denial = harness.gate.evaluate(request(cross_actor, sequence=1))
    source_denial = harness.gate.evaluate(
        request(harness.actor, sequence=2, source_session_id="voice-session-2")
    )

    assert actor_denial.reason is HandsFreeDecisionReason.ACTOR_MISMATCH
    assert source_denial.reason is HandsFreeDecisionReason.SESSION_MISMATCH
    assert harness.proposals == []


def test_non_voice_and_unauthenticated_actor_cannot_propose(tmp_path: Path) -> None:
    cli_actor = local_voice_actor(interface=InteractionInterface.LOCAL_CLI)
    cli_harness = GateHarness(tmp_path, actor=cli_actor)
    unauthenticated = local_voice_actor(
        assurance=AuthenticationAssurance.UNAUTHENTICATED,
        authenticated_at=None,
    )
    unauthenticated_harness = GateHarness(tmp_path, actor=unauthenticated)

    cli_decision = cli_harness.gate.evaluate(request(cli_actor))
    unauthenticated_decision = unauthenticated_harness.gate.evaluate(request(unauthenticated))

    assert cli_decision.reason is HandsFreeDecisionReason.ACTOR_INTERFACE_DENIED
    assert unauthenticated_decision.reason is HandsFreeDecisionReason.ACTOR_UNAUTHENTICATED
    assert cli_harness.proposals == unauthenticated_harness.proposals == []


@pytest.mark.parametrize(
    ("detected_at", "confidence", "reason"),
    [
        (
            FIXED_NOW - timedelta(seconds=2, milliseconds=1),
            0.95,
            HandsFreeDecisionReason.INTENT_STALE,
        ),
        (
            FIXED_NOW + timedelta(milliseconds=251),
            0.95,
            HandsFreeDecisionReason.INTENT_FROM_FUTURE,
        ),
        (FIXED_NOW, 0.899, HandsFreeDecisionReason.LOW_CONFIDENCE),
    ],
)
def test_freshness_skew_and_high_confidence_are_bounded(
    tmp_path: Path,
    detected_at: datetime,
    confidence: float,
    reason: HandsFreeDecisionReason,
) -> None:
    harness = GateHarness(tmp_path)

    decision = harness.gate.evaluate(
        request(harness.actor, detected_at=detected_at, confidence=confidence)
    )

    assert decision.reason is reason
    assert decision.disposition is HandsFreeDisposition.DENY
    assert harness.proposals == []


def test_naive_detector_timestamp_is_denied_and_safely_recorded(tmp_path: Path) -> None:
    harness = GateHarness(tmp_path)

    decision = harness.gate.evaluate(
        request(harness.actor, detected_at=FIXED_NOW.replace(tzinfo=None))
    )

    assert decision.reason is HandsFreeDecisionReason.INVALID_TIMESTAMP
    assert decision.detected_at is None
    assert harness.proposals == []


def test_event_and_nonce_replay_are_rejected_before_rate_limit(tmp_path: Path) -> None:
    harness = GateHarness(tmp_path)
    original = request(harness.actor, sequence=1)

    accepted = harness.gate.evaluate(original)
    event_replay = harness.gate.evaluate(original)
    nonce_replay = harness.gate.evaluate(request(harness.actor, sequence=2, nonce=original.nonce))

    assert accepted.proposed is True
    assert event_replay.reason is HandsFreeDecisionReason.EVENT_REPLAY
    assert nonce_replay.reason is HandsFreeDecisionReason.NONCE_REPLAY
    assert len(harness.proposals) == 1
    assert len(harness.decisions) == 3


def test_shared_replay_store_rejects_replay_after_gate_recreation(tmp_path: Path) -> None:
    replay_store = BoundedHandsFreeReplayCache()
    first = GateHarness(tmp_path, replay_store=replay_store)
    item = request(first.actor)
    assert first.gate.evaluate(item).proposed is True
    recreated = GateHarness(tmp_path, actor=first.actor, replay_store=replay_store)

    replay = recreated.gate.evaluate(item)

    assert replay.reason is HandsFreeDecisionReason.EVENT_REPLAY
    assert recreated.proposals == []


def test_rate_limit_denies_new_events_until_full_interval_elapses(tmp_path: Path) -> None:
    harness = GateHarness(tmp_path)
    assert harness.gate.evaluate(request(harness.actor, sequence=1)).proposed is True
    harness.now += timedelta(seconds=2)

    limited = harness.gate.evaluate(request(harness.actor, sequence=2, detected_at=harness.now))
    harness.now += timedelta(seconds=3)
    accepted = harness.gate.evaluate(request(harness.actor, sequence=3, detected_at=harness.now))

    assert limited.reason is HandsFreeDecisionReason.RATE_LIMITED
    assert accepted.proposed is True
    assert len(harness.proposals) == 2


def test_external_and_terminal_cancellation_consume_events_without_proposal(
    tmp_path: Path,
) -> None:
    harness = GateHarness(tmp_path)
    stop = threading.Event()
    stop.set()
    first = request(harness.actor, sequence=1)

    cancelled = harness.gate.evaluate(first, cancel=stop)
    stop.clear()
    replay = harness.gate.evaluate(first, cancel=stop)
    harness.gate.cancel()
    terminal = harness.gate.evaluate(request(harness.actor, sequence=2))

    assert cancelled.disposition is HandsFreeDisposition.CANCELLED
    assert cancelled.reason is HandsFreeDecisionReason.CANCELLED
    assert replay.reason is HandsFreeDecisionReason.EVENT_REPLAY
    assert terminal.disposition is HandsFreeDisposition.CANCELLED
    assert harness.proposals == []


def test_future_unknown_intent_and_source_fail_closed(tmp_path: Path) -> None:
    harness = GateHarness(tmp_path)
    unknown_intent = HandsFreeIntent.model_construct(
        session_id=SOURCE_SESSION,
        source=AcousticEventType.DOUBLE_CLAP,
        intent="future_intent",
        confidence=0.99,
        detected_at=FIXED_NOW,
        event_id="acoustic-event-1",
    )
    unknown_source = HandsFreeIntent.model_construct(
        session_id=SOURCE_SESSION,
        source="future_source",
        intent=HandsFreeIntentType.LAUNCH_APP_GROUP,
        confidence=0.99,
        detected_at=FIXED_NOW,
        event_id="acoustic-event-2",
    )

    intent_decision = harness.gate.evaluate(
        HandsFreeRequest(
            intent=unknown_intent,
            actor=harness.actor,
            nonce="nonce-0000000001",
        )
    )
    source_decision = harness.gate.evaluate(
        HandsFreeRequest(
            intent=unknown_source,
            actor=harness.actor,
            nonce="nonce-0000000002",
        )
    )

    assert intent_decision.reason is HandsFreeDecisionReason.INTENT_DENIED
    assert source_decision.reason is HandsFreeDecisionReason.SOURCE_DENIED
    assert harness.proposals == []


def test_decision_sink_failure_blocks_proposal_callback(tmp_path: Path) -> None:
    proposals: list[HandsFreeProposal] = []
    actor = local_voice_actor()

    def fail_sink(_decision: HandsFreeDecisionRecord) -> None:
        raise OSError("audit unavailable")

    gate = HandsFreeProposalGate(
        policy=access_policy(tmp_path),
        actor=actor,
        active_source_session_id=SOURCE_SESSION,
        proposal_callback=proposals.append,
        decision_sink=fail_sink,
        now=lambda: FIXED_NOW,
    )

    with pytest.raises(OSError, match="audit unavailable"):
        gate.evaluate(request(actor))

    assert proposals == []


def test_replay_cache_is_bounded_and_expires_claims() -> None:
    cache = BoundedHandsFreeReplayCache(maximum_entries=16)
    expiry = FIXED_NOW + timedelta(seconds=10)
    for index in range(16):
        assert (
            cache.claim(
                event_id=f"event-{index}",
                nonce=f"nonce-{index:010d}",
                observed_at=FIXED_NOW,
                retain_until=expiry,
            )
            is ReplayClaim.CLAIMED
        )

    assert (
        cache.claim(
            event_id="event-overflow",
            nonce="nonce-9999999999",
            observed_at=FIXED_NOW,
            retain_until=expiry,
        )
        is ReplayClaim.CAPACITY_EXHAUSTED
    )
    assert (
        cache.claim(
            event_id="event-0",
            nonce="nonce-new-0000001",
            observed_at=FIXED_NOW,
            retain_until=expiry,
        )
        is ReplayClaim.EVENT_REPLAY
    )
    later = expiry + timedelta(microseconds=1)
    assert (
        cache.claim(
            event_id="event-new",
            nonce="nonce-9999999999",
            observed_at=later,
            retain_until=later + timedelta(seconds=10),
        )
        is ReplayClaim.CLAIMED
    )


def test_models_cannot_encode_approval_or_execution_authority(tmp_path: Path) -> None:
    harness = GateHarness(tmp_path)
    assert harness.gate.evaluate(request(harness.actor)).proposed is True
    proposal_data = harness.proposals[0].model_dump()
    proposal_data["approval_granted"] = True

    with pytest.raises(ValidationError):
        HandsFreeProposal.model_validate(proposal_data)


@pytest.mark.parametrize(
    "options",
    [
        {"confidence_threshold": 0.79},
        {"max_intent_age": timedelta(seconds=11)},
        {"max_future_skew": timedelta(seconds=2)},
        {"rate_limit": timedelta(milliseconds=999)},
        {"replay_retention": timedelta(seconds=1)},
        {"proposal_ttl": timedelta(seconds=31)},
    ],
)
def test_gate_configuration_cannot_weaken_safety_bounds(
    tmp_path: Path,
    options: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        GateHarness(tmp_path, **cast(dict[str, Any], options))
