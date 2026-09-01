"""Additional narrow Phase 3 handlers for volume, clipboard, and browser targets."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path
from typing import Annotated, Protocol, TypeVar, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator

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
    ActionDefinition,
    ActionEffect,
    CanonicalAction,
    PostconditionEvidence,
    PostconditionStatus,
    RollbackReceipt,
    RollbackStatus,
    sha256_fingerprint,
)

from .actions import (
    ActionPreparationError,
    ComputerActionError,
    LaunchObservation,
    PreparedAction,
    _action_arguments,
    _ensure_policy_enabled,
    _json_schema,
    _parse_effect,
    _require_precondition,
    _schema_with_ids,
    _unavailable_rollback,
)
from .audio import (
    AudioPostconditionError,
    CoreAudioError,
    MasterVolumeOperation,
    MasterVolumeReceipt,
    MasterVolumeState,
    get_master_volume_state,
    set_master_volume_scalar,
)
from .clipboard import (
    ClipboardChangedError,
    ClipboardError,
    ClipboardMutationReceipt,
    ClipboardRollbackReceipt,
    ClipboardSnapshot,
    get_clipboard_snapshot,
    rollback_clipboard_text,
    set_clipboard_text,
)
from .config import ComputerAccessPolicy
from .windows import (
    ExecutableEnrollment,
    FixedExecutableLauncher,
    IdentityMismatchError,
)

_VOLUME_TOLERANCE = 0.001
_EXACT_STATE_TOLERANCE = 0.000001
_MAX_CLIPBOARD_HUMAN_EFFECT = 2_000


class _ArgumentsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SetMasterVolumeArguments(_ArgumentsModel):
    percent: Annotated[int, Field(strict=True, ge=0, le=100)]


class SetClipboardTextArguments(_ArgumentsModel):
    text: Annotated[str, Field(max_length=32_768)]

    @field_validator("text")
    @classmethod
    def validate_exact_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("clipboard text cannot contain NUL")
        try:
            value.encode("utf-16-le", errors="strict")
        except UnicodeError as exc:
            raise ValueError("clipboard text must be valid Unicode") from exc
        return value


class OpenBrowserTargetArguments(_ArgumentsModel):
    target_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=64,
            pattern=r"^[a-z][a-z0-9_-]{0,63}$",
        ),
    ]


class _VolumePrecondition(_ArgumentsModel):
    before_scalar: Annotated[float, Field(ge=0, le=1)]
    before_muted: bool
    target_scalar: Annotated[float, Field(ge=0, le=1)]
    event_context: UUID

    @field_validator("event_context")
    @classmethod
    def reject_null_context(cls, value: UUID) -> UUID:
        if value.int == 0:
            raise ValueError("volume event context must be non-null")
        return value


class _VolumeEffect(_ArgumentsModel):
    requested_percent: Annotated[int, Field(strict=True, ge=0, le=100)]
    observed_scalar: Annotated[float, Field(ge=0, le=1)]
    observed_muted: bool
    event_context: UUID
    verified: bool


class _VolumeRollbackContext(_ArgumentsModel):
    before_scalar: Annotated[float, Field(ge=0, le=1)]
    before_muted: bool
    action_scalar: Annotated[float, Field(ge=0, le=1)]
    action_muted: bool
    event_context: UUID


class _ClipboardPrecondition(_ArgumentsModel):
    recovery_token: Annotated[str, Field(min_length=16, max_length=100)]
    before_sequence: Annotated[int, Field(strict=True, ge=0)]
    before_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    before_utf16_bytes: Annotated[int, Field(strict=True, ge=0)]
    before_formats: Annotated[tuple[int, ...], Field(max_length=32)]
    requested_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    requested_utf16_bytes: Annotated[int, Field(strict=True, ge=0)]


class _ClipboardEffect(_ArgumentsModel):
    text_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    utf16_bytes: Annotated[int, Field(strict=True, ge=0)]
    changed: bool
    verified: bool


class _ClipboardRollbackContext(_ArgumentsModel):
    recovery_token: Annotated[str, Field(min_length=16, max_length=100)]
    expected_current_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    requested_utf16_bytes: Annotated[int, Field(strict=True, ge=0)]


class _BrowserEffect(_ArgumentsModel):
    target_id: Annotated[str, Field(min_length=1, max_length=64)]
    application_id: Annotated[str, Field(min_length=1, max_length=64)]
    url_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    pid: Annotated[int, Field(strict=True, gt=0)]
    image_verified: bool


class VolumeReader(Protocol):
    def __call__(self) -> MasterVolumeState: ...


class VolumeSetter(Protocol):
    def __call__(
        self,
        value: float,
        *,
        event_context: UUID,
    ) -> MasterVolumeReceipt: ...


EventContextFactory = Callable[[], UUID]


class SetMasterVolumeHandler:
    """Broker handler for one absolute master-volume percentage."""

    def __init__(
        self,
        policy: ComputerAccessPolicy,
        *,
        read_state: VolumeReader = get_master_volume_state,
        set_scalar: VolumeSetter = set_master_volume_scalar,
        event_context_factory: EventContextFactory = uuid4,
    ) -> None:
        _ensure_policy_enabled(policy, PermissionLevel.LEVEL_1)
        self._read_state = read_state
        self._set_scalar = set_scalar
        self._event_context_factory = event_context_factory
        tool = ToolDefinition(
            name="set_master_volume",
            version="1",
            description="Set Windows master volume to one absolute integer percentage.",
            input_schema=_json_schema(SetMasterVolumeArguments),
            permission_level=PermissionLevel.LEVEL_1,
            approval_rule=ApprovalRule.EXPLICIT_ENABLEMENT,
            risk=ToolRisk.REVERSIBLE,
            side_effect=ToolSideEffect.REVERSIBLE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.volume.set",),
            timeout_seconds=3,
            max_result_bytes=2_048,
            max_result_items=5,
            idempotency=ToolIdempotency.IDEMPOTENCY_KEY,
            retry_policy=ToolRetryPolicy.RECONCILE_FIRST,
            concurrency=ToolConcurrency.SERIAL_GLOBAL,
            postcondition=(
                "The default console render endpoint reads back the exact approved absolute "
                "scalar within 0.001 without changing mute state."
            ),
            recovery=(
                "Restore the captured prior scalar only while scalar and mute still equal this "
                "action's verified result; otherwise refuse rollback."
            ),
        )
        self._definition = ActionDefinition(
            tool=tool,
            supports_rollback=True,
            effect_may_outlive_cancellation=True,
            rollback_timeout_seconds=3,
        )

    @property
    def definition(self) -> ActionDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return SetMasterVolumeArguments

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        parsed = SetMasterVolumeArguments.model_validate(arguments)
        try:
            before = _validated_volume_state(self._read_state())
        except CoreAudioError as exc:
            raise ActionPreparationError("master volume state could not be captured") from exc
        event_context = self._event_context_factory()
        if not isinstance(event_context, UUID) or event_context.int == 0:
            raise ActionPreparationError("volume event context factory returned an invalid UUID")
        target = parsed.percent / 100
        return PreparedAction(
            normalized_arguments={"percent": parsed.percent},
            human_effect=f"Set Windows master volume exactly to {parsed.percent}%.",
            recovery_limits=(
                "The prior volume is restored only if no application or user changes volume or "
                "mute after this action."
            ),
            precondition=_volume_precondition(before, target, event_context),
        )

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        parsed = cast(
            SetMasterVolumeArguments,
            _action_arguments(action, self._definition, SetMasterVolumeArguments),
        )
        precondition = _parse_volume_precondition(action)
        current = _validated_volume_state(await asyncio.to_thread(self._read_state))
        _require_precondition(
            action,
            _volume_precondition(current, parsed.percent / 100, precondition.event_context),
        )
        try:
            receipt = await asyncio.to_thread(
                self._set_scalar,
                parsed.percent / 100,
                event_context=precondition.event_context,
            )
        except AudioPostconditionError as error:
            if (
                error.operation is not MasterVolumeOperation.SET_SCALAR
                or error.event_context != precondition.event_context
                or error.requested_scalar is None
            ):
                raise
            observed_before = error.before
            observed_after = error.observed
            receipt_verified = False
        else:
            if not isinstance(receipt, MasterVolumeReceipt):
                raise CoreAudioError("master-volume adapter returned an invalid receipt")
            observed_before = receipt.before
            observed_after = receipt.after
            receipt_verified = (
                receipt.operation is MasterVolumeOperation.SET_SCALAR
                and receipt.event_context == precondition.event_context
                and receipt.requested_scalar is not None
                and _scalar_matches(
                    receipt.requested_scalar,
                    parsed.percent / 100,
                    _EXACT_STATE_TOLERANCE,
                )
                and _volume_state_matches(
                    receipt.before,
                    precondition.before_scalar,
                    precondition.before_muted,
                    tolerance=_EXACT_STATE_TOLERANCE,
                )
                and _volume_state_matches(
                    receipt.after,
                    parsed.percent / 100,
                    precondition.before_muted,
                    tolerance=_VOLUME_TOLERANCE,
                )
            )
        context = _VolumeRollbackContext(
            before_scalar=observed_before.scalar,
            before_muted=observed_before.muted,
            action_scalar=observed_after.scalar,
            action_muted=observed_after.muted,
            event_context=precondition.event_context,
        )
        result: dict[str, JsonValue] = {
            "requested_percent": parsed.percent,
            "observed_scalar": observed_after.scalar,
            "observed_muted": observed_after.muted,
            "event_context": str(precondition.event_context),
            "verified": receipt_verified,
        }
        return ActionEffect(
            result=result,
            rollback_context=cast(JsonValue, context.model_dump(mode="json")),
        )

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        parsed = cast(
            SetMasterVolumeArguments,
            _action_arguments(action, self._definition, SetMasterVolumeArguments),
        )
        precondition = _parse_volume_precondition(action)
        observed = _parse_effect(effect, _VolumeEffect)
        try:
            current = _validated_volume_state(await asyncio.to_thread(self._read_state))
        except CoreAudioError:
            current = None
        target = parsed.percent / 100
        passed = (
            observed is not None
            and observed.requested_percent == parsed.percent
            and observed.event_context == precondition.event_context
            and observed.verified
            and current is not None
            and _scalar_matches(current.scalar, target, _VOLUME_TOLERANCE)
            and current.muted is precondition.before_muted
        )
        return PostconditionEvidence(
            status=PostconditionStatus.PASSED if passed else PostconditionStatus.MISMATCH,
            summary=(
                "Master volume matched the approved absolute percentage and mute state."
                if passed
                else "Master volume or mute state did not match the approved postcondition."
            ),
            detail={"requested_percent": parsed.percent},
        )

    async def rollback(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
        *,
        reason: str,
    ) -> RollbackReceipt:
        del reason
        cast(
            SetMasterVolumeArguments,
            _action_arguments(action, self._definition, SetMasterVolumeArguments),
        )
        context = _parse_rollback_context(effect, _VolumeRollbackContext)
        if context is None:
            return _unavailable_rollback("Volume rollback context is absent or malformed.")
        precondition = _parse_volume_precondition(action)
        observed = _parse_effect(effect, _VolumeEffect)
        if (
            observed is None
            or context.event_context != precondition.event_context
            or observed.event_context != context.event_context
            or not _scalar_matches(
                observed.observed_scalar,
                context.action_scalar,
                _EXACT_STATE_TOLERANCE,
            )
            or observed.observed_muted is not context.action_muted
            or not _scalar_matches(
                context.before_scalar,
                precondition.before_scalar,
                _EXACT_STATE_TOLERANCE,
            )
            or context.before_muted is not precondition.before_muted
        ):
            return _unavailable_rollback(
                "Volume rollback context does not match the approved action."
            )
        try:
            current = _validated_volume_state(await asyncio.to_thread(self._read_state))
        except CoreAudioError:
            return RollbackReceipt(
                status=RollbackStatus.FAILED,
                summary="Current master-volume state could not be read; rollback was refused.",
            )
        if not _volume_state_matches(
            current,
            context.action_scalar,
            context.action_muted,
            tolerance=_VOLUME_TOLERANCE,
        ):
            return RollbackReceipt(
                status=RollbackStatus.FAILED,
                summary="Master volume changed after this action; rollback was refused.",
            )
        try:
            receipt = await asyncio.to_thread(
                self._set_scalar,
                context.before_scalar,
                event_context=context.event_context,
            )
        except CoreAudioError:
            return RollbackReceipt(
                status=RollbackStatus.FAILED,
                summary="Prior master-volume state could not be restored.",
            )
        restored = (
            isinstance(receipt, MasterVolumeReceipt)
            and receipt.event_context == context.event_context
            and _volume_state_matches(
                receipt.after,
                context.before_scalar,
                context.before_muted,
                tolerance=_VOLUME_TOLERANCE,
            )
        )
        return RollbackReceipt(
            status=RollbackStatus.SUCCEEDED if restored else RollbackStatus.FAILED,
            summary=(
                "Prior master-volume scalar was restored without changing mute state."
                if restored
                else "Master-volume rollback postcondition did not match."
            ),
        )


@dataclass(frozen=True, slots=True)
class _ClipboardRecoveryReservation:
    before_sequence: int
    before_sha256: str | None
    before_utf16_bytes: int
    before_formats: tuple[int, ...]
    expires_at: float

    def matches(self, snapshot: ClipboardSnapshot) -> bool:
        return (
            self.before_sequence == snapshot.sequence
            and self.before_sha256 == snapshot.text_sha256
            and self.before_utf16_bytes == snapshot.utf16_bytes
            and self.before_formats == snapshot.formats
        )


@dataclass(frozen=True, slots=True)
class _ClipboardRecoveryEntry:
    previous_text: str | None
    before_sequence: int
    before_sha256: str | None
    before_utf16_bytes: int
    before_formats: tuple[int, ...]
    expires_at: float

    @property
    def retained_bytes(self) -> int:
        return self.before_utf16_bytes


TokenFactory = Callable[[], str]
MonotonicClock = Callable[[], float]


class _VolatileClipboardRecovery:
    """Separate metadata reservations from broker-time volatile prior plaintext."""

    def __init__(
        self,
        *,
        maximum_entries: int,
        maximum_bytes: int,
        ttl_seconds: float,
        token_factory: TokenFactory,
        monotonic: MonotonicClock,
    ) -> None:
        self._maximum_entries = maximum_entries
        self._maximum_bytes = maximum_bytes
        self._ttl_seconds = ttl_seconds
        self._token_factory = token_factory
        self._monotonic = monotonic
        self._namespace = uuid4().hex
        self._maximum_reservations = min(100_000, maximum_entries * 16)
        self._reservations: dict[str, _ClipboardRecoveryReservation] = {}
        self._entries: dict[str, _ClipboardRecoveryEntry] = {}
        self._lock = threading.Lock()

    def reserve_token(
        self,
        *,
        before_sequence: int,
        before_sha256: str | None,
        before_utf16_bytes: int,
        before_formats: tuple[int, ...],
    ) -> str:
        """Bind only opaque token and snapshot metadata during preparation."""

        now = self._monotonic()
        if not math.isfinite(now):
            raise ActionPreparationError("clipboard recovery clock is invalid")
        with self._lock:
            self._prune(now)
            if len(self._reservations) >= self._maximum_reservations:
                raise ActionPreparationError("clipboard proposal reservation capacity is exhausted")
            token_material = self._token_factory()
            if (
                not isinstance(token_material, str)
                or not 16 <= len(token_material) <= 80
                or any(
                    not (character.isascii() and (character.isalnum() or character in "_-"))
                    for character in token_material
                )
            ):
                raise ActionPreparationError("clipboard recovery token is invalid or duplicated")
            token_digest = hashlib.sha256(token_material.encode("ascii")).hexdigest()[:32]
            token = f"cb-{self._namespace}-{token_digest}"
            if token in self._reservations or token in self._entries:
                raise ActionPreparationError("clipboard recovery token is invalid or duplicated")
            self._reservations[token] = _ClipboardRecoveryReservation(
                before_sequence=before_sequence,
                before_sha256=before_sha256,
                before_utf16_bytes=before_utf16_bytes,
                before_formats=before_formats,
                expires_at=now + self._ttl_seconds,
            )
            return token

    def materialize(
        self,
        token: str,
        snapshot: ClipboardSnapshot,
    ) -> _ClipboardRecoveryEntry | None:
        """Store prior plaintext only at broker execution after exact revalidation.

        A token issued by this cache must retain a live, matching reservation. A token from a
        prior cache instance may be reconstructed after restart because the broker has already
        fingerprint-validated the action and the handler has matched its exact live precondition.
        """

        now = self._monotonic()
        if not math.isfinite(now):
            return None
        with self._lock:
            reservation = self._reservations.get(token)
            if reservation is not None:
                self._reservations.pop(token)
                if reservation.expires_at <= now or not reservation.matches(snapshot):
                    return None
            elif self._owns_token(token):
                return None
            self._prune(now)
            retained = sum(entry.retained_bytes for entry in self._entries.values())
            if (
                len(self._entries) >= self._maximum_entries
                or retained + snapshot.utf16_bytes > self._maximum_bytes
            ):
                raise ComputerActionError("volatile clipboard recovery capacity is exhausted")
            entry = _ClipboardRecoveryEntry(
                previous_text=snapshot.text,
                before_sequence=snapshot.sequence,
                before_sha256=snapshot.text_sha256,
                before_utf16_bytes=snapshot.utf16_bytes,
                before_formats=snapshot.formats,
                expires_at=now + self._ttl_seconds,
            )
            self._entries[token] = entry
            return entry

    def _owns_token(self, token: str) -> bool:
        return token.startswith(f"cb-{self._namespace}-")

    def get(self, token: str) -> _ClipboardRecoveryEntry | None:
        now = self._monotonic()
        if not math.isfinite(now):
            return None
        with self._lock:
            self._prune(now)
            return self._entries.get(token)

    def discard(self, token: str) -> None:
        with self._lock:
            self._reservations.pop(token, None)
            self._entries.pop(token, None)

    @property
    def materialized_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def _prune(self, now: float) -> None:
        self._reservations = {
            token: reservation
            for token, reservation in self._reservations.items()
            if reservation.expires_at > now
        }
        self._entries = {
            token: entry for token, entry in self._entries.items() if entry.expires_at > now
        }


ClipboardReader = Callable[..., ClipboardSnapshot]
ClipboardSetter = Callable[..., ClipboardMutationReceipt]
ClipboardRollback = Callable[..., ClipboardRollbackReceipt]


class SetClipboardTextHandler:
    """Broker handler binding exact text while keeping receipts and audit evidence text-free."""

    def __init__(
        self,
        policy: ComputerAccessPolicy,
        *,
        read_snapshot: ClipboardReader = get_clipboard_snapshot,
        set_text: ClipboardSetter = set_clipboard_text,
        rollback_text: ClipboardRollback = rollback_clipboard_text,
        recovery_ttl_seconds: float = 15 * 60,
        recovery_maximum_entries: int = 64,
        recovery_maximum_bytes: int = 1 * 1024 * 1024,
        token_factory: TokenFactory = lambda: f"clipboard-{uuid4().hex}",
        monotonic: MonotonicClock = time.monotonic,
    ) -> None:
        _ensure_policy_enabled(policy, PermissionLevel.LEVEL_2)
        if not 60 <= recovery_ttl_seconds <= 60 * 60:
            raise ValueError("clipboard recovery TTL must be from 60 to 3600 seconds")
        if not 1 <= recovery_maximum_entries <= 1_024:
            raise ValueError("clipboard recovery entries must be from 1 to 1024")
        if not policy.max_clipboard_bytes <= recovery_maximum_bytes <= 16 * 1024 * 1024:
            raise ValueError("clipboard recovery byte capacity is invalid")
        self._max_bytes = policy.max_clipboard_bytes
        self._read_snapshot = read_snapshot
        self._set_text = set_text
        self._rollback_text = rollback_text
        self._recovery = _VolatileClipboardRecovery(
            maximum_entries=recovery_maximum_entries,
            maximum_bytes=recovery_maximum_bytes,
            ttl_seconds=recovery_ttl_seconds,
            token_factory=token_factory,
            monotonic=monotonic,
        )
        tool = ToolDefinition(
            name="set_clipboard_text",
            version="1",
            description="Replace Windows clipboard content with one exact bounded Unicode text.",
            input_schema=_json_schema(SetClipboardTextArguments),
            permission_level=PermissionLevel.LEVEL_2,
            approval_rule=ApprovalRule.POLICY_OR_EXPLICIT,
            risk=ToolRisk.REVERSIBLE,
            side_effect=ToolSideEffect.REVERSIBLE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.clipboard.write",),
            timeout_seconds=3,
            max_result_bytes=2_048,
            max_result_items=4,
            idempotency=ToolIdempotency.IDEMPOTENCY_KEY,
            retry_policy=ToolRetryPolicy.RECONCILE_FIRST,
            concurrency=ToolConcurrency.SERIAL_GLOBAL,
            postcondition=(
                "Clipboard Unicode text hashes and byte length match the exact approved text; "
                "receipts contain no clipboard text."
            ),
            recovery=(
                "The bounded prior text is held only in volatile expiring memory and restored "
                "only while the clipboard still matches this action's hash."
            ),
        )
        self._definition = ActionDefinition(
            tool=tool,
            supports_rollback=True,
            effect_may_outlive_cancellation=True,
            rollback_timeout_seconds=3,
        )

    @property
    def definition(self) -> ActionDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return SetClipboardTextArguments

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        parsed = SetClipboardTextArguments.model_validate(arguments)
        digest, utf16_bytes = _clipboard_text_authority(parsed.text, self._max_bytes)
        human_effect = (
            f"Set clipboard text exactly to {json.dumps(parsed.text, ensure_ascii=False)}."
        )
        if len(human_effect) > _MAX_CLIPBOARD_HUMAN_EFFECT:
            raise ActionPreparationError(
                "exact clipboard text is too long for trusted approval display"
            )
        try:
            before = _validated_clipboard_snapshot(
                self._read_snapshot(max_bytes=self._max_bytes),
                maximum_bytes=self._max_bytes,
            )
        except ClipboardError as exc:
            raise ActionPreparationError("clipboard state could not be captured safely") from exc
        token = self._recovery.reserve_token(
            before_sequence=before.sequence,
            before_sha256=before.text_sha256,
            before_utf16_bytes=before.utf16_bytes,
            before_formats=before.formats,
        )
        return PreparedAction(
            normalized_arguments={"text": parsed.text},
            human_effect=human_effect,
            recovery_limits=(
                "Prior clipboard text is volatile and expires; rollback is refused if another "
                "application changes the clipboard."
            ),
            precondition=_clipboard_precondition(before, token, digest, utf16_bytes),
        )

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        parsed = cast(
            SetClipboardTextArguments,
            _action_arguments(action, self._definition, SetClipboardTextArguments),
        )
        digest, utf16_bytes = _clipboard_text_authority(parsed.text, self._max_bytes)
        precondition = _parse_clipboard_precondition(action)
        current = _validated_clipboard_snapshot(
            await asyncio.to_thread(
                self._read_snapshot,
                max_bytes=self._max_bytes,
            ),
            maximum_bytes=self._max_bytes,
        )
        _require_precondition(
            action,
            _clipboard_precondition(current, precondition.recovery_token, digest, utf16_bytes),
        )
        entry = self._recovery.materialize(precondition.recovery_token, current)
        if entry is None:
            raise ComputerActionError("clipboard recovery reservation is unavailable or changed")
        if not _entry_matches_precondition(entry, precondition):
            self._recovery.discard(precondition.recovery_token)
            raise ComputerActionError("volatile clipboard recovery state does not match approval")
        try:
            receipt = await asyncio.to_thread(
                self._set_text,
                parsed.text,
                max_bytes=self._max_bytes,
            )
        except Exception:
            self._recovery.discard(precondition.recovery_token)
            raise
        if not isinstance(receipt, ClipboardMutationReceipt):
            raise ClipboardError("clipboard adapter returned an invalid receipt")
        receipt_verified = (
            receipt.verified
            and compare_digest(receipt.after_sha256, digest)
            and receipt.utf16_bytes == utf16_bytes
            and receipt.before_sequence == current.sequence
        )
        context = _ClipboardRollbackContext(
            recovery_token=precondition.recovery_token,
            expected_current_sha256=digest,
            requested_utf16_bytes=utf16_bytes,
        )
        result: dict[str, JsonValue] = {
            "text_sha256": digest,
            "utf16_bytes": utf16_bytes,
            "changed": receipt.changed,
            "verified": receipt_verified,
        }
        return ActionEffect(
            result=result,
            rollback_context=cast(JsonValue, context.model_dump(mode="json")),
        )

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        parsed = cast(
            SetClipboardTextArguments,
            _action_arguments(action, self._definition, SetClipboardTextArguments),
        )
        digest, utf16_bytes = _clipboard_text_authority(parsed.text, self._max_bytes)
        observed = _parse_effect(effect, _ClipboardEffect)
        try:
            current = _validated_clipboard_snapshot(
                await asyncio.to_thread(
                    self._read_snapshot,
                    max_bytes=self._max_bytes,
                ),
                maximum_bytes=self._max_bytes,
            )
        except ClipboardError:
            current = None
        passed = (
            observed is not None
            and compare_digest(observed.text_sha256, digest)
            and observed.utf16_bytes == utf16_bytes
            and observed.verified
            and current is not None
            and current.text_sha256 is not None
            and compare_digest(current.text_sha256, digest)
            and current.utf16_bytes == utf16_bytes
        )
        return PostconditionEvidence(
            status=PostconditionStatus.PASSED if passed else PostconditionStatus.MISMATCH,
            summary=(
                "Clipboard hash and byte length match the exact approved text."
                if passed
                else "Clipboard hash or byte length does not match the approved text."
            ),
            detail={"text_sha256": digest, "utf16_bytes": utf16_bytes},
        )

    async def rollback(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
        *,
        reason: str,
    ) -> RollbackReceipt:
        del reason
        cast(
            SetClipboardTextArguments,
            _action_arguments(action, self._definition, SetClipboardTextArguments),
        )
        context = _parse_rollback_context(effect, _ClipboardRollbackContext)
        if context is None:
            return _unavailable_rollback("Clipboard rollback context is absent or malformed.")
        precondition = _parse_clipboard_precondition(action)
        if (
            context.recovery_token != precondition.recovery_token
            or not compare_digest(
                context.expected_current_sha256,
                precondition.requested_sha256,
            )
            or context.requested_utf16_bytes != precondition.requested_utf16_bytes
        ):
            return _unavailable_rollback(
                "Clipboard rollback context does not match the approved action."
            )
        entry = self._recovery.get(context.recovery_token)
        if entry is None:
            return _unavailable_rollback("Volatile prior clipboard text is unavailable or expired.")
        try:
            receipt = await asyncio.to_thread(
                self._rollback_text,
                entry.previous_text,
                expected_current_sha256=context.expected_current_sha256,
                max_bytes=self._max_bytes,
            )
        except ClipboardChangedError:
            return RollbackReceipt(
                status=RollbackStatus.FAILED,
                summary="Clipboard changed after this action; rollback was refused.",
                detail={"expected_current_sha256": context.expected_current_sha256},
            )
        except ClipboardError:
            return RollbackReceipt(
                status=RollbackStatus.FAILED,
                summary="Prior clipboard text could not be restored safely.",
            )
        finally:
            self._recovery.discard(context.recovery_token)
        restored = receipt.verified and receipt.restored_sha256 == entry.before_sha256
        return RollbackReceipt(
            status=RollbackStatus.SUCCEEDED if restored else RollbackStatus.FAILED,
            summary=(
                "Prior clipboard text was restored from volatile recovery state."
                if restored
                else "Clipboard rollback postcondition did not match."
            ),
            detail={
                "restored_sha256": receipt.restored_sha256,
                "restored_utf16_bytes": entry.before_utf16_bytes,
            },
        )


EnrollmentCapture = Callable[[Path], ExecutableEnrollment]
BrowserLauncher = Callable[[ExecutableEnrollment, tuple[str, ...]], LaunchObservation]


def _default_browser_launcher(
    enrollment: ExecutableEnrollment,
    arguments: tuple[str, ...],
) -> LaunchObservation:
    return FixedExecutableLauncher(enrollment, arguments).launch()


class OpenBrowserTargetHandler:
    """Launch one enrolled browser with fixed host argv plus one allowlisted HTTPS URL."""

    def __init__(
        self,
        policy: ComputerAccessPolicy,
        *,
        capture_enrollment: EnrollmentCapture = ExecutableEnrollment.capture,
        launch_browser: BrowserLauncher = _default_browser_launcher,
    ) -> None:
        _ensure_policy_enabled(policy, PermissionLevel.LEVEL_2)
        if not policy.browser_targets or policy.browser_application is None:
            raise ValueError(
                "browser target action requires targets and one fixed browser application"
            )
        application = policy.applications[policy.browser_application]
        enrollment = capture_enrollment(application.executable)
        if not compare_digest(application.sha256, enrollment.sha256):
            raise IdentityMismatchError(
                "configured browser SHA-256 does not match enrolled executable"
            )
        self._application_id = policy.browser_application
        self._application = application
        self._targets = {
            target_id: str(target.url) for target_id, target in policy.browser_targets.items()
        }
        self._enrollment = enrollment
        self._launch = launch_browser
        tool = ToolDefinition(
            name="open_browser_target",
            version="1",
            description="Open one host-allowlisted HTTPS target in one enrolled browser.",
            input_schema=_schema_with_ids(
                OpenBrowserTargetArguments,
                "target_id",
                tuple(self._targets),
            ),
            permission_level=PermissionLevel.LEVEL_2,
            approval_rule=ApprovalRule.POLICY_OR_EXPLICIT,
            risk=ToolRisk.REVERSIBLE,
            side_effect=ToolSideEffect.EXTERNAL,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.browser.open_target",),
            timeout_seconds=min(30, application.startup_timeout_seconds + 1),
            max_result_bytes=2_048,
            max_result_items=5,
            idempotency=ToolIdempotency.IDEMPOTENCY_KEY,
            retry_policy=ToolRetryPolicy.RECONCILE_FIRST,
            concurrency=ToolConcurrency.SERIAL_PER_SESSION,
            postcondition=(
                "The spawned process image matches the enrolled browser executable; the "
                "allowlisted URL is the final fixed argument."
            ),
            recovery=(
                "The browser is not terminated automatically because it may contain existing "
                "user work; close the unwanted tab or window manually."
            ),
        )
        self._definition = ActionDefinition(
            tool=tool,
            supports_rollback=False,
            effect_may_outlive_cancellation=True,
        )

    @property
    def definition(self) -> ActionDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return OpenBrowserTargetArguments

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        parsed = OpenBrowserTargetArguments.model_validate(arguments)
        url = self._targets.get(parsed.target_id)
        if url is None:
            raise ActionPreparationError("browser target ID is not configured")
        return PreparedAction(
            normalized_arguments={"target_id": parsed.target_id},
            human_effect=f"Open configured browser target '{parsed.target_id}': {url}",
            recovery_limits=(
                "JARVIS will not automatically terminate the browser because that could lose "
                "unrelated user work."
            ),
            precondition=self._precondition(parsed.target_id, url),
        )

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        parsed = cast(
            OpenBrowserTargetArguments,
            _action_arguments(action, self._definition, OpenBrowserTargetArguments),
        )
        url = self._targets.get(parsed.target_id)
        if url is None:
            raise ComputerActionError("browser target ID is no longer configured")
        _require_precondition(action, self._precondition(parsed.target_id, url))
        arguments = (*self._application.arguments, url)
        observation = await asyncio.to_thread(
            self._launch,
            self._enrollment,
            arguments,
        )
        result: dict[str, JsonValue] = {
            "target_id": parsed.target_id,
            "application_id": self._application_id,
            "url_sha256": _url_digest(url),
            "pid": observation.pid,
            "image_verified": observation.image_verified,
        }
        return ActionEffect(result=result)

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        parsed = cast(
            OpenBrowserTargetArguments,
            _action_arguments(action, self._definition, OpenBrowserTargetArguments),
        )
        url = self._targets.get(parsed.target_id)
        observed = _parse_effect(effect, _BrowserEffect)
        passed = (
            url is not None
            and observed is not None
            and observed.target_id == parsed.target_id
            and observed.application_id == self._application_id
            and compare_digest(observed.url_sha256, _url_digest(url))
            and observed.image_verified
        )
        return PostconditionEvidence(
            status=PostconditionStatus.PASSED if passed else PostconditionStatus.MISMATCH,
            summary=(
                "Spawned browser image matched enrollment for the allowlisted target."
                if passed
                else "Browser image or allowlisted target evidence did not match."
            ),
            detail={"target_id": parsed.target_id},
        )

    async def rollback(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
        *,
        reason: str,
    ) -> RollbackReceipt:
        del action, effect, reason
        return _unavailable_rollback(
            "Automatic browser termination is unavailable because it could discard user work."
        )

    def _precondition(self, target_id: str, url: str) -> dict[str, JsonValue]:
        return {
            "target_id": target_id,
            "url": url,
            "url_sha256": _url_digest(url),
            "application_id": self._application_id,
            "executable_sha256": self._enrollment.sha256,
            "executable_volume_serial": self._enrollment.identity.volume_serial,
            "executable_file_id": self._enrollment.identity.file_id,
            "fixed_arguments_fingerprint": sha256_fingerprint([*self._application.arguments, url]),
        }


def _validated_volume_state(value: MasterVolumeState) -> MasterVolumeState:
    if not isinstance(value, MasterVolumeState):
        raise CoreAudioError("master-volume adapter returned an invalid state")
    return MasterVolumeState(value.scalar, value.muted)


def _scalar_matches(left: float, right: float, tolerance: float) -> bool:
    return math.isfinite(left) and math.isfinite(right) and abs(left - right) <= tolerance


def _volume_state_matches(
    state: MasterVolumeState,
    scalar: float,
    muted: bool,
    *,
    tolerance: float,
) -> bool:
    return _scalar_matches(state.scalar, scalar, tolerance) and state.muted is muted


def _volume_precondition(
    before: MasterVolumeState,
    target: float,
    event_context: UUID,
) -> dict[str, JsonValue]:
    return {
        "before_scalar": before.scalar,
        "before_muted": before.muted,
        "target_scalar": target,
        "event_context": str(event_context),
    }


def _parse_volume_precondition(action: CanonicalAction) -> _VolumePrecondition:
    try:
        return _VolumePrecondition.model_validate(action.precondition)
    except ValidationError as exc:
        raise ComputerActionError("volume precondition is malformed") from exc


EffectContext = TypeVar("EffectContext", bound=BaseModel)


def _parse_rollback_context(
    effect: ActionEffect | None,
    model: type[EffectContext],
) -> EffectContext | None:
    if effect is None or effect.rollback_context is None:
        return None
    try:
        return model.model_validate(effect.rollback_context)
    except ValidationError:
        return None


def _clipboard_text_authority(text: str, maximum_bytes: int) -> tuple[str, int]:
    if "\x00" in text:
        raise ValueError("clipboard text cannot contain NUL")
    try:
        encoded = text.encode("utf-16-le", errors="strict")
    except UnicodeError as exc:
        raise ValueError("clipboard text must be valid Unicode") from exc
    if len(encoded) > maximum_bytes:
        raise ValueError("clipboard text exceeds the configured UTF-16 byte limit")
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def _validated_clipboard_snapshot(
    value: ClipboardSnapshot,
    *,
    maximum_bytes: int,
) -> ClipboardSnapshot:
    if not isinstance(value, ClipboardSnapshot):
        raise ClipboardError("clipboard adapter returned an invalid snapshot")
    if (
        isinstance(value.sequence, bool)
        or not isinstance(value.sequence, int)
        or value.sequence < 0
    ):
        raise ClipboardError("clipboard snapshot sequence is invalid")
    if (
        len(value.formats) > 32
        or len(value.formats) != len(set(value.formats))
        or any(
            isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 0xFFFFFFFF
            for item in value.formats
        )
    ):
        raise ClipboardError("clipboard snapshot formats are invalid")
    if value.text is None:
        if value.text_sha256 is not None or value.utf16_bytes != 0:
            raise ClipboardError("empty clipboard snapshot metadata is inconsistent")
        return value
    try:
        digest, utf16_bytes = _clipboard_text_authority(value.text, maximum_bytes)
    except ValueError as exc:
        raise ClipboardError("clipboard snapshot text is invalid or exceeds policy") from exc
    if (
        value.text_sha256 is None
        or not compare_digest(value.text_sha256, digest)
        or value.utf16_bytes != utf16_bytes
    ):
        raise ClipboardError("clipboard snapshot text metadata is inconsistent")
    return value


def _clipboard_precondition(
    snapshot: ClipboardSnapshot,
    token: str,
    requested_sha256: str,
    requested_utf16_bytes: int,
) -> dict[str, JsonValue]:
    return {
        "recovery_token": token,
        "before_sequence": snapshot.sequence,
        "before_sha256": snapshot.text_sha256,
        "before_utf16_bytes": snapshot.utf16_bytes,
        "before_formats": list(snapshot.formats),
        "requested_sha256": requested_sha256,
        "requested_utf16_bytes": requested_utf16_bytes,
    }


def _parse_clipboard_precondition(action: CanonicalAction) -> _ClipboardPrecondition:
    try:
        return _ClipboardPrecondition.model_validate(action.precondition)
    except ValidationError as exc:
        raise ComputerActionError("clipboard precondition is malformed") from exc


def _entry_matches_precondition(
    entry: _ClipboardRecoveryEntry,
    precondition: _ClipboardPrecondition,
) -> bool:
    return (
        entry.before_sequence == precondition.before_sequence
        and entry.before_sha256 == precondition.before_sha256
        and entry.before_utf16_bytes == precondition.before_utf16_bytes
        and entry.before_formats == precondition.before_formats
    )


def _url_digest(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8", errors="strict")).hexdigest()
