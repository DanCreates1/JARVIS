"""Strict values crossing the Phase 3 policy, approval, and broker boundaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import IntEnum, StrEnum
from hmac import compare_digest
from typing import Annotated, Self

from pydantic import (
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from jarvis.core import ApprovalRule, PermissionLevel, ToolDefinition, ToolSideEffect
from jarvis.core.models import CoreModel, Identifier

from .canonical import canonicalize, sha256_fingerprint

MAX_ACTION_TTL = timedelta(minutes=15)
MAX_APPROVAL_TTL = timedelta(minutes=10)
MAX_GRANT_TTL = timedelta(minutes=5)

ActionIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$",
    ),
]
ActionVersion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+(?:\.[0-9]+){0,2}$",
    ),
]
Fingerprint = Annotated[
    str,
    StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$", min_length=71, max_length=71),
]
Capability = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$",
    ),
]


class DomainModel(CoreModel):
    """Strict immutable model for authority-bearing data."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class InteractionInterface(StrEnum):
    LOCAL_CLI = "local_cli"
    LOCAL_WEB = "local_web"
    VOICE = "voice"
    SYSTEM = "system"
    TEST = "test"


class AuthenticationAssurance(IntEnum):
    UNAUTHENTICATED = 0
    LOCAL_SESSION = 1
    RECENT_AUTH = 2
    STEP_UP = 3


class PolicyDisposition(StrEnum):
    DENY = "deny"
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"


class ExecutionOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    DENIED = "denied"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    UNCERTAIN = "uncertain"
    POSTCONDITION_MISMATCH = "postcondition_mismatch"


class PostconditionStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class RollbackStatus(StrEnum):
    NOT_NEEDED = "not_needed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class ActionAuditEventType(StrEnum):
    BROKER_REJECTED = "broker_rejected"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_FINISHED = "execution_finished"


class ActorContext(DomainModel):
    """Authenticated origin. Client/model metadata must never construct this value."""

    host_id: Identifier
    session_id: Identifier
    device_id: Identifier
    interface: InteractionInterface
    assurance: AuthenticationAssurance
    authenticated_at: datetime | None = None
    capabilities: Annotated[tuple[Capability, ...], Field(max_length=64)] = ()

    @field_validator("authenticated_at")
    @classmethod
    def normalize_authenticated_at(cls, value: datetime | None) -> datetime | None:
        return _aware_utc(value, field_name="authenticated_at") if value is not None else None

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("actor capabilities must be distinct")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_authentication_shape(self) -> Self:
        if self.assurance is AuthenticationAssurance.UNAUTHENTICATED:
            if self.authenticated_at is not None:
                raise ValueError("unauthenticated actors cannot have an authentication timestamp")
        elif self.authenticated_at is None:
            raise ValueError("authenticated actors require an authentication timestamp")
        return self

    def same_identity(self, other: ActorContext) -> bool:
        return (
            self.host_id == other.host_id
            and self.session_id == other.session_id
            and self.device_id == other.device_id
        )

    def has_execution_authority_for(self, origin: ActorContext) -> bool:
        """Keep exact proposal authority across safe same-session process restarts."""
        return (
            self.same_identity(origin)
            and self.interface is origin.interface
            and self.assurance is not AuthenticationAssurance.UNAUTHENTICATED
            and self.assurance >= origin.assurance
            and set(origin.capabilities).issubset(self.capabilities)
        )


class ActionDefinition(DomainModel):
    """Broker metadata derived from one reviewed, registered tool definition."""

    tool: ToolDefinition
    supports_rollback: bool
    effect_may_outlive_cancellation: bool = False
    rollback_timeout_seconds: Annotated[float, Field(gt=0, le=30)] = 5.0

    @model_validator(mode="after")
    def validate_rollback_claim(self) -> Self:
        if self.tool.permission_level is PermissionLevel.LEVEL_0 and self.supports_rollback:
            raise ValueError("read-only actions cannot claim rollback")
        if self.effect_may_outlive_cancellation and self.tool.side_effect is ToolSideEffect.NONE:
            raise ValueError("side-effect-free actions cannot outlive cancellation")
        return self

    @property
    def action_id(self) -> str:
        return self.tool.name

    @property
    def version(self) -> str:
        return self.tool.version

    @property
    def dispatch_key(self) -> str:
        return f"{self.action_id}@{self.version}"


class CanonicalAction(DomainModel):
    """Fully normalized operation; changing any authority-bearing value invalidates it."""

    request_id: Identifier
    conversation_id: Identifier | None = None
    tool_call_id: Identifier | None = None
    action_id: ActionIdentifier
    action_version: ActionVersion
    actor: ActorContext
    normalized_arguments: dict[str, JsonValue]
    permission_level: PermissionLevel
    approval_rule: ApprovalRule
    policy_version: Identifier
    idempotency_key: Identifier
    human_effect: Annotated[str, Field(min_length=1, max_length=2_000)]
    recovery_limits: Annotated[str, Field(min_length=1, max_length=2_000)]
    precondition: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime
    expires_at: datetime
    fingerprint: Fingerprint

    @field_validator("normalized_arguments", "precondition", mode="before")
    @classmethod
    def normalize_json_fields(cls, value: object) -> object:
        normalized = canonicalize(value)
        if not isinstance(normalized, dict):
            raise TypeError("action arguments and preconditions must be JSON objects")
        return normalized

    @field_validator("created_at", "expires_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "timestamp")
        normalized = _aware_utc(value, field_name=field_name)
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_expiry_and_fingerprint(self) -> Self:
        _validate_ttl(self.created_at, self.expires_at, MAX_ACTION_TTL, "action")
        expected = sha256_fingerprint(self.fingerprint_payload())
        if not compare_digest(self.fingerprint, expected):
            raise ValueError("action fingerprint does not match canonical authority data")
        return self

    def fingerprint_payload(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "tool_call_id": self.tool_call_id,
            "action_id": self.action_id,
            "action_version": self.action_version,
            "actor": self.actor,
            "normalized_arguments": self.normalized_arguments,
            "permission_level": int(self.permission_level),
            "approval_rule": self.approval_rule,
            "policy_version": self.policy_version,
            "idempotency_key": self.idempotency_key,
            "human_effect": self.human_effect,
            "recovery_limits": self.recovery_limits,
            "precondition": self.precondition,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        action_id: str,
        action_version: str,
        actor: ActorContext,
        normalized_arguments: dict[str, JsonValue],
        permission_level: PermissionLevel,
        approval_rule: ApprovalRule,
        policy_version: str,
        idempotency_key: str,
        human_effect: str,
        recovery_limits: str,
        created_at: datetime,
        expires_at: datetime,
        conversation_id: str | None = None,
        tool_call_id: str | None = None,
        precondition: dict[str, JsonValue] | None = None,
    ) -> CanonicalAction:
        normalized_created_at = _aware_utc(created_at, field_name="created_at")
        normalized_expires_at = _aware_utc(expires_at, field_name="expires_at")
        assert normalized_created_at is not None
        assert normalized_expires_at is not None
        values: dict[str, object] = {
            "request_id": request_id,
            "conversation_id": conversation_id,
            "tool_call_id": tool_call_id,
            "action_id": action_id,
            "action_version": action_version,
            "actor": actor,
            "normalized_arguments": normalized_arguments,
            "permission_level": permission_level,
            "approval_rule": approval_rule,
            "policy_version": policy_version,
            "idempotency_key": idempotency_key,
            "human_effect": human_effect,
            "recovery_limits": recovery_limits,
            "precondition": precondition or {},
            "created_at": normalized_created_at,
            "expires_at": normalized_expires_at,
        }
        return cls.model_validate({**values, "fingerprint": sha256_fingerprint(values)})


class ActionPolicyDecision(DomainModel):
    disposition: PolicyDisposition
    permission_level: PermissionLevel
    policy_version: Identifier
    rule_id: Identifier
    reason: Annotated[str, Field(min_length=1, max_length=2_000)]

    @property
    def allowed(self) -> bool:
        return self.disposition is PolicyDisposition.ALLOW


class ApprovalRequest(DomainModel):
    approval_id: Identifier
    action: CanonicalAction
    requested_at: datetime
    expires_at: datetime

    @field_validator("requested_at", "expires_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime, info: object) -> datetime:
        normalized = _aware_utc(value, field_name=getattr(info, "field_name", "timestamp"))
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_expiry(self) -> Self:
        _validate_ttl(self.requested_at, self.expires_at, MAX_APPROVAL_TTL, "approval")
        if self.expires_at > self.action.expires_at:
            raise ValueError("approval cannot outlive its canonical action")
        return self


class ApprovalDecision(DomainModel):
    approval_id: Identifier
    action_fingerprint: Fingerprint
    approver: ActorContext
    approved: bool
    decided_at: datetime
    reason: Annotated[str, Field(max_length=2_000)] | None = None

    @field_validator("decided_at")
    @classmethod
    def normalize_decided_at(cls, value: datetime) -> datetime:
        normalized = _aware_utc(value, field_name="decided_at")
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def require_denial_reason(self) -> Self:
        if not self.approved and not (self.reason and self.reason.strip()):
            raise ValueError("denied approvals require a reason")
        return self


class ApprovalGrant(DomainModel):
    grant_id: Identifier
    approval_id: Identifier
    action: CanonicalAction
    approved_by: ActorContext
    issued_at: datetime
    expires_at: datetime
    nonce: Identifier
    grant_fingerprint: Fingerprint

    @field_validator("issued_at", "expires_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime, info: object) -> datetime:
        normalized = _aware_utc(value, field_name=getattr(info, "field_name", "timestamp"))
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_grant(self) -> Self:
        _validate_ttl(self.issued_at, self.expires_at, MAX_GRANT_TTL, "grant")
        if self.expires_at > self.action.expires_at:
            raise ValueError("grant cannot outlive its canonical action")
        if self.approved_by.host_id != self.action.actor.host_id:
            raise ValueError("approver and action actor must belong to the same host")
        expected = sha256_fingerprint(self.fingerprint_payload())
        if not compare_digest(self.grant_fingerprint, expected):
            raise ValueError("grant fingerprint does not match exact approval data")
        return self

    def fingerprint_payload(self) -> dict[str, object]:
        return {
            "grant_id": self.grant_id,
            "approval_id": self.approval_id,
            "action_fingerprint": self.action.fingerprint,
            "approved_by": self.approved_by,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }

    @classmethod
    def create(
        cls,
        *,
        grant_id: str,
        approval_id: str,
        action: CanonicalAction,
        approved_by: ActorContext,
        issued_at: datetime,
        expires_at: datetime,
        nonce: str,
    ) -> ApprovalGrant:
        normalized_issued_at = _aware_utc(issued_at, field_name="issued_at")
        normalized_expires_at = _aware_utc(expires_at, field_name="expires_at")
        assert normalized_issued_at is not None
        assert normalized_expires_at is not None
        values: dict[str, object] = {
            "grant_id": grant_id,
            "approval_id": approval_id,
            "action": action,
            "approved_by": approved_by,
            "issued_at": normalized_issued_at,
            "expires_at": normalized_expires_at,
            "nonce": nonce,
        }
        payload = {
            "grant_id": grant_id,
            "approval_id": approval_id,
            "action_fingerprint": action.fingerprint,
            "approved_by": approved_by,
            "issued_at": normalized_issued_at,
            "expires_at": normalized_expires_at,
            "nonce": nonce,
        }
        return cls.model_validate({**values, "grant_fingerprint": sha256_fingerprint(payload)})


class ActionEffect(DomainModel):
    result: JsonValue
    rollback_context: JsonValue | None = None


class PostconditionEvidence(DomainModel):
    status: PostconditionStatus
    summary: Annotated[str, Field(min_length=1, max_length=2_000)]
    detail: dict[str, JsonValue] = Field(default_factory=dict)


class RollbackReceipt(DomainModel):
    status: RollbackStatus
    summary: Annotated[str, Field(min_length=1, max_length=2_000)]
    detail: dict[str, JsonValue] = Field(default_factory=dict)


class ExecutionReceipt(DomainModel):
    receipt_id: Identifier
    grant_id: Identifier
    request_id: Identifier
    action_id: ActionIdentifier
    action_version: ActionVersion
    action_fingerprint: Fingerprint
    actor: ActorContext
    policy_version: Identifier
    idempotency_key: Identifier
    outcome: ExecutionOutcome
    started_at: datetime
    finished_at: datetime
    result: JsonValue | None = None
    result_bytes: Annotated[int, Field(ge=0)] = 0
    postcondition: PostconditionEvidence
    rollback: RollbackReceipt
    error_code: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    error_message: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime, info: object) -> datetime:
        normalized = _aware_utc(value, field_name=getattr(info, "field_name", "timestamp"))
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("execution finish must not precede start")
        if self.outcome is ExecutionOutcome.SUCCEEDED:
            if self.postcondition.status is not PostconditionStatus.PASSED:
                raise ValueError("successful execution requires a passed postcondition")
            if self.error_code is not None or self.error_message is not None:
                raise ValueError("successful execution cannot contain an error")
        elif self.error_code is None or self.error_message is None:
            raise ValueError("non-success execution requires a normalized error")
        return self


class ActionAuditEvent(DomainModel):
    event_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    type: ActionAuditEventType
    request_id: Identifier
    grant_id: Identifier
    action_id: ActionIdentifier
    action_version: ActionVersion
    action_fingerprint: Fingerprint
    occurred_at: datetime
    outcome: ExecutionOutcome | None = None
    error_code: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    detail: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        normalized = _aware_utc(value, field_name="occurred_at")
        assert normalized is not None
        return normalized


def _aware_utc(value: datetime | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _validate_ttl(start: datetime, end: datetime, maximum: timedelta, label: str) -> None:
    if end <= start:
        raise ValueError(f"{label} expiry must follow creation")
    if end - start > maximum:
        raise ValueError(f"{label} TTL exceeds {maximum.total_seconds():.0f} seconds")
