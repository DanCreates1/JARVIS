from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from jarvis.broker import LocalActionBroker
from jarvis.computer.actions import MediaControlHandler, MediaOperation
from jarvis.computer.audio import MasterVolumeState
from jarvis.computer.config import (
    AppGroupPolicy,
    ApplicationPolicy,
    ComputerAccessPolicy,
    HandsFreeMappingsPolicy,
)
from jarvis.computer.hands_free import (
    HandsFreeActionProposal,
    HandsFreeCancelDirective,
    HandsFreeCancelIntent,
    HandsFreeCoordinatorProposalConsumer,
    HandsFreeDecisionReason,
    HandsFreeDisposition,
    HandsFreeMediaNextTrackIntent,
    HandsFreeMediaNextTrackProposal,
    HandsFreeMediaPlayPauseIntent,
    HandsFreeMediaPlayPauseProposal,
    HandsFreeMediaPreviousTrackIntent,
    HandsFreeMediaPreviousTrackProposal,
    HandsFreeMuteToggleIntent,
    HandsFreeMuteToggleProposal,
    HandsFreeProposalGate,
    HandsFreeRequest,
    HandsFreeVolumeDownIntent,
    HandsFreeVolumeDownProposal,
    HandsFreeVolumeUpIntent,
    HandsFreeVolumeUpProposal,
)
from jarvis.computer.registry import ComputerActionRegistry
from jarvis.core import PermissionLevel
from jarvis.permissions import (
    ActionCoordinator,
    ActionCoordinatorStatus,
    ActorContext,
    ApprovalSource,
    AuthenticationAssurance,
    InteractionInterface,
    PermissionEngine,
    SQLiteActionStore,
)

FIXED_NOW = datetime(2026, 8, 22, 18, 0, tzinfo=UTC)
SOURCE_SESSION = "gesture-session-1"


def voice_actor(*, capabilities: tuple[str, ...] = ()) -> ActorContext:
    return ActorContext(
        host_id="host-1",
        session_id="actor-session-1",
        device_id="device-1",
        interface=InteractionInterface.VOICE,
        assurance=AuthenticationAssurance.LOCAL_SESSION,
        authenticated_at=FIXED_NOW,
        capabilities=capabilities,
    )


def policy(
    tmp_path: Path,
    *,
    mappings: HandsFreeMappingsPolicy | None = None,
) -> ComputerAccessPolicy:
    return ComputerAccessPolicy(
        enabled=True,
        policy_version="phase3-hands-free-test",
        controlled_root=tmp_path / "controlled-files",
        applications={
            "fixture": ApplicationPolicy(
                executable=tmp_path / "fixture.exe",
                sha256="a" * 64,
            )
        },
        app_groups={"main": AppGroupPolicy(applications=("fixture",))},
        hands_free_app_group="main",
        hands_free_mappings=mappings or HandsFreeMappingsPolicy(),
    )


def all_mappings() -> HandsFreeMappingsPolicy:
    return HandsFreeMappingsPolicy(
        volume_step=True,
        media_play_pause=True,
        mute_toggle=True,
        media_track_navigation=True,
        cancel_session=True,
    )


def intent(
    intent_type: type[Any],
    *,
    sequence: int = 1,
    session_id: str = SOURCE_SESSION,
    detected_at: datetime = FIXED_NOW,
    confidence: float = 0.95,
) -> Any:
    return intent_type(
        session_id=session_id,
        confidence=confidence,
        detected_at=detected_at,
        event_id=f"gesture-event-{sequence}",
    )


class GateHarness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        mappings: HandsFreeMappingsPolicy | None = None,
        actor: ActorContext | None = None,
        volume_reader=lambda: MasterVolumeState(scalar=0.48, muted=False),
    ) -> None:
        self.actor = actor or voice_actor()
        self.proposals: list[HandsFreeActionProposal] = []
        self.cancels: list[HandsFreeCancelDirective] = []
        self.decisions = []
        ids = count(1)
        self.gate = HandsFreeProposalGate(
            policy=policy(tmp_path, mappings=mappings),
            actor=self.actor,
            active_source_session_id=SOURCE_SESSION,
            proposal_callback=self.proposals.append,
            cancel_callback=self.cancels.append,
            decision_sink=self.decisions.append,
            volume_reader=volume_reader,
            now=lambda: FIXED_NOW,
            id_factory=lambda: f"{next(ids):016d}",
        )

    def request(
        self,
        detector_intent: Any,
        *,
        nonce: str = "nonce-0000000001",
        mapped_level: PermissionLevel = PermissionLevel.LEVEL_1,
    ) -> HandsFreeRequest:
        return HandsFreeRequest(
            intent=detector_intent,
            actor=self.actor,
            nonce=nonce,
            mapped_permission_level=mapped_level,
        )


def test_dormant_mappings_are_absent_by_default(tmp_path: Path) -> None:
    harness = GateHarness(tmp_path)

    decision = harness.gate.evaluate(harness.request(intent(HandsFreeVolumeUpIntent)))

    assert decision.reason is HandsFreeDecisionReason.MAPPING_NOT_CONFIGURED
    assert harness.proposals == []
    assert harness.gate.policy.hands_free_app_group == "main"
    assert harness.gate.policy.hands_free_mappings == HandsFreeMappingsPolicy()


@pytest.mark.parametrize(
    ("intent_type", "proposal_type", "action_id", "arguments"),
    [
        (
            HandsFreeVolumeUpIntent,
            HandsFreeVolumeUpProposal,
            "set_master_volume",
            {"percent": 53},
        ),
        (
            HandsFreeVolumeDownIntent,
            HandsFreeVolumeDownProposal,
            "set_master_volume",
            {"percent": 43},
        ),
        (
            HandsFreeMediaPlayPauseIntent,
            HandsFreeMediaPlayPauseProposal,
            "control_media",
            {"operation": MediaOperation.PLAY_PAUSE},
        ),
        (
            HandsFreeMuteToggleIntent,
            HandsFreeMuteToggleProposal,
            "control_media",
            {"operation": MediaOperation.MUTE_TOGGLE},
        ),
        (
            HandsFreeMediaPreviousTrackIntent,
            HandsFreeMediaPreviousTrackProposal,
            "control_media",
            {"operation": MediaOperation.PREVIOUS_TRACK},
        ),
        (
            HandsFreeMediaNextTrackIntent,
            HandsFreeMediaNextTrackProposal,
            "control_media",
            {"operation": MediaOperation.NEXT_TRACK},
        ),
    ],
)
def test_each_dormant_gesture_maps_to_one_closed_level_one_proposal(
    tmp_path: Path,
    intent_type: type[Any],
    proposal_type: type[Any],
    action_id: str,
    arguments: dict[str, object],
) -> None:
    harness = GateHarness(tmp_path, mappings=all_mappings())

    decision = harness.gate.evaluate(harness.request(intent(intent_type)))

    assert decision.disposition is HandsFreeDisposition.PROPOSE
    assert len(harness.proposals) == 1
    proposal = harness.proposals[0]
    assert isinstance(proposal, proposal_type)
    assert proposal.action_id == action_id
    assert proposal.arguments.model_dump() == arguments
    assert proposal.permission_level is PermissionLevel.LEVEL_1
    assert proposal.approval_granted is False
    assert proposal.execution_authorized is False


@pytest.mark.parametrize(
    ("intent_type", "scalar", "expected"),
    [
        (HandsFreeVolumeUpIntent, 0.98, 100),
        (HandsFreeVolumeDownIntent, 0.02, 0),
    ],
)
def test_volume_mapping_reads_current_state_and_clamps_fixed_five_percent_step(
    tmp_path: Path,
    intent_type: type[Any],
    scalar: float,
    expected: int,
) -> None:
    harness = GateHarness(
        tmp_path,
        mappings=all_mappings(),
        volume_reader=lambda: MasterVolumeState(scalar=scalar, muted=False),
    )

    harness.gate.evaluate(harness.request(intent(intent_type)))

    assert harness.proposals[0].arguments.model_dump() == {"percent": expected}


def test_volume_read_failure_denies_without_proposal(tmp_path: Path) -> None:
    def fail_read() -> MasterVolumeState:
        raise OSError("unavailable")

    harness = GateHarness(tmp_path, mappings=all_mappings(), volume_reader=fail_read)

    decision = harness.gate.evaluate(harness.request(intent(HandsFreeVolumeUpIntent)))

    assert decision.reason is HandsFreeDecisionReason.VOLUME_READ_FAILED
    assert harness.proposals == []


def test_cancel_is_session_scoped_and_cannot_encode_authority(tmp_path: Path) -> None:
    harness = GateHarness(tmp_path, mappings=all_mappings())
    wrong_session = harness.gate.evaluate(
        harness.request(intent(HandsFreeCancelIntent, session_id="other-session"))
    )
    accepted = harness.gate.evaluate(
        harness.request(intent(HandsFreeCancelIntent, sequence=2), nonce="nonce-0000000002")
    )

    assert wrong_session.reason is HandsFreeDecisionReason.SESSION_MISMATCH
    assert accepted.disposition is HandsFreeDisposition.CANCELLED
    assert len(harness.cancels) == 1
    directive = harness.cancels[0]
    assert directive.actor_session_id == harness.actor.session_id
    assert directive.source_session_id == SOURCE_SESSION
    assert directive.authority_created is False
    assert directive.approval_id is directive.grant_id is None
    assert "action_id" not in directive.model_dump()
    assert harness.proposals == []


@pytest.mark.parametrize("extra", [{"action_id": "delete"}, {"path": "C:/"}, {"delta": 90}])
def test_detector_payload_cannot_supply_action_path_or_numeric_delta(
    tmp_path: Path,
    extra: dict[str, object],
) -> None:
    del tmp_path
    with pytest.raises(ValidationError):
        HandsFreeVolumeUpIntent(
            session_id=SOURCE_SESSION,
            confidence=0.99,
            detected_at=FIXED_NOW,
            event_id="gesture-event-1",
            **extra,
        )


def test_unknown_intent_source_level_and_shared_guards_fail_closed(tmp_path: Path) -> None:
    harness = GateHarness(tmp_path, mappings=all_mappings())
    unknown_source = HandsFreeVolumeUpIntent.model_construct(
        session_id=SOURCE_SESSION,
        source="camera",
        intent="volume_up",
        confidence=0.99,
        detected_at=FIXED_NOW,
        event_id="gesture-event-1",
    )
    unknown_intent = HandsFreeVolumeUpIntent.model_construct(
        session_id=SOURCE_SESSION,
        source="gesture",
        intent="future_action",
        confidence=0.99,
        detected_at=FIXED_NOW,
        event_id="gesture-event-2",
    )

    assert harness.gate.evaluate(harness.request(unknown_source)).reason is (
        HandsFreeDecisionReason.SOURCE_DENIED
    )
    assert (
        harness.gate.evaluate(harness.request(unknown_intent, nonce="nonce-0000000002")).reason
        is HandsFreeDecisionReason.INTENT_DENIED
    )

    level_harness = GateHarness(tmp_path, mappings=all_mappings())
    level = level_harness.gate.evaluate(
        level_harness.request(
            intent(HandsFreeMediaPlayPauseIntent), mapped_level=PermissionLevel.LEVEL_2
        )
    )
    assert level.reason is HandsFreeDecisionReason.MAPPING_PERMISSION_DENIED
    assert level_harness.proposals == []


def test_gesture_mapping_uses_shared_freshness_replay_rate_and_session_checks(
    tmp_path: Path,
) -> None:
    stale = GateHarness(tmp_path, mappings=all_mappings())
    assert (
        stale.gate.evaluate(
            stale.request(
                intent(
                    HandsFreeMediaPlayPauseIntent,
                    detected_at=FIXED_NOW - timedelta(seconds=3),
                )
            )
        ).reason
        is HandsFreeDecisionReason.INTENT_STALE
    )

    harness = GateHarness(tmp_path, mappings=all_mappings())
    first_request = harness.request(intent(HandsFreeMediaPlayPauseIntent))
    assert harness.gate.evaluate(first_request).proposed is True
    assert harness.gate.evaluate(first_request).reason is HandsFreeDecisionReason.EVENT_REPLAY
    limited = harness.gate.evaluate(
        harness.request(
            intent(HandsFreeMediaNextTrackIntent, sequence=2),
            nonce="nonce-0000000002",
        )
    )
    assert limited.reason is HandsFreeDecisionReason.RATE_LIMITED


def test_proposal_models_cannot_mint_approval_or_change_fixed_operation(tmp_path: Path) -> None:
    harness = GateHarness(tmp_path, mappings=all_mappings())
    harness.gate.evaluate(harness.request(intent(HandsFreeMediaNextTrackIntent)))
    proposal = harness.proposals[0]
    assert type(TypeAdapter(HandsFreeActionProposal).validate_python(proposal.model_dump())) is (
        HandsFreeMediaNextTrackProposal
    )
    payload = proposal.model_dump()
    payload["approval_granted"] = True

    with pytest.raises(ValidationError):
        type(proposal).model_validate(payload)
    with pytest.raises(ValidationError):
        HandsFreeMediaNextTrackProposal(
            **{**proposal.model_dump(), "arguments": {"operation": "play_pause"}}
        )


def test_mapping_layer_never_starts_audio_camera_or_background_listener(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbid_start(_thread: threading.Thread) -> None:
        raise AssertionError("listener started")

    monkeypatch.setattr(threading.Thread, "start", forbid_start)
    harness = GateHarness(tmp_path, mappings=all_mappings())

    decision = harness.gate.evaluate(harness.request(intent(HandsFreeMediaPlayPauseIntent)))

    assert decision.proposed is True


async def test_consumer_reaches_only_coordinator_propose_with_hands_free_source(
    tmp_path: Path,
) -> None:
    sent = []

    def forbid_media_effect(key: object) -> object:
        sent.append(key)
        raise AssertionError("proposal consumer dispatched an effect")

    handler = MediaControlHandler(send_input=forbid_media_effect)  # type: ignore[arg-type]
    registry = ComputerActionRegistry([handler])
    actor = voice_actor(capabilities=("computer.media.control",))
    harness = GateHarness(tmp_path, mappings=all_mappings(), actor=actor)
    harness.gate.evaluate(harness.request(intent(HandsFreeMediaPlayPauseIntent)))
    proposal = harness.proposals[0]

    store = SQLiteActionStore(tmp_path / "hands-free.db", now=lambda: FIXED_NOW)
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
        result = await consumer.consume(proposal)
        assert result.status is ActionCoordinatorStatus.PENDING, result
        assert result.request is not None
        assert result.request.action.normalized_arguments == {"operation": "play_pause"}
        record = await store.get_approval_request(result.request.approval_id)
        assert record is not None and record.source is ApprovalSource.HANDS_FREE
        assert result.grant_id is None
        assert result.receipt is None
        assert sent == []
    finally:
        await store.close()
