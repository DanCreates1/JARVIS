"""Closed Phase 7 gesture-observation bridge into the Phase 3 proposal gate."""

from __future__ import annotations

import hashlib
from types import MappingProxyType

from jarvis.gestures.models import GestureKind, GestureObservation
from jarvis.permissions import ActorContext

from .hands_free import (
    HandsFreeCancelIntent,
    HandsFreeGestureIntent,
    HandsFreeGestureIntentType,
    HandsFreeMediaPlayPauseIntent,
    HandsFreeMuteToggleIntent,
    HandsFreeProposalGate,
    HandsFreeRequest,
    HandsFreeVolumeDownIntent,
    HandsFreeVolumeUpIntent,
)

_CLOSED_MAPPING: MappingProxyType[GestureKind, HandsFreeGestureIntentType] = MappingProxyType(
    {
        GestureKind.CLOSED_FIST: HandsFreeGestureIntentType.CANCEL,
        GestureKind.OPEN_PALM: HandsFreeGestureIntentType.MEDIA_PLAY_PAUSE,
        GestureKind.PINCH: HandsFreeGestureIntentType.MUTE_TOGGLE,
        GestureKind.FINGER_ROLL_CLOCKWISE: HandsFreeGestureIntentType.VOLUME_UP,
        GestureKind.FINGER_ROLL_COUNTERCLOCKWISE: HandsFreeGestureIntentType.VOLUME_DOWN,
    }
)


def _event_nonce(observation: GestureObservation) -> str:
    payload = (
        f"{observation.session_id}\0{observation.event_id}\0"
        f"{observation.start_sequence}\0{observation.end_sequence}"
    ).encode("utf-8", errors="strict")
    return f"gesture-{hashlib.sha256(payload).hexdigest()}"


class GestureIntentMapper:
    """Map one validated observation to one argument-free closed intent."""

    @property
    def mapping(self) -> MappingProxyType[GestureKind, HandsFreeGestureIntentType]:
        return _CLOSED_MAPPING

    def map(self, observation: GestureObservation) -> HandsFreeGestureIntent:
        validated = _validated_observation(observation)
        mapped = _CLOSED_MAPPING.get(validated.gesture)
        if mapped is None:
            raise ValueError("gesture has no closed intent mapping")
        if mapped is HandsFreeGestureIntentType.CANCEL:
            return HandsFreeCancelIntent(
                session_id=validated.session_id,
                confidence=validated.confidence,
                detected_at=validated.detected_at,
                event_id=validated.event_id,
            )
        if mapped is HandsFreeGestureIntentType.MEDIA_PLAY_PAUSE:
            return HandsFreeMediaPlayPauseIntent(
                session_id=validated.session_id,
                confidence=validated.confidence,
                detected_at=validated.detected_at,
                event_id=validated.event_id,
            )
        if mapped is HandsFreeGestureIntentType.MUTE_TOGGLE:
            return HandsFreeMuteToggleIntent(
                session_id=validated.session_id,
                confidence=validated.confidence,
                detected_at=validated.detected_at,
                event_id=validated.event_id,
            )
        if mapped is HandsFreeGestureIntentType.VOLUME_UP:
            return HandsFreeVolumeUpIntent(
                session_id=validated.session_id,
                confidence=validated.confidence,
                detected_at=validated.detected_at,
                event_id=validated.event_id,
            )
        if mapped is HandsFreeGestureIntentType.VOLUME_DOWN:
            return HandsFreeVolumeDownIntent(
                session_id=validated.session_id,
                confidence=validated.confidence,
                detected_at=validated.detected_at,
                event_id=validated.event_id,
            )
        raise AssertionError("closed gesture mapping is incomplete")


class GestureHandsFreeGateSink:
    """Foreground sink that enters Phase 3 policy; it never approves or executes."""

    def __init__(
        self,
        *,
        gate: HandsFreeProposalGate,
        actor: ActorContext,
        mapper: GestureIntentMapper | None = None,
    ) -> None:
        if not isinstance(gate, HandsFreeProposalGate):
            raise TypeError("gesture sink requires HandsFreeProposalGate")
        if not isinstance(actor, ActorContext):
            raise TypeError("gesture sink requires ActorContext")
        if actor != gate.actor:
            raise ValueError("gesture sink actor must match the Phase 3 gate actor")
        self._gate = gate
        self._actor = actor
        self._mapper = mapper or GestureIntentMapper()

    async def __call__(self, observation: GestureObservation) -> None:
        validated = _validated_observation(observation)
        intent = self._mapper.map(validated)
        nonce = _event_nonce(validated)
        self._gate.evaluate(
            HandsFreeRequest(
                intent=intent,
                actor=self._actor,
                nonce=nonce,
            )
        )


def _validated_observation(observation: GestureObservation) -> GestureObservation:
    if not isinstance(observation, GestureObservation):
        raise TypeError("gesture mapping requires GestureObservation")
    return GestureObservation.model_validate(observation.model_dump(warnings=False))
