from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from pathlib import Path

import pytest

from jarvis.broker import LocalActionBroker
from jarvis.computer.actions import MediaControlHandler
from jarvis.computer.config import ComputerAccessPolicy, HandsFreeMappingsPolicy
from jarvis.computer.gesture_bridge import GestureHandsFreeGateSink, GestureIntentMapper
from jarvis.computer.hands_free import (
    HandsFreeActionProposal,
    HandsFreeCancelDirective,
    HandsFreeCoordinatorProposalConsumer,
    HandsFreeDecisionReason,
    HandsFreeDisposition,
    HandsFreeGestureIntentType,
    HandsFreeProposalGate,
)
from jarvis.computer.registry import ComputerActionRegistry
from jarvis.gestures.models import GestureKind, GestureObservation, Handedness
from jarvis.permissions import (
    ActionCoordinator,
    ActionCoordinatorStatus,
    ActorContext,
    AuthenticationAssurance,
    InteractionInterface,
    PermissionEngine,
    SQLiteActionStore,
)

FIXED_NOW = datetime(2026, 9, 8, 22, 0, tzinfo=UTC)
SOURCE_SESSION = "gesture-session-7c"


def actor() -> ActorContext:
    return ActorContext(
        host_id="host-1",
        session_id="actor-session-1",
        device_id="device-1",
        interface=InteractionInterface.VOICE,
        assurance=AuthenticationAssurance.LOCAL_SESSION,
        authenticated_at=FIXED_NOW,
        capabilities=("computer.media.control", "computer.volume.set"),
    )


def policy(tmp_path: Path, *, enabled: bool = True) -> ComputerAccessPolicy:
    return ComputerAccessPolicy(
        enabled=enabled,
        policy_version="phase7c-test",
        controlled_root=tmp_path / "controlled",
        hands_free_mappings=HandsFreeMappingsPolicy(
            volume_step=True,
            media_play_pause=True,
            mute_toggle=True,
            cancel_session=True,
        ),
    )


def observation(
    gesture: GestureKind,
    *,
    sequence: int = 1,
    session_id: str = SOURCE_SESSION,
    confidence: float = 0.96,
) -> GestureObservation:
    return GestureObservation(
        event_id=f"gesture-event-{sequence}",
        session_id=session_id,
        gesture=gesture,
        handedness=Handedness.RIGHT,
        confidence=confidence,
        started_at=FIXED_NOW,
        detected_at=FIXED_NOW,
        start_sequence=sequence,
        end_sequence=sequence,
    )


class Harness:
    def __init__(self, tmp_path: Path, *, enabled: bool = True) -> None:
        self.actor = actor()
        self.proposals: list[HandsFreeActionProposal] = []
        self.cancels: list[HandsFreeCancelDirective] = []
        self.decisions = []
        ids = count(1)
        self.gate = HandsFreeProposalGate(
            policy=policy(tmp_path, enabled=enabled),
            actor=self.actor,
            active_source_session_id=SOURCE_SESSION,
            proposal_callback=self.proposals.append,
            cancel_callback=self.cancels.append,
            decision_sink=self.decisions.append,
            now=lambda: FIXED_NOW,
            id_factory=lambda: f"{next(ids):016d}",
        )
        self.sink = GestureHandsFreeGateSink(gate=self.gate, actor=self.actor)


@pytest.mark.parametrize(
    ("gesture", "intent"),
    [
        (GestureKind.CLOSED_FIST, HandsFreeGestureIntentType.CANCEL),
        (GestureKind.OPEN_PALM, HandsFreeGestureIntentType.MEDIA_PLAY_PAUSE),
        (GestureKind.PINCH, HandsFreeGestureIntentType.MUTE_TOGGLE),
        (GestureKind.FINGER_ROLL_CLOCKWISE, HandsFreeGestureIntentType.VOLUME_UP),
        (
            GestureKind.FINGER_ROLL_COUNTERCLOCKWISE,
            HandsFreeGestureIntentType.VOLUME_DOWN,
        ),
    ],
)
def test_mapper_has_one_exact_argument_free_mapping(
    gesture: GestureKind,
    intent: HandsFreeGestureIntentType,
) -> None:
    mapped = GestureIntentMapper().map(observation(gesture))

    assert mapped.intent is intent
    assert mapped.event_id == "gesture-event-1"
    assert mapped.session_id == SOURCE_SESSION
    assert mapped.confidence == 0.96
    assert set(mapped.model_dump()) == {
        "session_id",
        "source",
        "confidence",
        "detected_at",
        "event_id",
        "intent",
    }


def test_mapper_revalidates_constructed_unknown_gesture() -> None:
    malformed = observation(GestureKind.OPEN_PALM).model_copy()
    object.__setattr__(malformed, "gesture", "delete_everything")

    with pytest.raises(ValueError):
        GestureIntentMapper().map(malformed)


def test_mapping_table_is_immutable() -> None:
    mapping = GestureIntentMapper().mapping

    with pytest.raises(TypeError):
        mapping[GestureKind.OPEN_PALM] = HandsFreeGestureIntentType.CANCEL  # type: ignore[index]


@pytest.mark.asyncio
async def test_sink_reaches_phase3_gate_but_never_executes(tmp_path: Path) -> None:
    harness = Harness(tmp_path)

    await harness.sink(observation(GestureKind.PINCH))

    assert len(harness.proposals) == 1
    proposal = harness.proposals[0]
    assert proposal.intent is HandsFreeGestureIntentType.MUTE_TOGGLE
    assert proposal.action_id == "control_media"
    assert proposal.arguments.model_dump() == {"operation": "mute_toggle"}
    assert proposal.approval_granted is False
    assert proposal.execution_authorized is False
    assert harness.decisions[0].disposition is HandsFreeDisposition.PROPOSE


@pytest.mark.asyncio
async def test_pinch_reaches_coordinator_as_pending_mute_without_effect(tmp_path: Path) -> None:
    sent = []

    def forbid_effect(key: object) -> object:
        sent.append(key)
        raise AssertionError("gesture proposal dispatched an effect")

    harness = Harness(tmp_path)
    await harness.sink(observation(GestureKind.PINCH))
    handler = MediaControlHandler(send_input=forbid_effect)  # type: ignore[arg-type]
    registry = ComputerActionRegistry([handler])
    store = SQLiteActionStore(tmp_path / "phase7c.db", now=lambda: FIXED_NOW)
    await store.initialize()
    broker = LocalActionBroker(
        [handler],
        state_store=store,
        audit_store=store,
        policy_version=harness.gate.policy.policy_version,
        now=lambda: FIXED_NOW,
    )
    coordinator = ActionCoordinator(
        store=store,
        permission_engine=PermissionEngine(
            policy_version=harness.gate.policy.policy_version,
            now=lambda: FIXED_NOW,
        ),
        broker=broker,
        now=lambda: FIXED_NOW,
    )
    consumer = HandsFreeCoordinatorProposalConsumer(
        coordinator=coordinator,
        registry=registry,
        now=lambda: FIXED_NOW,
    )
    try:
        result = await consumer.consume(harness.proposals[0])
        assert result.status is ActionCoordinatorStatus.PENDING
        assert result.request is not None
        assert result.request.action.normalized_arguments == {"operation": "mute_toggle"}
        assert result.grant_id is None
        assert result.receipt is None
        assert sent == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_closed_fist_cancels_bound_session_and_blocks_later_events(tmp_path: Path) -> None:
    harness = Harness(tmp_path)

    await harness.sink(observation(GestureKind.CLOSED_FIST))
    await harness.sink(observation(GestureKind.OPEN_PALM, sequence=2))

    assert harness.proposals == []
    assert len(harness.cancels) == 1
    assert harness.cancels[0].authority_created is False
    assert [decision.disposition for decision in harness.decisions] == [
        HandsFreeDisposition.CANCELLED,
        HandsFreeDisposition.CANCELLED,
    ]


@pytest.mark.asyncio
async def test_policy_disable_session_mismatch_and_replay_fail_closed(tmp_path: Path) -> None:
    disabled = Harness(tmp_path, enabled=False)
    await disabled.sink(observation(GestureKind.OPEN_PALM))
    assert disabled.decisions[0].reason is HandsFreeDecisionReason.POLICY_DISABLED
    assert disabled.proposals == []

    harness = Harness(tmp_path)
    wrong = observation(GestureKind.OPEN_PALM, session_id="other-session")
    await harness.sink(wrong)
    assert harness.decisions[-1].reason is HandsFreeDecisionReason.SESSION_MISMATCH
    assert harness.proposals == []

    item = observation(GestureKind.OPEN_PALM, sequence=2)
    await harness.sink(item)
    await harness.sink(item)
    assert harness.decisions[-1].reason is HandsFreeDecisionReason.EVENT_REPLAY
    assert len(harness.proposals) == 1


def test_sink_rejects_actor_mismatch_at_composition() -> None:
    gate_actor = actor()
    other_actor = gate_actor.model_copy(update={"session_id": "other-actor-session"})
    gate = HandsFreeProposalGate(
        policy=ComputerAccessPolicy(
            enabled=True,
            policy_version="phase7c-test",
            controlled_root=Path("C:/controlled"),
        ),
        actor=gate_actor,
        active_source_session_id=SOURCE_SESSION,
        proposal_callback=lambda _proposal: None,
        decision_sink=lambda _decision: None,
        now=lambda: FIXED_NOW,
    )

    with pytest.raises(ValueError, match="actor must match"):
        GestureHandsFreeGateSink(gate=gate, actor=other_actor)
