"""Fail-closed Phase 3 gate from acoustic intent data to low-risk proposals.

This module cannot approve or execute an action. It accepts the fixed Phase 2
double-clap shape plus default-off synthetic Phase 3 gesture contracts. It can
emit only closed Level 1 proposals, or a session-scoped no-authority cancel
directive. A trusted caller must still canonicalize, review, approve, and
dispatch every action proposal through the Phase 3 permission broker.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self, TypeAlias, TypedDict, runtime_checkable
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from jarvis.computer.actions import (
    AppGroupLaunchArguments,
    MediaControlArguments,
    MediaOperation,
)
from jarvis.computer.audio import MasterVolumeState, get_master_volume_state
from jarvis.computer.config import ComputerAccessPolicy
from jarvis.computer.extra_actions import SetMasterVolumeArguments
from jarvis.computer.registry import ComputerActionRegistry
from jarvis.core import PermissionLevel
from jarvis.core.models import CoreModel, Identifier
from jarvis.permissions import (
    ActionCoordinator,
    ActionCoordinatorResult,
    ActorContext,
    ApprovalSource,
    AuthenticationAssurance,
    InteractionInterface,
    sha256_fingerprint,
)
from jarvis.voice.models import (
    AcousticEventType,
    HandsFreeIntent,
    HandsFreeIntentType,
)

_DEFAULT_CONFIDENCE_THRESHOLD = 0.90
_DEFAULT_MAX_INTENT_AGE = timedelta(seconds=2)
_DEFAULT_MAX_FUTURE_SKEW = timedelta(milliseconds=250)
_DEFAULT_RATE_LIMIT = timedelta(seconds=5)
_DEFAULT_REPLAY_RETENTION = timedelta(minutes=10)
_DEFAULT_PROPOSAL_TTL = timedelta(seconds=30)

Nonce = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$",
    ),
]


class _GateModel(CoreModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class HandsFreeSignalSource(StrEnum):
    """Phase 3 source vocabulary; no gesture detector is implemented here."""

    GESTURE = "gesture"


class HandsFreeGestureIntentType(StrEnum):
    """Closed dormant gesture vocabulary owned by the Phase 3 mapping layer."""

    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    MEDIA_PLAY_PAUSE = "media_play_pause"
    MEDIA_PREVIOUS_TRACK = "media_previous_track"
    MEDIA_NEXT_TRACK = "media_next_track"
    CANCEL = "cancel"


class _HandsFreeGestureIntentBase(_GateModel):
    session_id: Identifier
    source: Literal[HandsFreeSignalSource.GESTURE] = HandsFreeSignalSource.GESTURE
    confidence: Annotated[float, Field(ge=0, le=1)]
    detected_at: datetime
    event_id: Identifier


class HandsFreeVolumeUpIntent(_HandsFreeGestureIntentBase):
    intent: Literal[HandsFreeGestureIntentType.VOLUME_UP] = HandsFreeGestureIntentType.VOLUME_UP


class HandsFreeVolumeDownIntent(_HandsFreeGestureIntentBase):
    intent: Literal[HandsFreeGestureIntentType.VOLUME_DOWN] = HandsFreeGestureIntentType.VOLUME_DOWN


class HandsFreeMediaPlayPauseIntent(_HandsFreeGestureIntentBase):
    intent: Literal[HandsFreeGestureIntentType.MEDIA_PLAY_PAUSE] = (
        HandsFreeGestureIntentType.MEDIA_PLAY_PAUSE
    )


class HandsFreeMediaPreviousTrackIntent(_HandsFreeGestureIntentBase):
    intent: Literal[HandsFreeGestureIntentType.MEDIA_PREVIOUS_TRACK] = (
        HandsFreeGestureIntentType.MEDIA_PREVIOUS_TRACK
    )


class HandsFreeMediaNextTrackIntent(_HandsFreeGestureIntentBase):
    intent: Literal[HandsFreeGestureIntentType.MEDIA_NEXT_TRACK] = (
        HandsFreeGestureIntentType.MEDIA_NEXT_TRACK
    )


class HandsFreeCancelIntent(_HandsFreeGestureIntentBase):
    intent: Literal[HandsFreeGestureIntentType.CANCEL] = HandsFreeGestureIntentType.CANCEL


HandsFreeGestureIntent: TypeAlias = (
    HandsFreeVolumeUpIntent
    | HandsFreeVolumeDownIntent
    | HandsFreeMediaPlayPauseIntent
    | HandsFreeMediaPreviousTrackIntent
    | HandsFreeMediaNextTrackIntent
    | HandsFreeCancelIntent
)
HandsFreeGateIntent: TypeAlias = HandsFreeIntent | HandsFreeGestureIntent


class HandsFreeRequest(_GateModel):
    """One detector event bound to a trusted actor and a caller-generated nonce."""

    intent: HandsFreeGateIntent
    actor: ActorContext
    nonce: Nonce
    mapped_permission_level: PermissionLevel = PermissionLevel.LEVEL_1


class _HandsFreeProposalBase(_GateModel):
    """Authority-free fields shared by every closed Phase 3 proposal variant."""

    proposal_id: Identifier
    event_id: Identifier
    nonce: Nonce
    actor: ActorContext
    source_session_id: Identifier
    permission_level: Literal[PermissionLevel.LEVEL_1] = PermissionLevel.LEVEL_1
    policy_version: Identifier
    created_at: datetime
    expires_at: datetime
    requires_trusted_review: Literal[True] = True
    approval_granted: Literal[False] = False
    execution_authorized: Literal[False] = False

    @field_validator("created_at", "expires_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime, info: object) -> datetime:
        return _aware_utc(value, field_name=getattr(info, "field_name", "timestamp"))

    @model_validator(mode="after")
    def validate_ttl(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("hands-free proposal expiry must follow creation")
        if self.expires_at - self.created_at > _DEFAULT_PROPOSAL_TTL:
            raise ValueError("hands-free proposal TTL exceeds 30 seconds")
        return self


class HandsFreeProposal(_HandsFreeProposalBase):
    """Backward-compatible double-clap proposal for one configured app group."""

    source: Literal[AcousticEventType.DOUBLE_CLAP] = AcousticEventType.DOUBLE_CLAP
    intent: Literal[HandsFreeIntentType.LAUNCH_APP_GROUP] = HandsFreeIntentType.LAUNCH_APP_GROUP
    action_id: Literal["launch_app_group"] = "launch_app_group"
    arguments: AppGroupLaunchArguments
    app_group_id: Identifier

    @model_validator(mode="after")
    def bind_group_argument(self) -> Self:
        if self.arguments.group_id != self.app_group_id:
            raise ValueError("hands-free app-group argument must match configured group")
        return self


class HandsFreeVolumeUpProposal(_HandsFreeProposalBase):
    source: Literal[HandsFreeSignalSource.GESTURE] = HandsFreeSignalSource.GESTURE
    intent: Literal[HandsFreeGestureIntentType.VOLUME_UP] = HandsFreeGestureIntentType.VOLUME_UP
    action_id: Literal["set_master_volume"] = "set_master_volume"
    observed_percent: Annotated[int, Field(strict=True, ge=0, le=100)]
    arguments: SetMasterVolumeArguments

    @model_validator(mode="after")
    def bind_fixed_step(self) -> Self:
        if self.arguments.percent != min(100, self.observed_percent + 5):
            raise ValueError("volume-up proposal must be one clamped five-percent step")
        return self


class HandsFreeVolumeDownProposal(_HandsFreeProposalBase):
    source: Literal[HandsFreeSignalSource.GESTURE] = HandsFreeSignalSource.GESTURE
    intent: Literal[HandsFreeGestureIntentType.VOLUME_DOWN] = HandsFreeGestureIntentType.VOLUME_DOWN
    action_id: Literal["set_master_volume"] = "set_master_volume"
    observed_percent: Annotated[int, Field(strict=True, ge=0, le=100)]
    arguments: SetMasterVolumeArguments

    @model_validator(mode="after")
    def bind_fixed_step(self) -> Self:
        if self.arguments.percent != max(0, self.observed_percent - 5):
            raise ValueError("volume-down proposal must be one clamped five-percent step")
        return self


class HandsFreeMediaPlayPauseProposal(_HandsFreeProposalBase):
    source: Literal[HandsFreeSignalSource.GESTURE] = HandsFreeSignalSource.GESTURE
    intent: Literal[HandsFreeGestureIntentType.MEDIA_PLAY_PAUSE] = (
        HandsFreeGestureIntentType.MEDIA_PLAY_PAUSE
    )
    action_id: Literal["control_media"] = "control_media"
    arguments: MediaControlArguments

    @model_validator(mode="after")
    def bind_operation(self) -> Self:
        if self.arguments.operation is not MediaOperation.PLAY_PAUSE:
            raise ValueError("play-pause proposal requires play_pause operation")
        return self


class HandsFreeMediaPreviousTrackProposal(_HandsFreeProposalBase):
    source: Literal[HandsFreeSignalSource.GESTURE] = HandsFreeSignalSource.GESTURE
    intent: Literal[HandsFreeGestureIntentType.MEDIA_PREVIOUS_TRACK] = (
        HandsFreeGestureIntentType.MEDIA_PREVIOUS_TRACK
    )
    action_id: Literal["control_media"] = "control_media"
    arguments: MediaControlArguments

    @model_validator(mode="after")
    def bind_operation(self) -> Self:
        if self.arguments.operation is not MediaOperation.PREVIOUS_TRACK:
            raise ValueError("previous-track proposal requires previous_track operation")
        return self


class HandsFreeMediaNextTrackProposal(_HandsFreeProposalBase):
    source: Literal[HandsFreeSignalSource.GESTURE] = HandsFreeSignalSource.GESTURE
    intent: Literal[HandsFreeGestureIntentType.MEDIA_NEXT_TRACK] = (
        HandsFreeGestureIntentType.MEDIA_NEXT_TRACK
    )
    action_id: Literal["control_media"] = "control_media"
    arguments: MediaControlArguments

    @model_validator(mode="after")
    def bind_operation(self) -> Self:
        if self.arguments.operation is not MediaOperation.NEXT_TRACK:
            raise ValueError("next-track proposal requires next_track operation")
        return self


HandsFreeActionProposal: TypeAlias = Annotated[
    HandsFreeProposal
    | HandsFreeVolumeUpProposal
    | HandsFreeVolumeDownProposal
    | HandsFreeMediaPlayPauseProposal
    | HandsFreeMediaPreviousTrackProposal
    | HandsFreeMediaNextTrackProposal,
    Field(discriminator="intent"),
]


class _ProposalFields(TypedDict):
    proposal_id: str
    event_id: str
    nonce: str
    actor: ActorContext
    source_session_id: str
    policy_version: str
    created_at: datetime
    expires_at: datetime


class HandsFreeCancelDirective(_GateModel):
    """Session-scoped cancellation marker that cannot encode action authority."""

    directive_id: Identifier
    event_id: Identifier
    nonce: Nonce
    host_id: Identifier
    actor_session_id: Identifier
    device_id: Identifier
    source_session_id: Identifier
    source: Literal[HandsFreeSignalSource.GESTURE] = HandsFreeSignalSource.GESTURE
    intent: Literal[HandsFreeGestureIntentType.CANCEL] = HandsFreeGestureIntentType.CANCEL
    created_at: datetime
    authority_created: Literal[False] = False
    approval_id: Literal[None] = None
    grant_id: Literal[None] = None
    cancels_only_bound_session: Literal[True] = True

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="created_at")


class HandsFreeDisposition(StrEnum):
    PROPOSE = "propose"
    DENY = "deny"
    CANCELLED = "cancelled"


class HandsFreeDecisionReason(StrEnum):
    PROPOSAL_READY = "proposal_ready"
    CANCELLED = "cancelled"
    EVENT_REPLAY = "event_replay"
    NONCE_REPLAY = "nonce_replay"
    REPLAY_CAPACITY_EXHAUSTED = "replay_capacity_exhausted"
    POLICY_DISABLED = "policy_disabled"
    MAPPING_PERMISSION_DENIED = "mapping_permission_denied"
    POLICY_LEVEL_DISALLOWED = "policy_level_disallowed"
    APP_GROUP_NOT_CONFIGURED = "app_group_not_configured"
    MAPPING_NOT_CONFIGURED = "mapping_not_configured"
    VOLUME_READ_FAILED = "volume_read_failed"
    ACTOR_MISMATCH = "actor_mismatch"
    ACTOR_INTERFACE_DENIED = "actor_interface_denied"
    ACTOR_UNAUTHENTICATED = "actor_unauthenticated"
    SESSION_MISMATCH = "session_mismatch"
    INTENT_DENIED = "intent_denied"
    SOURCE_DENIED = "source_denied"
    INVALID_TIMESTAMP = "invalid_timestamp"
    INTENT_STALE = "intent_stale"
    INTENT_FROM_FUTURE = "intent_from_future"
    LOW_CONFIDENCE = "low_confidence"
    RATE_LIMITED = "rate_limited"


class HandsFreeDecisionRecord(_GateModel):
    """Sanitized terminal gate decision suitable for a durable audit sink."""

    decision_id: Identifier
    disposition: HandsFreeDisposition
    reason: HandsFreeDecisionReason
    event_id: Identifier
    nonce: Nonce
    actor: ActorContext
    active_source_session_id: Identifier
    observed_source_session_id: Identifier
    intent: Annotated[str, Field(min_length=1, max_length=100)]
    source: Annotated[str, Field(min_length=1, max_length=100)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    requested_permission_level: PermissionLevel
    policy_version: Identifier
    action_id: Literal["launch_app_group", "set_master_volume", "control_media"] | None = None
    app_group_id: Identifier | None = None
    proposal_id: Identifier | None = None
    detected_at: datetime | None = None
    decided_at: datetime

    @field_validator("detected_at", "decided_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None, info: object) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, field_name=getattr(info, "field_name", "timestamp"))

    @model_validator(mode="after")
    def validate_decision_shape(self) -> Self:
        if self.disposition is HandsFreeDisposition.PROPOSE:
            if self.reason is not HandsFreeDecisionReason.PROPOSAL_READY:
                raise ValueError("proposal decision requires proposal_ready reason")
            if self.proposal_id is None or self.action_id is None:
                raise ValueError("proposal decision requires proposal and action IDs")
            if self.action_id == "launch_app_group" and self.app_group_id is None:
                raise ValueError("app-group proposal decision requires an app-group ID")
        elif self.proposal_id is not None or self.action_id is not None:
            raise ValueError("non-proposal decision cannot contain proposal authority IDs")
        if self.disposition is HandsFreeDisposition.CANCELLED:
            if self.reason is not HandsFreeDecisionReason.CANCELLED:
                raise ValueError("cancelled decision requires cancelled reason")
        elif self.reason is HandsFreeDecisionReason.CANCELLED:
            raise ValueError("cancelled reason requires cancelled disposition")
        return self

    @property
    def proposed(self) -> bool:
        return self.disposition is HandsFreeDisposition.PROPOSE


class ReplayClaim(StrEnum):
    CLAIMED = "claimed"
    EVENT_REPLAY = "event_replay"
    NONCE_REPLAY = "nonce_replay"
    CAPACITY_EXHAUSTED = "capacity_exhausted"


@runtime_checkable
class HandsFreeReplayStore(Protocol):
    """Atomic replay claim port; durable implementations may survive process restart."""

    def claim(
        self,
        *,
        event_id: str,
        nonce: str,
        observed_at: datetime,
        retain_until: datetime,
    ) -> ReplayClaim: ...


class BoundedHandsFreeReplayCache:
    """Bounded in-memory replay store for one process/runtime instance."""

    def __init__(self, *, maximum_entries: int = 1_024) -> None:
        if not 16 <= maximum_entries <= 100_000:
            raise ValueError("replay cache entries must be between 16 and 100000")
        self.maximum_entries = maximum_entries
        self._events: dict[str, datetime] = {}
        self._nonces: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def claim(
        self,
        *,
        event_id: str,
        nonce: str,
        observed_at: datetime,
        retain_until: datetime,
    ) -> ReplayClaim:
        observed = _aware_utc(observed_at, field_name="observed_at")
        retain = _aware_utc(retain_until, field_name="retain_until")
        if retain <= observed:
            raise ValueError("replay retention must extend beyond observation")
        with self._lock:
            self._events = {
                key: expiry for key, expiry in self._events.items() if expiry > observed
            }
            self._nonces = {
                key: expiry for key, expiry in self._nonces.items() if expiry > observed
            }
            if event_id in self._events:
                return ReplayClaim.EVENT_REPLAY
            if nonce in self._nonces:
                return ReplayClaim.NONCE_REPLAY
            if (
                len(self._events) >= self.maximum_entries
                or len(self._nonces) >= self.maximum_entries
            ):
                return ReplayClaim.CAPACITY_EXHAUSTED
            self._events[event_id] = retain
            self._nonces[nonce] = retain
            return ReplayClaim.CLAIMED


class CancellationSignal(Protocol):
    def is_set(self) -> bool: ...


ProposalCallback = Callable[[HandsFreeActionProposal], None]
CancelCallback = Callable[[HandsFreeCancelDirective], None]
VolumeStateReader = Callable[[], MasterVolumeState]
DecisionSink = Callable[[HandsFreeDecisionRecord], None]
Now = Callable[[], datetime]
IdFactory = Callable[[], str]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _random_id_token() -> str:
    return uuid4().hex


class HandsFreeProposalGate:
    """Map one exact enabled intent to a reviewable Level 1 proposal, never authority."""

    def __init__(
        self,
        *,
        policy: ComputerAccessPolicy,
        actor: ActorContext,
        active_source_session_id: str,
        proposal_callback: ProposalCallback,
        decision_sink: DecisionSink,
        cancel_callback: CancelCallback | None = None,
        volume_reader: VolumeStateReader = get_master_volume_state,
        replay_store: HandsFreeReplayStore | None = None,
        confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
        max_intent_age: timedelta = _DEFAULT_MAX_INTENT_AGE,
        max_future_skew: timedelta = _DEFAULT_MAX_FUTURE_SKEW,
        rate_limit: timedelta = _DEFAULT_RATE_LIMIT,
        replay_retention: timedelta = _DEFAULT_REPLAY_RETENTION,
        proposal_ttl: timedelta = _DEFAULT_PROPOSAL_TTL,
        now: Now = _utc_now,
        id_factory: IdFactory = _random_id_token,
    ) -> None:
        if not isinstance(policy, ComputerAccessPolicy):
            raise TypeError("policy must be ComputerAccessPolicy")
        if not isinstance(actor, ActorContext):
            raise TypeError("actor must be ActorContext")
        self.active_source_session_id = _validated_identifier(
            active_source_session_id, label="active source session ID"
        )
        if not math.isfinite(confidence_threshold) or not 0.8 <= confidence_threshold <= 1:
            raise ValueError("hands-free confidence threshold must be from 0.8 to 1.0")
        if not timedelta(milliseconds=100) <= max_intent_age <= timedelta(seconds=10):
            raise ValueError("maximum intent age must be from 100 milliseconds to 10 seconds")
        if not timedelta(0) <= max_future_skew <= timedelta(seconds=1):
            raise ValueError("maximum future skew must be from 0 to 1 second")
        if not timedelta(seconds=1) <= rate_limit <= timedelta(minutes=1):
            raise ValueError("hands-free rate limit must be from 1 to 60 seconds")
        if not max_intent_age + max_future_skew <= replay_retention <= timedelta(hours=1):
            raise ValueError("replay retention must cover freshness and be at most 1 hour")
        if not timedelta(seconds=1) <= proposal_ttl <= _DEFAULT_PROPOSAL_TTL:
            raise ValueError("proposal TTL must be from 1 to 30 seconds")
        self.policy = policy
        self.actor = actor
        self.proposal_callback = proposal_callback
        self.decision_sink = decision_sink
        self.cancel_callback = cancel_callback
        self.volume_reader = volume_reader
        self.replay_store = replay_store or BoundedHandsFreeReplayCache()
        self.confidence_threshold = float(confidence_threshold)
        self.max_intent_age = max_intent_age
        self.max_future_skew = max_future_skew
        self.rate_limit = rate_limit
        self.replay_retention = replay_retention
        self.proposal_ttl = proposal_ttl
        self._now = now
        self._id_factory = id_factory
        self._last_proposal_at: datetime | None = None
        self._cancelled = False
        self._lock = threading.RLock()

    def cancel(self) -> None:
        """Permanently cancel this session-bound gate; a new session needs a new gate."""

        with self._lock:
            self._cancelled = True

    def evaluate(
        self,
        request: HandsFreeRequest,
        *,
        cancel: CancellationSignal | None = None,
    ) -> HandsFreeDecisionRecord:
        if not isinstance(request, HandsFreeRequest):
            raise TypeError("request must be HandsFreeRequest")
        with self._lock:
            now = _aware_utc(self._now(), field_name="hands-free clock")
            replay = self.replay_store.claim(
                event_id=request.intent.event_id,
                nonce=request.nonce,
                observed_at=now,
                retain_until=now + self.replay_retention,
            )
            if replay is ReplayClaim.EVENT_REPLAY:
                return self._deny(request, now, HandsFreeDecisionReason.EVENT_REPLAY)
            if replay is ReplayClaim.NONCE_REPLAY:
                return self._deny(request, now, HandsFreeDecisionReason.NONCE_REPLAY)
            if replay is ReplayClaim.CAPACITY_EXHAUSTED:
                return self._deny(
                    request,
                    now,
                    HandsFreeDecisionReason.REPLAY_CAPACITY_EXHAUSTED,
                )

            if self._cancelled or (cancel is not None and cancel.is_set()):
                return self._deny(
                    request,
                    now,
                    HandsFreeDecisionReason.CANCELLED,
                    disposition=HandsFreeDisposition.CANCELLED,
                )
            if not self.policy.enabled:
                return self._deny(request, now, HandsFreeDecisionReason.POLICY_DISABLED)
            if request.mapped_permission_level is not PermissionLevel.LEVEL_1:
                return self._deny(
                    request,
                    now,
                    HandsFreeDecisionReason.MAPPING_PERMISSION_DENIED,
                )
            if self.policy.maximum_permission_level < PermissionLevel.LEVEL_1:
                return self._deny(
                    request,
                    now,
                    HandsFreeDecisionReason.POLICY_LEVEL_DISALLOWED,
                )
            if request.actor != self.actor:
                return self._deny(request, now, HandsFreeDecisionReason.ACTOR_MISMATCH)
            if request.actor.interface is not InteractionInterface.VOICE:
                return self._deny(
                    request,
                    now,
                    HandsFreeDecisionReason.ACTOR_INTERFACE_DENIED,
                )
            if request.actor.assurance is AuthenticationAssurance.UNAUTHENTICATED:
                return self._deny(
                    request,
                    now,
                    HandsFreeDecisionReason.ACTOR_UNAUTHENTICATED,
                )
            if request.intent.session_id != self.active_source_session_id:
                return self._deny(request, now, HandsFreeDecisionReason.SESSION_MISMATCH)

            intent_value = str(request.intent.intent)
            source_value = str(request.intent.source)
            group_id: str | None = None
            if intent_value == HandsFreeIntentType.LAUNCH_APP_GROUP.value:
                if source_value != AcousticEventType.DOUBLE_CLAP.value:
                    return self._deny(request, now, HandsFreeDecisionReason.SOURCE_DENIED)
                group_id = self.policy.hands_free_app_group
                if group_id is None or group_id not in self.policy.app_groups:
                    return self._deny(
                        request,
                        now,
                        HandsFreeDecisionReason.APP_GROUP_NOT_CONFIGURED,
                    )
            elif intent_value in {item.value for item in HandsFreeGestureIntentType}:
                if source_value != HandsFreeSignalSource.GESTURE.value:
                    return self._deny(request, now, HandsFreeDecisionReason.SOURCE_DENIED)
                mappings = self.policy.hands_free_mappings
                enabled = {
                    HandsFreeGestureIntentType.VOLUME_UP.value: mappings.volume_step,
                    HandsFreeGestureIntentType.VOLUME_DOWN.value: mappings.volume_step,
                    HandsFreeGestureIntentType.MEDIA_PLAY_PAUSE.value: mappings.media_play_pause,
                    HandsFreeGestureIntentType.MEDIA_PREVIOUS_TRACK.value: (
                        mappings.media_track_navigation
                    ),
                    HandsFreeGestureIntentType.MEDIA_NEXT_TRACK.value: (
                        mappings.media_track_navigation
                    ),
                    HandsFreeGestureIntentType.CANCEL.value: mappings.cancel_session,
                }[intent_value]
                if not enabled:
                    return self._deny(
                        request,
                        now,
                        HandsFreeDecisionReason.MAPPING_NOT_CONFIGURED,
                    )
            else:
                return self._deny(request, now, HandsFreeDecisionReason.INTENT_DENIED)

            detected_at = request.intent.detected_at
            if detected_at.tzinfo is None or detected_at.utcoffset() is None:
                return self._deny(
                    request,
                    now,
                    HandsFreeDecisionReason.INVALID_TIMESTAMP,
                    detected_at=None,
                )
            detected_at = detected_at.astimezone(UTC)
            age = now - detected_at
            if age > self.max_intent_age:
                return self._deny(
                    request,
                    now,
                    HandsFreeDecisionReason.INTENT_STALE,
                    detected_at=detected_at,
                )
            if age < -self.max_future_skew:
                return self._deny(
                    request,
                    now,
                    HandsFreeDecisionReason.INTENT_FROM_FUTURE,
                    detected_at=detected_at,
                )
            if (
                not math.isfinite(request.intent.confidence)
                or request.intent.confidence < self.confidence_threshold
            ):
                return self._deny(
                    request,
                    now,
                    HandsFreeDecisionReason.LOW_CONFIDENCE,
                    detected_at=detected_at,
                )
            if intent_value == HandsFreeGestureIntentType.CANCEL.value:
                directive = HandsFreeCancelDirective(
                    directive_id=self._new_id("cancel"),
                    event_id=request.intent.event_id,
                    nonce=request.nonce,
                    host_id=request.actor.host_id,
                    actor_session_id=request.actor.session_id,
                    device_id=request.actor.device_id,
                    source_session_id=request.intent.session_id,
                    created_at=now,
                )
                decision = self._record(
                    request,
                    now,
                    HandsFreeDisposition.CANCELLED,
                    HandsFreeDecisionReason.CANCELLED,
                    app_group_id=None,
                    detected_at=detected_at,
                )
                self._cancelled = True
                if self.cancel_callback is not None:
                    self.cancel_callback(directive)
                return decision
            if self._last_proposal_at is not None:
                elapsed = now - self._last_proposal_at
                if elapsed < self.rate_limit:
                    return self._deny(
                        request,
                        now,
                        HandsFreeDecisionReason.RATE_LIMITED,
                        detected_at=detected_at,
                    )

            proposal_id = self._new_id("proposal")
            common: _ProposalFields = {
                "proposal_id": proposal_id,
                "event_id": request.intent.event_id,
                "nonce": request.nonce,
                "actor": request.actor,
                "source_session_id": request.intent.session_id,
                "policy_version": self.policy.policy_version,
                "created_at": now,
                "expires_at": now + self.proposal_ttl,
            }
            proposal: HandsFreeActionProposal
            if intent_value == HandsFreeIntentType.LAUNCH_APP_GROUP.value:
                assert group_id is not None
                proposal = HandsFreeProposal(
                    **common,
                    app_group_id=group_id,
                    arguments=AppGroupLaunchArguments(group_id=group_id),
                )
            elif intent_value in {
                HandsFreeGestureIntentType.VOLUME_UP.value,
                HandsFreeGestureIntentType.VOLUME_DOWN.value,
            }:
                try:
                    state = self.volume_reader()
                    if not isinstance(state, MasterVolumeState):
                        raise TypeError("volume reader returned an invalid state")
                except Exception:
                    return self._deny(
                        request,
                        now,
                        HandsFreeDecisionReason.VOLUME_READ_FAILED,
                        detected_at=detected_at,
                    )
                observed_percent = min(100, max(0, math.floor(state.scalar * 100 + 0.5)))
                if intent_value == HandsFreeGestureIntentType.VOLUME_UP.value:
                    proposal = HandsFreeVolumeUpProposal(
                        **common,
                        observed_percent=observed_percent,
                        arguments=SetMasterVolumeArguments(percent=min(100, observed_percent + 5)),
                    )
                else:
                    proposal = HandsFreeVolumeDownProposal(
                        **common,
                        observed_percent=observed_percent,
                        arguments=SetMasterVolumeArguments(percent=max(0, observed_percent - 5)),
                    )
            elif intent_value == HandsFreeGestureIntentType.MEDIA_PLAY_PAUSE.value:
                proposal = HandsFreeMediaPlayPauseProposal(
                    **common,
                    arguments=MediaControlArguments(operation=MediaOperation.PLAY_PAUSE),
                )
            elif intent_value == HandsFreeGestureIntentType.MEDIA_PREVIOUS_TRACK.value:
                proposal = HandsFreeMediaPreviousTrackProposal(
                    **common,
                    arguments=MediaControlArguments(operation=MediaOperation.PREVIOUS_TRACK),
                )
            else:
                proposal = HandsFreeMediaNextTrackProposal(
                    **common,
                    arguments=MediaControlArguments(operation=MediaOperation.NEXT_TRACK),
                )
            decision = self._record(
                request,
                now,
                HandsFreeDisposition.PROPOSE,
                HandsFreeDecisionReason.PROPOSAL_READY,
                app_group_id=group_id,
                proposal_id=proposal_id,
                action_id=proposal.action_id,
                detected_at=detected_at,
            )
            self._last_proposal_at = now
            self.proposal_callback(proposal)
            return decision

    def _deny(
        self,
        request: HandsFreeRequest,
        now: datetime,
        reason: HandsFreeDecisionReason,
        *,
        disposition: HandsFreeDisposition = HandsFreeDisposition.DENY,
        detected_at: datetime | Literal[False] | None = False,
    ) -> HandsFreeDecisionRecord:
        timestamp = request.intent.detected_at if detected_at is False else detected_at
        if timestamp is not None and (timestamp.tzinfo is None or timestamp.utcoffset() is None):
            timestamp = None
        return self._record(
            request,
            now,
            disposition,
            reason,
            app_group_id=self.policy.hands_free_app_group,
            detected_at=timestamp,
        )

    def _record(
        self,
        request: HandsFreeRequest,
        now: datetime,
        disposition: HandsFreeDisposition,
        reason: HandsFreeDecisionReason,
        *,
        app_group_id: str | None,
        proposal_id: str | None = None,
        action_id: Literal["launch_app_group", "set_master_volume", "control_media"] | None = None,
        detected_at: datetime | None = None,
    ) -> HandsFreeDecisionRecord:
        decision = HandsFreeDecisionRecord(
            decision_id=self._new_id("decision"),
            disposition=disposition,
            reason=reason,
            event_id=request.intent.event_id,
            nonce=request.nonce,
            actor=request.actor,
            active_source_session_id=self.active_source_session_id,
            observed_source_session_id=request.intent.session_id,
            intent=str(request.intent.intent),
            source=str(request.intent.source),
            confidence=request.intent.confidence,
            requested_permission_level=request.mapped_permission_level,
            policy_version=self.policy.policy_version,
            action_id=action_id,
            app_group_id=app_group_id,
            proposal_id=proposal_id,
            detected_at=detected_at,
            decided_at=now,
        )
        self.decision_sink(decision)
        return decision

    def _new_id(self, kind: str) -> str:
        token = self._id_factory()
        if (
            not isinstance(token, str)
            or not 8 <= len(token) <= 64
            or any(
                not (character.isascii() and (character.isalnum() or character in "_-"))
                for character in token
            )
        ):
            raise ValueError("hands-free ID factory returned an invalid token")
        return f"hands-free-{kind}-{token}"


class HandsFreeCoordinatorProposalConsumer:
    """Send a validated mapping to ``ActionCoordinator.propose`` and nowhere else."""

    _PROPOSAL_TYPES = (
        HandsFreeProposal,
        HandsFreeVolumeUpProposal,
        HandsFreeVolumeDownProposal,
        HandsFreeMediaPlayPauseProposal,
        HandsFreeMediaPreviousTrackProposal,
        HandsFreeMediaNextTrackProposal,
    )

    def __init__(
        self,
        *,
        coordinator: ActionCoordinator,
        registry: ComputerActionRegistry,
        now: Now = _utc_now,
    ) -> None:
        self._coordinator = coordinator
        self._registry = registry
        self._now = now

    async def consume(self, proposal: HandsFreeActionProposal) -> ActionCoordinatorResult:
        """Create one pending proposal; this type exposes no review or execute method."""
        if not isinstance(proposal, self._PROPOSAL_TYPES):
            raise TypeError("hands-free consumer requires an action proposal")
        validated = type(proposal).model_validate(proposal.model_dump())
        now = _aware_utc(self._now(), field_name="hands-free consumer clock")
        if validated.created_at > now + _DEFAULT_MAX_FUTURE_SKEW:
            raise ValueError("hands-free proposal was created in the future")
        if validated.expires_at <= now:
            raise ValueError("hands-free proposal expired before coordinator submission")
        if validated.policy_version != self._coordinator.policy_version:
            raise ValueError("hands-free proposal policy version is no longer active")
        action = self._registry.action(validated.action_id)
        if action is None:
            raise ValueError("hands-free proposal action is not in the fixed registry")
        if (
            action.definition.action_id != validated.action_id
            or action.definition.tool.permission_level is not PermissionLevel.LEVEL_1
        ):
            raise ValueError("hands-free proposal cannot target non-Level-1 authority")
        raw_arguments: BaseModel = action.input_model.model_validate(
            validated.arguments.model_dump()
        )
        idempotency_key = "hands-free-" + sha256_fingerprint(
            {
                "event_id": validated.event_id,
                "nonce": validated.nonce,
                "source_session_id": validated.source_session_id,
                "action_id": validated.action_id,
                "arguments": validated.arguments,
                "policy_version": validated.policy_version,
            }
        ).removeprefix("sha256:")
        return await self._coordinator.propose(
            action,
            raw_arguments,
            actor=validated.actor,
            source=ApprovalSource.HANDS_FREE,
            idempotency_key=idempotency_key,
        )


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _validated_identifier(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 200
        or any(ord(character) < 32 for character in normalized)
    ):
        raise ValueError(f"{label} is invalid")
    return normalized
