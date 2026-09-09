"""Typed Phase 3 computer actions and read-only computer tools.

Preparation is read-only.  It canonicalizes model-facing IDs or controlled-root
relative paths into exact broker authority data.  Only ``ActionHandler.execute``
methods mutate state, so the broker remains the sole mutation entrypoint.
"""

from __future__ import annotations

import asyncio
import os
import stat
import time
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from hmac import compare_digest
from pathlib import Path, PurePosixPath
from typing import Annotated, Protocol, TypeVar, cast, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from jarvis.core import (
    ApprovalRule,
    PermissionLevel,
    SensitivityClass,
    ToolConcurrency,
    ToolDefinition,
    ToolIdempotency,
    ToolResult,
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
    canonicalize,
    sha256_fingerprint,
)

from .config import ComputerAccessPolicy
from .windows import (
    AllowedRootGuard,
    ExecutableEnrollment,
    FileIdentity,
    FixedExecutableLauncher,
    IdentityMismatchError,
    MediaInputResult,
    MediaKey,
    PrinterStatus,
    RenamePostconditionError,
    RenameReceipt,
    UnsafePathError,
    WindowsPrimitiveError,
    discover_local_printers,
    rename_file_same_volume,
    rollback_rename,
    send_media_key,
)

_IDENTIFIER = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_-]{0,63}$",
    ),
]
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_IO_REPARSE_TAG_NAME_SURROGATE = 0x20000000
_MAX_SEARCH_ENTRIES = 1_000_000
_MAX_SEARCH_RELATIVE_PATH_BYTES = 400
_SEARCH_RESULT_FIXED_JSON_BYTES = 1_024
_SEARCH_RESULT_JSON_BYTES_PER_PATH = 3
_MAX_TOOL_RESULT_BYTES = 100 * 1_024
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


def _search_result_byte_cap(max_results: int) -> int:
    cap = _SEARCH_RESULT_FIXED_JSON_BYTES + max_results * (
        _MAX_SEARCH_RELATIVE_PATH_BYTES + _SEARCH_RESULT_JSON_BYTES_PER_PATH
    )
    if cap > _MAX_TOOL_RESULT_BYTES:
        raise ValueError("configured search results cannot fit the universal result byte limit")
    return cap


class ComputerActionError(RuntimeError):
    """Safe normalized failure at a computer-action boundary."""


class ActionPreparationError(ComputerActionError):
    """Raised before approval when an exact action cannot be prepared."""


class _ArgumentsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PreparedAction(BaseModel):
    """Read-only canonicalizer output consumed by the action coordinator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    normalized_arguments: dict[str, JsonValue]
    human_effect: Annotated[str, Field(min_length=1, max_length=2_000)]
    recovery_limits: Annotated[str, Field(min_length=1, max_length=2_000)]
    precondition: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("normalized_arguments", "precondition", mode="before")
    @classmethod
    def canonicalize_json_object(cls, value: object) -> object:
        normalized = canonicalize(value)
        if not isinstance(normalized, dict):
            raise TypeError("prepared arguments and precondition must be JSON objects")
        return normalized


@runtime_checkable
class ActionCanonicalizer(Protocol):
    @property
    def definition(self) -> ActionDefinition: ...

    @property
    def input_model(self) -> type[BaseModel]: ...

    def prepare(self, arguments: BaseModel) -> PreparedAction: ...


def prepare_action(
    canonicalizer: ActionCanonicalizer,
    raw_arguments: object,
) -> PreparedAction:
    """Validate untrusted arguments once, then run a read-only canonicalizer."""

    value = raw_arguments.model_dump() if isinstance(raw_arguments, BaseModel) else raw_arguments
    parsed = canonicalizer.input_model.model_validate(value)
    return PreparedAction.model_validate(canonicalizer.prepare(parsed))


def _json_schema(model: type[BaseModel]) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], model.model_json_schema())


def _schema_with_ids(
    model: type[BaseModel],
    field_name: str,
    identifiers: Sequence[str],
) -> dict[str, JsonValue]:
    schema = model.model_json_schema()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        field_schema = properties.get(field_name)
        if isinstance(field_schema, dict):
            field_schema["enum"] = sorted(identifiers)
    return cast(dict[str, JsonValue], schema)


def _ensure_policy_enabled(
    policy: ComputerAccessPolicy,
    required_level: PermissionLevel,
) -> None:
    if not policy.enabled:
        raise ValueError("computer access policy is disabled")
    if policy.maximum_permission_level < required_level:
        raise ValueError(
            f"computer access policy does not enable permission Level {int(required_level)}"
        )


def _action_arguments(
    action: CanonicalAction,
    definition: ActionDefinition,
    model: type[BaseModel],
) -> BaseModel:
    if (
        action.action_id != definition.action_id
        or action.action_version != definition.version
        or action.permission_level is not definition.tool.permission_level
        or action.approval_rule is not definition.tool.approval_rule
    ):
        raise ComputerActionError("canonical action does not match registered definition")
    return model.model_validate(action.normalized_arguments)


def _require_precondition(action: CanonicalAction, expected: Mapping[str, JsonValue]) -> None:
    if canonicalize(action.precondition) != canonicalize(dict(expected)):
        raise IdentityMismatchError("canonical action precondition no longer matches")


def _unavailable_rollback(summary: str) -> RollbackReceipt:
    return RollbackReceipt(status=RollbackStatus.UNAVAILABLE, summary=summary)


class ApplicationLaunchArguments(_ArgumentsModel):
    application_id: _IDENTIFIER


class AppGroupLaunchArguments(_ArgumentsModel):
    group_id: _IDENTIFIER


class MediaOperation(StrEnum):
    PREVIOUS_TRACK = "previous_track"
    NEXT_TRACK = "next_track"
    STOP = "stop"
    PLAY_PAUSE = "play_pause"
    MUTE_TOGGLE = "mute_toggle"


_MEDIA_KEYS = {
    MediaOperation.PREVIOUS_TRACK: MediaKey.PREVIOUS_TRACK,
    MediaOperation.NEXT_TRACK: MediaKey.NEXT_TRACK,
    MediaOperation.STOP: MediaKey.STOP,
    MediaOperation.PLAY_PAUSE: MediaKey.PLAY_PAUSE,
    MediaOperation.MUTE_TOGGLE: MediaKey.VOLUME_MUTE,
}


class MediaControlArguments(_ArgumentsModel):
    operation: MediaOperation


def _controlled_relative_path(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("controlled path must be a normalized forward-slash relative path")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or len(candidate.parts) > 16
        or any(component in {"", ".", ".."} for component in candidate.parts)
        or candidate.as_posix() != value
    ):
        raise ValueError("controlled path must remain beneath the configured root")
    for component in candidate.parts:
        if (
            component.endswith((" ", "."))
            or any(character in '<>:"|?*' for character in component)
            or component.split(".", maxsplit=1)[0].upper() in _WINDOWS_RESERVED_NAMES
        ):
            raise ValueError("controlled path contains a forbidden Windows name")
    return value


class ReversibleMoveArguments(_ArgumentsModel):
    source: Annotated[str, Field(min_length=1, max_length=1_000)]
    destination: Annotated[str, Field(min_length=1, max_length=1_000)]

    @field_validator("source", "destination")
    @classmethod
    def validate_controlled_path(cls, value: str) -> str:
        return _controlled_relative_path(value)

    @model_validator(mode="after")
    def require_distinct_paths(self) -> ReversibleMoveArguments:
        if self.source.casefold() == self.destination.casefold():
            raise ValueError("move source and destination must be distinct")
        return self


class SearchControlledFilesArguments(_ArgumentsModel):
    query: Annotated[str, Field(min_length=1, max_length=128)]
    limit: Annotated[int, Field(strict=True, ge=1, le=200)] = 20

    @field_validator("query")
    @classmethod
    def validate_filename_query(cls, value: str) -> str:
        if (
            value != value.strip()
            or any(ord(character) < 32 for character in value)
            or any(character in "/\\:" for character in value)
        ):
            raise ValueError("query must be filename text, not a path")
        return value


class LocalPrinterStatusArguments(_ArgumentsModel):
    printer_id: _IDENTIFIER | None = None


class _ApplicationEffect(_ArgumentsModel):
    application_id: _IDENTIFIER
    pid: Annotated[int, Field(strict=True, gt=0)]
    image_verified: bool


class _GroupApplicationEffect(_ArgumentsModel):
    application_id: _IDENTIFIER
    pid: Annotated[int, Field(strict=True, gt=0)]
    image_verified: bool


class _AppGroupEffect(_ArgumentsModel):
    group_id: _IDENTIFIER
    launched: Annotated[tuple[_GroupApplicationEffect, ...], Field(max_length=8)]
    complete: bool
    failed_application_id: _IDENTIFIER | None = None


class _MediaEffect(_ArgumentsModel):
    operation: MediaOperation
    requested_count: Annotated[int, Field(strict=True, ge=0, le=2)]
    accepted_count: Annotated[int, Field(strict=True, ge=0, le=2)]
    last_error: Annotated[int, Field(strict=True, ge=0)] | None = None


class _MoveContext(_ArgumentsModel):
    source: Annotated[str, Field(min_length=1, max_length=1_000)]
    destination: Annotated[str, Field(min_length=1, max_length=1_000)]
    volume_serial: Annotated[int, Field(strict=True, ge=0)]
    file_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    size: Annotated[int, Field(strict=True, ge=0)]
    modified_100ns: Annotated[int, Field(strict=True, ge=0)]
    link_count: Annotated[int, Field(strict=True, ge=1)]
    attributes: Annotated[int, Field(strict=True, ge=0)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


EffectModel = TypeVar("EffectModel", bound=BaseModel)


def _parse_effect(effect: ActionEffect | None, model: type[EffectModel]) -> EffectModel | None:
    if effect is None:
        return None
    try:
        return model.model_validate(effect.result)
    except ValidationError:
        return None


class LaunchObservation(Protocol):
    @property
    def pid(self) -> int: ...

    @property
    def image_verified(self) -> bool: ...


EnrollmentCapture = Callable[[Path], ExecutableEnrollment]
ApplicationLauncher = Callable[[ExecutableEnrollment, tuple[str, ...]], LaunchObservation]


def _default_application_launcher(
    enrollment: ExecutableEnrollment,
    arguments: tuple[str, ...],
) -> LaunchObservation:
    return FixedExecutableLauncher(enrollment, arguments).launch()


def _capture_enrollments(
    policy: ComputerAccessPolicy,
    application_ids: Sequence[str],
    capture: EnrollmentCapture,
) -> dict[str, ExecutableEnrollment]:
    enrollments: dict[str, ExecutableEnrollment] = {}
    for application_id in application_ids:
        application = policy.applications[application_id]
        enrollment = capture(application.executable)
        if not compare_digest(application.sha256, enrollment.sha256):
            raise IdentityMismatchError(
                f"configured SHA-256 does not match enrolled application ID {application_id!r}"
            )
        enrollments[application_id] = enrollment
    return enrollments


def _application_precondition(
    application_id: str,
    enrollment: ExecutableEnrollment,
    arguments: tuple[str, ...],
) -> dict[str, JsonValue]:
    return {
        "application_id": application_id,
        "executable_sha256": enrollment.sha256,
        "executable_volume_serial": enrollment.identity.volume_serial,
        "executable_file_id": enrollment.identity.file_id,
        "arguments_fingerprint": sha256_fingerprint(list(arguments)),
    }


class ApplicationLaunchHandler:
    def __init__(
        self,
        policy: ComputerAccessPolicy,
        *,
        capture_enrollment: EnrollmentCapture = ExecutableEnrollment.capture,
        launch_application: ApplicationLauncher = _default_application_launcher,
    ) -> None:
        _ensure_policy_enabled(policy, PermissionLevel.LEVEL_1)
        if not policy.applications:
            raise ValueError("application launch requires at least one configured application")
        self._applications = dict(policy.applications)
        self._enrollments = _capture_enrollments(
            policy,
            tuple(self._applications),
            capture_enrollment,
        )
        self._launch = launch_application
        timeout = min(
            30.0,
            max(application.startup_timeout_seconds for application in self._applications.values())
            + 1,
        )
        tool = ToolDefinition(
            name="launch_application",
            version="1",
            description="Launch one host-enrolled application by fixed application ID.",
            input_schema=_schema_with_ids(
                ApplicationLaunchArguments,
                "application_id",
                tuple(self._applications),
            ),
            permission_level=PermissionLevel.LEVEL_1,
            approval_rule=ApprovalRule.EXPLICIT_ENABLEMENT,
            risk=ToolRisk.REVERSIBLE,
            side_effect=ToolSideEffect.REVERSIBLE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.app.launch",),
            timeout_seconds=timeout,
            max_result_bytes=2_048,
            max_result_items=3,
            idempotency=ToolIdempotency.IDEMPOTENCY_KEY,
            retry_policy=ToolRetryPolicy.RECONCILE_FIRST,
            concurrency=ToolConcurrency.SERIAL_PER_SESSION,
            postcondition="The spawned process image matches the enrolled executable identity.",
            recovery=(
                "No automatic close is attempted because terminating an application could lose "
                "user data; close the launched application manually if unwanted."
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
        return ApplicationLaunchArguments

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        parsed = ApplicationLaunchArguments.model_validate(arguments)
        application = self._applications.get(parsed.application_id)
        enrollment = self._enrollments.get(parsed.application_id)
        if application is None or enrollment is None:
            raise ActionPreparationError("application ID is not configured")
        return PreparedAction(
            normalized_arguments={"application_id": parsed.application_id},
            human_effect=f"Launch configured application '{parsed.application_id}'.",
            recovery_limits=(
                "JARVIS will not automatically terminate the application because it may contain "
                "user work."
            ),
            precondition=_application_precondition(
                parsed.application_id,
                enrollment,
                application.arguments,
            ),
        )

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        parsed = cast(
            ApplicationLaunchArguments,
            _action_arguments(action, self._definition, ApplicationLaunchArguments),
        )
        application = self._applications.get(parsed.application_id)
        enrollment = self._enrollments.get(parsed.application_id)
        if application is None or enrollment is None:
            raise ComputerActionError("application ID is no longer configured")
        _require_precondition(
            action,
            _application_precondition(parsed.application_id, enrollment, application.arguments),
        )
        observation = await asyncio.to_thread(
            self._launch,
            enrollment,
            application.arguments,
        )
        result: dict[str, JsonValue] = {
            "application_id": parsed.application_id,
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
            ApplicationLaunchArguments,
            _action_arguments(action, self._definition, ApplicationLaunchArguments),
        )
        observed = _parse_effect(effect, _ApplicationEffect)
        passed = (
            observed is not None
            and observed.application_id == parsed.application_id
            and observed.image_verified
        )
        return PostconditionEvidence(
            status=PostconditionStatus.PASSED if passed else PostconditionStatus.UNKNOWN,
            summary=(
                "Spawned process image matched the enrolled executable."
                if passed
                else "Spawned process image could not be verified."
            ),
            detail={"application_id": parsed.application_id},
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
            "Automatic application termination is unavailable because it could discard user data."
        )


class AppGroupLaunchHandler:
    def __init__(
        self,
        policy: ComputerAccessPolicy,
        *,
        capture_enrollment: EnrollmentCapture = ExecutableEnrollment.capture,
        launch_application: ApplicationLauncher = _default_application_launcher,
    ) -> None:
        _ensure_policy_enabled(policy, PermissionLevel.LEVEL_1)
        if not policy.app_groups:
            raise ValueError("app-group launch requires at least one configured group")
        self._applications = dict(policy.applications)
        self._groups = dict(policy.app_groups)
        max_group_result_items = max(
            len(group.applications) * 3 + 3 for group in self._groups.values()
        )
        used_ids = tuple(
            dict.fromkeys(
                application_id
                for group in self._groups.values()
                for application_id in group.applications
            )
        )
        self._enrollments = _capture_enrollments(policy, used_ids, capture_enrollment)
        self._launch = launch_application
        tool = ToolDefinition(
            name="launch_app_group",
            version="1",
            description="Launch one host-enrolled ordered application group by fixed group ID.",
            input_schema=_schema_with_ids(
                AppGroupLaunchArguments,
                "group_id",
                tuple(self._groups),
            ),
            permission_level=PermissionLevel.LEVEL_1,
            approval_rule=ApprovalRule.EXPLICIT_ENABLEMENT,
            risk=ToolRisk.REVERSIBLE,
            side_effect=ToolSideEffect.REVERSIBLE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.app_group.launch",),
            timeout_seconds=30,
            max_result_bytes=8_192,
            max_result_items=max_group_result_items,
            idempotency=ToolIdempotency.IDEMPOTENCY_KEY,
            retry_policy=ToolRetryPolicy.RECONCILE_FIRST,
            concurrency=ToolConcurrency.SERIAL_PER_SESSION,
            postcondition=(
                "Every configured group member reports a spawned process image matching its "
                "enrollment."
            ),
            recovery=(
                "Partial launch is reported exactly; applications are not automatically killed "
                "because they may contain user work."
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
        return AppGroupLaunchArguments

    def _precondition(self, group_id: str) -> dict[str, JsonValue]:
        group = self._groups[group_id]
        applications: list[JsonValue] = []
        for application_id in group.applications:
            application = self._applications[application_id]
            applications.append(
                _application_precondition(
                    application_id,
                    self._enrollments[application_id],
                    application.arguments,
                )
            )
        return {"group_id": group_id, "applications": applications}

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        parsed = AppGroupLaunchArguments.model_validate(arguments)
        if parsed.group_id not in self._groups:
            raise ActionPreparationError("application group ID is not configured")
        return PreparedAction(
            normalized_arguments={"group_id": parsed.group_id},
            human_effect=f"Launch configured application group '{parsed.group_id}'.",
            recovery_limits=(
                "Partial launch is possible. JARVIS will report launched application IDs but "
                "will not terminate applications automatically."
            ),
            precondition=self._precondition(parsed.group_id),
        )

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        parsed = cast(
            AppGroupLaunchArguments,
            _action_arguments(action, self._definition, AppGroupLaunchArguments),
        )
        group = self._groups.get(parsed.group_id)
        if group is None:
            raise ComputerActionError("application group ID is no longer configured")
        _require_precondition(action, self._precondition(parsed.group_id))
        launched: list[JsonValue] = []
        failed: str | None = None
        for application_id in group.applications:
            application = self._applications[application_id]
            try:
                observation = await asyncio.to_thread(
                    self._launch,
                    self._enrollments[application_id],
                    application.arguments,
                )
            except Exception:
                failed = application_id
                break
            launched.append(
                {
                    "application_id": application_id,
                    "pid": observation.pid,
                    "image_verified": observation.image_verified,
                }
            )
            if not observation.image_verified:
                failed = application_id
                break
        complete = failed is None and len(launched) == len(group.applications)
        result: dict[str, JsonValue] = {
            "group_id": parsed.group_id,
            "launched": launched,
            "complete": complete,
            "failed_application_id": failed,
        }
        return ActionEffect(result=result)

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        parsed = cast(
            AppGroupLaunchArguments,
            _action_arguments(action, self._definition, AppGroupLaunchArguments),
        )
        group = self._groups.get(parsed.group_id)
        observed = _parse_effect(effect, _AppGroupEffect)
        expected_ids = tuple(group.applications) if group is not None else ()
        observed_ids = (
            tuple(item.application_id for item in observed.launched) if observed is not None else ()
        )
        passed = (
            observed is not None
            and observed.group_id == parsed.group_id
            and observed.complete
            and observed.failed_application_id is None
            and observed_ids == expected_ids
            and all(item.image_verified for item in observed.launched)
        )
        return PostconditionEvidence(
            status=PostconditionStatus.PASSED if passed else PostconditionStatus.MISMATCH,
            summary=(
                "Every configured application group member was image-verified."
                if passed
                else "Application group launch was partial or could not be fully verified."
            ),
            detail={
                "group_id": parsed.group_id,
                "launched_application_ids": list(observed_ids),
            },
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
            "Automatic group termination is unavailable because it could discard user data."
        )


MediaSender = Callable[[MediaKey], MediaInputResult]


class MediaControlHandler:
    def __init__(self, *, send_input: MediaSender = send_media_key) -> None:
        self._send = send_input
        tool = ToolDefinition(
            name="control_media",
            version="1",
            description="Inject one fixed global Windows media key-down/key-up pair.",
            input_schema=_json_schema(MediaControlArguments),
            permission_level=PermissionLevel.LEVEL_1,
            approval_rule=ApprovalRule.EXPLICIT_ENABLEMENT,
            risk=ToolRisk.REVERSIBLE,
            side_effect=ToolSideEffect.REVERSIBLE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.media.control",),
            timeout_seconds=2,
            max_result_bytes=2_048,
            max_result_items=4,
            idempotency=ToolIdempotency.NON_IDEMPOTENT,
            retry_policy=ToolRetryPolicy.NEVER,
            concurrency=ToolConcurrency.SERIAL_GLOBAL,
            postcondition=(
                "Windows accepts exactly one key-down and one key-up input; target application "
                "and playback state are explicitly not verified."
            ),
            recovery=(
                "No automatic retry or inverse media key is sent because global media routing "
                "and toggle state are ambiguous."
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
        return MediaControlArguments

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        parsed = MediaControlArguments.model_validate(arguments)
        key = _MEDIA_KEYS[parsed.operation]
        return PreparedAction(
            normalized_arguments={"operation": parsed.operation.value},
            human_effect=f"Send one global media '{parsed.operation.value}' input pair.",
            recovery_limits=(
                "Windows input acceptance does not identify the receiving application or prove "
                "playback state. The input will never be retried automatically."
            ),
            precondition={"virtual_key": key.name, "requested_input_count": 2},
        )

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        parsed = cast(
            MediaControlArguments,
            _action_arguments(action, self._definition, MediaControlArguments),
        )
        key = _MEDIA_KEYS[parsed.operation]
        _require_precondition(
            action,
            {"virtual_key": key.name, "requested_input_count": 2},
        )
        observed = await asyncio.to_thread(self._send, key)
        result: dict[str, JsonValue] = {
            "operation": parsed.operation.value,
            "requested_count": observed.requested_count,
            "accepted_count": observed.accepted_count,
            "last_error": observed.last_error,
        }
        return ActionEffect(result=result)

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        parsed = cast(
            MediaControlArguments,
            _action_arguments(action, self._definition, MediaControlArguments),
        )
        observed = _parse_effect(effect, _MediaEffect)
        passed = (
            observed is not None
            and observed.operation is parsed.operation
            and observed.requested_count == 2
            and observed.accepted_count == 2
        )
        return PostconditionEvidence(
            status=PostconditionStatus.PASSED if passed else PostconditionStatus.MISMATCH,
            summary=(
                "Windows accepted one media key-down/key-up pair; playback state remains "
                "unverified."
                if passed
                else "Windows did not accept the complete media input pair."
            ),
            detail={
                "operation": parsed.operation.value,
                "scope": "input_acceptance_only",
                "playback_state_verified": False,
            },
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
            "Media input cannot be safely inverted because the target and playback state are "
            "unknown."
        )


RenameOperation = Callable[
    [AllowedRootGuard, str | os.PathLike[str], str | os.PathLike[str]], RenameReceipt
]
RollbackOperation = Callable[[AllowedRootGuard, RenameReceipt], FileIdentity]


def _identity_precondition(identity: FileIdentity) -> dict[str, JsonValue]:
    if identity.sha256 is None:
        raise ActionPreparationError("source content hash was not captured")
    return {
        "volume_serial": identity.volume_serial,
        "file_id": identity.file_id,
        "size": identity.size,
        "modified_100ns": identity.modified_100ns,
        "sha256": identity.sha256,
    }


class ReversibleMoveHandler:
    def __init__(
        self,
        policy: ComputerAccessPolicy,
        *,
        guard: AllowedRootGuard | None = None,
        rename_operation: RenameOperation = rename_file_same_volume,
        rollback_operation: RollbackOperation = rollback_rename,
    ) -> None:
        _ensure_policy_enabled(policy, PermissionLevel.LEVEL_2)
        self._root = policy.controlled_root
        self._max_file_bytes = policy.max_file_bytes
        self._guard = guard or AllowedRootGuard((self._root,))
        self._rename = rename_operation
        self._rollback = rollback_operation
        tool = ToolDefinition(
            name="move_controlled_file",
            version="1",
            description=(
                "Move one exact existing regular file between paths beneath the controlled root."
            ),
            input_schema=_json_schema(ReversibleMoveArguments),
            permission_level=PermissionLevel.LEVEL_2,
            approval_rule=ApprovalRule.POLICY_OR_EXPLICIT,
            risk=ToolRisk.REVERSIBLE,
            side_effect=ToolSideEffect.REVERSIBLE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.files.move",),
            timeout_seconds=30,
            max_result_bytes=4_096,
            max_result_items=4,
            idempotency=ToolIdempotency.IDEMPOTENCY_KEY,
            retry_policy=ToolRetryPolicy.RECONCILE_FIRST,
            concurrency=ToolConcurrency.SERIAL_GLOBAL,
            postcondition=(
                "The destination contains the approved volume/file ID and content hash, and the "
                "source path is absent."
            ),
            recovery=(
                "Rollback renames the same unchanged file ID to the absent source path; any "
                "collision or identity drift refuses rollback."
            ),
        )
        self._definition = ActionDefinition(
            tool=tool,
            supports_rollback=True,
            effect_may_outlive_cancellation=True,
            rollback_timeout_seconds=30,
        )

    @property
    def definition(self) -> ActionDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return ReversibleMoveArguments

    def _absolute(self, relative: str) -> Path:
        return self._root.joinpath(*PurePosixPath(relative).parts)

    def _probe_move(
        self,
        parsed: ReversibleMoveArguments,
    ) -> tuple[FileIdentity, FileIdentity]:
        source = self._guard.probe_existing_file(
            self._absolute(parsed.source),
            compute_sha256=True,
            for_mutation=True,
        )
        if source.size > self._max_file_bytes:
            raise ActionPreparationError("source file exceeds the configured move size limit")
        destination = self._absolute(parsed.destination)
        _target, destination_parent = self._guard._prepare_destination(destination)
        if source.volume_serial != destination_parent.volume_serial:
            raise UnsafePathError("cross-volume moves are not accepted")
        return source, destination_parent

    def _precondition(
        self,
        parsed: ReversibleMoveArguments,
        source: FileIdentity,
        destination_parent: FileIdentity,
    ) -> dict[str, JsonValue]:
        return {
            "source": parsed.source,
            "destination": parsed.destination,
            "source_identity": _identity_precondition(source),
            "destination_parent_volume_serial": destination_parent.volume_serial,
            "destination_parent_file_id": destination_parent.file_id,
            "destination_must_not_exist": True,
        }

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        parsed = ReversibleMoveArguments.model_validate(arguments)
        source, destination_parent = self._probe_move(parsed)
        return PreparedAction(
            normalized_arguments={
                "source": parsed.source,
                "destination": parsed.destination,
            },
            human_effect=(
                f"Move controlled file '{parsed.source}' to '{parsed.destination}' without "
                "overwrite."
            ),
            recovery_limits=(
                "Rollback is possible only while the moved file is unchanged and the original "
                "source path remains absent."
            ),
            precondition=self._precondition(parsed, source, destination_parent),
        )

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        parsed = cast(
            ReversibleMoveArguments,
            _action_arguments(action, self._definition, ReversibleMoveArguments),
        )
        source, destination_parent = await asyncio.to_thread(self._probe_move, parsed)
        _require_precondition(action, self._precondition(parsed, source, destination_parent))
        receipt = await asyncio.to_thread(
            self._rename,
            self._guard,
            self._absolute(parsed.source),
            self._absolute(parsed.destination),
        )
        approved_sha256 = source.sha256
        assert approved_sha256 is not None
        context = _MoveContext(
            source=parsed.source,
            destination=parsed.destination,
            volume_serial=receipt.identity.volume_serial,
            file_id=receipt.identity.file_id,
            size=receipt.identity.size,
            modified_100ns=receipt.identity.modified_100ns,
            link_count=receipt.identity.link_count,
            attributes=receipt.identity.attributes,
            sha256=approved_sha256,
        )
        result: dict[str, JsonValue] = {
            "source": parsed.source,
            "destination": parsed.destination,
            "file_id": receipt.identity.file_id,
            "moved": True,
        }
        return ActionEffect(
            result=result,
            rollback_context=cast(JsonValue, context.model_dump(mode="json")),
        )

    def _context(self, effect: ActionEffect | None) -> _MoveContext | None:
        if effect is None or effect.rollback_context is None:
            return None
        try:
            return _MoveContext.model_validate(effect.rollback_context)
        except ValidationError:
            return None

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        parsed = cast(
            ReversibleMoveArguments,
            _action_arguments(action, self._definition, ReversibleMoveArguments),
        )
        context = self._context(effect)
        if (
            context is None
            or context.source != parsed.source
            or context.destination != parsed.destination
        ):
            return PostconditionEvidence(
                status=PostconditionStatus.UNKNOWN,
                summary="Move receipt is absent or malformed.",
            )
        source_abs = self._absolute(context.source)
        try:
            destination = await asyncio.to_thread(
                self._guard.probe_existing_file,
                self._absolute(context.destination),
                compute_sha256=True,
                for_mutation=True,
            )
        except (OSError, WindowsPrimitiveError):
            destination = None
        source_absent = not await asyncio.to_thread(os.path.lexists, source_abs)
        passed = (
            destination is not None and source_absent and _context_matches(context, destination)
        )
        return PostconditionEvidence(
            status=PostconditionStatus.PASSED if passed else PostconditionStatus.MISMATCH,
            summary=(
                "Approved file identity is present only at the destination."
                if passed
                else "Moved file identity or source/destination state does not match."
            ),
            detail={
                "source": context.source,
                "destination": context.destination,
                "source_absent": source_absent,
            },
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
            ReversibleMoveArguments,
            _action_arguments(action, self._definition, ReversibleMoveArguments),
        )
        context = self._context(effect)
        if context is None:
            return _unavailable_rollback("Move rollback receipt is absent or malformed.")
        try:
            current = await asyncio.to_thread(
                self._guard.probe_existing_file,
                self._absolute(context.destination),
                compute_sha256=True,
                for_mutation=True,
            )
        except (OSError, WindowsPrimitiveError):
            current = None
        if current is None or not _context_matches(context, current):
            return RollbackReceipt(
                status=RollbackStatus.FAILED,
                summary="Rollback refused because the path, file identity, or content changed.",
                detail={"source": context.source, "destination": context.destination},
            )
        identity = FileIdentity(
            path=self._absolute(context.destination),
            final_path="",
            volume_serial=context.volume_serial,
            file_id=context.file_id,
            size=context.size,
            modified_100ns=context.modified_100ns,
            link_count=context.link_count,
            attributes=context.attributes,
            sha256=None,
        )
        receipt = RenameReceipt(
            source=self._absolute(context.source),
            destination=self._absolute(context.destination),
            identity=identity,
        )
        try:
            restored = await asyncio.to_thread(self._rollback, self._guard, receipt)
        except RenamePostconditionError as error:
            recovery = error.recovery
            recovery_evidence_bound = (
                recovery.source == receipt.destination
                and recovery.destination == receipt.source
                and receipt.identity.same_object(recovery.identity)
            )
            return RollbackReceipt(
                status=RollbackStatus.FAILED,
                summary=(
                    "Rollback was dispatched, but its final path state is uncertain; "
                    "reconciliation is required."
                ),
                detail={
                    "source": context.source,
                    "destination": context.destination,
                    "effect_may_have_completed": True,
                    "reconciliation_required": True,
                    "recovery_evidence_bound": recovery_evidence_bound,
                    "primitive_postcondition_verified": recovery.postcondition_verified,
                },
            )
        except (OSError, WindowsPrimitiveError):
            return RollbackReceipt(
                status=RollbackStatus.FAILED,
                summary="Rollback refused because the path or file identity changed.",
                detail={"source": context.source, "destination": context.destination},
            )
        return RollbackReceipt(
            status=RollbackStatus.SUCCEEDED,
            summary="The unchanged file identity was restored to its original controlled path.",
            detail={
                "source": context.source,
                "destination": context.destination,
                "file_id": restored.file_id,
            },
        )


def _context_matches(context: _MoveContext, identity: FileIdentity) -> bool:
    return (
        context.volume_serial == identity.volume_serial
        and compare_digest(context.file_id, identity.file_id)
        and context.size == identity.size
        and context.modified_100ns == identity.modified_100ns
        and identity.sha256 is not None
        and compare_digest(context.sha256, identity.sha256)
    )


class SearchControlledFilesTool:
    def __init__(
        self,
        policy: ComputerAccessPolicy,
        *,
        guard: AllowedRootGuard | None = None,
        max_entries: int = 10_000,
        max_depth: int = 16,
        scan_timeout_seconds: float = 5.0,
    ) -> None:
        _ensure_policy_enabled(policy, PermissionLevel.LEVEL_0)
        if (
            not 1 <= max_entries <= _MAX_SEARCH_ENTRIES
            or not 1 <= max_depth <= 32
            or not 0 < scan_timeout_seconds <= 30
        ):
            raise ValueError("search entry, depth, and timeout limits are invalid")
        self._root = policy.controlled_root
        self._guard = guard or AllowedRootGuard((self._root,))
        root_stat = os.lstat(self._root)
        self._root_identity = (root_stat.st_dev, root_stat.st_ino)
        self._max_results = policy.max_search_results
        self._max_entries = max_entries
        self._max_depth = max_depth
        self._scan_timeout_seconds = scan_timeout_seconds
        self._definition = ToolDefinition(
            name="search_controlled_files",
            version="1",
            description=(
                "Search filenames beneath the controlled root without reading file content."
            ),
            input_schema=_json_schema(SearchControlledFilesArguments),
            permission_level=PermissionLevel.LEVEL_0,
            approval_rule=ApprovalRule.NONE,
            risk=ToolRisk.READ_ONLY,
            side_effect=ToolSideEffect.NONE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.files.search",),
            timeout_seconds=min(30.0, scan_timeout_seconds + 1),
            max_result_bytes=_search_result_byte_cap(policy.max_search_results),
            max_result_items=policy.max_search_results + 3,
            idempotency=ToolIdempotency.SIDE_EFFECT_FREE,
            retry_policy=ToolRetryPolicy.TRANSIENT_ONLY,
            concurrency=ToolConcurrency.PARALLEL,
            postcondition="Every returned relative path is a matched regular file under the root.",
            recovery=(
                "No side effect occurs; narrow the filename query or retry after transient I/O."
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return SearchControlledFilesArguments

    async def invoke(self, arguments: BaseModel) -> ToolResult:
        parsed = SearchControlledFilesArguments.model_validate(arguments)
        limit = min(parsed.limit, self._max_results)
        try:
            matches, scanned, truncated = await asyncio.to_thread(
                self._search,
                parsed.query,
                limit,
            )
        except (OSError, WindowsPrimitiveError):
            return ToolResult(
                content="Controlled filename search failed safely.",
                is_error=True,
                data={"code": "controlled_search_failed"},
            )
        data: dict[str, JsonValue] = {
            "matches": cast(list[JsonValue], matches),
            "count": len(matches),
            "scanned_entries": scanned,
            "truncated": truncated,
        }
        return ToolResult(
            content=f"Found {len(matches)} controlled filename match(es).",
            data=data,
        )

    def _search(self, query: str, limit: int) -> tuple[list[str], int, bool]:
        root_stat = os.lstat(self._root)
        if (root_stat.st_dev, root_stat.st_ino) != self._root_identity:
            raise IdentityMismatchError("controlled search root identity changed")
        attributes = int(getattr(root_stat, "st_file_attributes", 0))
        tag = int(getattr(root_stat, "st_reparse_tag", 0))
        if attributes & _FILE_ATTRIBUTE_REPARSE_POINT and tag & _IO_REPARSE_TAG_NAME_SURROGATE:
            raise UnsafePathError("controlled search root became a name surrogate")

        deadline = time.monotonic() + self._scan_timeout_seconds
        pending: list[tuple[Path, int]] = [(self._root, 0)]
        matches: list[str] = []
        scanned = 0
        truncated = False
        needle = query.casefold()
        while pending:
            directory, depth = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > self._max_entries or time.monotonic() > deadline:
                        truncated = True
                        pending.clear()
                        break
                    try:
                        entry_stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    entry_attributes = int(getattr(entry_stat, "st_file_attributes", 0))
                    entry_tag = int(getattr(entry_stat, "st_reparse_tag", 0))
                    is_reparse = bool(entry_attributes & _FILE_ATTRIBUTE_REPARSE_POINT)
                    is_name_surrogate = is_reparse and bool(
                        entry_tag & _IO_REPARSE_TAG_NAME_SURROGATE
                    )
                    if stat.S_ISDIR(entry_stat.st_mode):
                        if not is_reparse and depth < self._max_depth:
                            pending.append((Path(entry.path), depth + 1))
                        continue
                    if is_name_surrogate or not stat.S_ISREG(entry_stat.st_mode):
                        continue
                    if needle not in entry.name.casefold():
                        continue
                    try:
                        self._guard.probe_existing_file(entry.path)
                    except (OSError, WindowsPrimitiveError):
                        continue
                    relative = Path(entry.path).relative_to(self._root).as_posix()
                    encoded_bytes = len(relative.encode("utf-8"))
                    if encoded_bytes > _MAX_SEARCH_RELATIVE_PATH_BYTES or any(
                        ord(character) < 32 or character in '"\\' for character in relative
                    ):
                        truncated = True
                        pending.clear()
                        break
                    matches.append(relative)
                    if len(matches) >= limit:
                        truncated = True
                        pending.clear()
                        break
        matches.sort(key=str.casefold)
        return matches, scanned, truncated


class PrinterDiscovery(Protocol):
    def __call__(self, *, max_printers: int = 64) -> tuple[PrinterStatus, ...]: ...


class LocalPrinterStatusTool:
    def __init__(
        self,
        policy: ComputerAccessPolicy,
        *,
        discover: PrinterDiscovery = discover_local_printers,
    ) -> None:
        _ensure_policy_enabled(policy, PermissionLevel.LEVEL_0)
        self._printers = dict(policy.printers)
        self._discover = discover
        schema = _schema_with_ids(
            LocalPrinterStatusArguments,
            "printer_id",
            tuple(self._printers),
        )
        self._definition = ToolDefinition(
            name="get_local_printer_status",
            version="1",
            description="Read status for configured local printer aliases without submitting jobs.",
            input_schema=schema,
            permission_level=PermissionLevel.LEVEL_0,
            approval_rule=ApprovalRule.NONE,
            risk=ToolRisk.READ_ONLY,
            side_effect=ToolSideEffect.NONE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.printer.status",),
            timeout_seconds=10,
            max_result_bytes=16_384,
            max_result_items=max(1, len(self._printers) * 4 + 1),
            idempotency=ToolIdempotency.SIDE_EFFECT_FREE,
            retry_policy=ToolRetryPolicy.TRANSIENT_ONLY,
            concurrency=ToolConcurrency.PARALLEL,
            postcondition="Results contain only configured aliases matched to local queue status.",
            recovery=(
                "No print job is created; retry status discovery after transient spooler errors."
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return LocalPrinterStatusArguments

    async def invoke(self, arguments: BaseModel) -> ToolResult:
        parsed = LocalPrinterStatusArguments.model_validate(arguments)
        if parsed.printer_id is not None and parsed.printer_id not in self._printers:
            return ToolResult(
                content="Printer alias is not configured.",
                is_error=True,
                data={"code": "unknown_printer_alias"},
            )
        try:
            discovered = await asyncio.to_thread(self._discover, max_printers=256)
        except (OSError, WindowsPrimitiveError):
            return ToolResult(
                content="Local printer status discovery failed safely.",
                is_error=True,
                data={"code": "printer_status_failed"},
            )
        by_name = {printer.name.casefold(): printer for printer in discovered}
        aliases = (
            (parsed.printer_id,) if parsed.printer_id is not None else tuple(sorted(self._printers))
        )
        results: list[JsonValue] = []
        for alias in aliases:
            configured = self._printers[alias]
            printer = by_name.get(configured.system_name.casefold())
            results.append(
                {
                    "printer_id": alias,
                    "installed": printer is not None,
                    "status_available": printer is not None and printer.status is not None,
                    "status_flags": printer.status if printer is not None else None,
                }
            )
        data: dict[str, JsonValue] = {"printers": results, "count": len(results)}
        return ToolResult(
            content=f"Read status for {len(results)} configured printer alias(es).",
            data=data,
        )
