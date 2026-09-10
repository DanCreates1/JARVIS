"""Owned Phase 8A remote identity contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$"
_BASE64URL_PATTERN = r"^[A-Za-z0-9_-]+$"


class DeviceType(StrEnum):
    PHONE = "phone"
    BROWSER = "browser"
    LAPTOP = "laptop"
    WEARABLE = "wearable"
    SERVICE = "service"


class DeviceState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class RemoteScope(StrEnum):
    IDENTITY_READ = "identity.read"
    EVENTS_READ = "events.read"
    SESSION_REVOKE = "session.revoke"
    KEY_ROTATE = "key.rotate"
    BROWSER_SESSION = "browser.session"
    APPROVAL_REVIEW = "approval.review"
    CLIENT_CHAT = "client.chat"
    CLIENT_TASKS_READ = "client.tasks.read"
    CLIENT_STATUS_READ = "client.status.read"


class RemoteSessionKind(StrEnum):
    SIGNED_API = "signed_api"
    BROWSER = "browser"


class RemoteAuditOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    SUCCEEDED = "succeeded"


class EnrollmentTicket(BaseModel):
    """One-time enrollment material returned only by a trusted local interface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=_IDENTIFIER_PATTERN)
    challenge: str = Field(min_length=43, max_length=128, pattern=_BASE64URL_PATTERN)
    host_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=100)
    device_type: DeviceType
    approved_scopes: tuple[RemoteScope, ...] = Field(min_length=1, max_length=16)
    risk_ceiling: int = Field(ge=0, le=2)
    expires_at: datetime

    @field_validator("approved_scopes")
    @classmethod
    def unique_scopes(cls, value: tuple[RemoteScope, ...]) -> tuple[RemoteScope, ...]:
        if len(value) != len(set(value)):
            raise ValueError("approved scopes must be unique")
        return tuple(sorted(value, key=str))


class EnrollmentCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enrollment_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    challenge: str = Field(min_length=43, max_length=128, pattern=_BASE64URL_PATTERN)
    public_key: str = Field(min_length=43, max_length=43, pattern=_BASE64URL_PATTERN)
    proof_signature: str = Field(min_length=86, max_length=86, pattern=_BASE64URL_PATTERN)
    protocol_version: str = Field(default="1", pattern=r"^1$")


class DeviceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=_IDENTIFIER_PATTERN)
    host_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=100)
    device_type: DeviceType
    key_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    key_version: int = Field(ge=1)
    approved_scopes: tuple[RemoteScope, ...]
    risk_ceiling: int = Field(ge=0, le=2)
    protocol_version: str = Field(pattern=r"^1$")
    state: DeviceState
    enrolled_at: datetime
    credential_expires_at: datetime
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_scopes: tuple[RemoteScope, ...] = Field(min_length=1, max_length=16)
    audience: str = Field(default="jarvis-api", pattern=r"^jarvis-api$")

    @field_validator("requested_scopes")
    @classmethod
    def unique_scopes(cls, value: tuple[RemoteScope, ...]) -> tuple[RemoteScope, ...]:
        if len(value) != len(set(value)):
            raise ValueError("requested scopes must be unique")
        return tuple(sorted(value, key=str))


class SessionCredential(BaseModel):
    """Opaque bearer material. The plaintext token is returned once and never persisted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    token: str = Field(min_length=43, max_length=128, pattern=_BASE64URL_PATTERN)
    token_type: str = Field(default="Bearer", pattern=r"^Bearer$")
    device_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    key_version: int = Field(ge=1)
    audience: str = Field(pattern=r"^jarvis-api$")
    scopes: tuple[RemoteScope, ...]
    expires_at: datetime


class BrowserSessionCredential(BaseModel):
    """One-time browser secrets. Only their SHA-256 digests are persisted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    cookie_token: str = Field(min_length=43, max_length=128, pattern=_BASE64URL_PATTERN)
    csrf_token: str = Field(min_length=43, max_length=128, pattern=_BASE64URL_PATTERN)
    device_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    key_version: int = Field(ge=1)
    audience: str = Field(pattern=r"^jarvis-api$")
    scopes: tuple[RemoteScope, ...]
    expires_at: datetime


class KeyRotationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    new_public_key: str = Field(min_length=43, max_length=43, pattern=_BASE64URL_PATTERN)
    new_key_proof: str = Field(min_length=86, max_length=86, pattern=_BASE64URL_PATTERN)


class RemoteIdentityContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    device_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    session_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    key_version: int = Field(ge=1)
    audience: str = Field(pattern=r"^jarvis-api$")
    scopes: frozenset[RemoteScope]
    session_kind: RemoteSessionKind = RemoteSessionKind.SIGNED_API
    risk_ceiling: int = Field(default=0, ge=0, le=2)
    authenticated_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("authenticated_at", "expires_at")
    @classmethod
    def require_aware_context_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("remote context timestamps must include a timezone")
        return value.astimezone(UTC)


class RemoteAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1)
    id: str = Field(pattern=_IDENTIFIER_PATTERN)
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_.]{0,63}$")
    outcome: RemoteAuditOutcome
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_.]{0,63}$")
    device_id: str | None = Field(default=None, pattern=_IDENTIFIER_PATTERN)
    session_id: str | None = Field(default=None, pattern=_IDENTIFIER_PATTERN)
    enrollment_id: str | None = Field(default=None, pattern=_IDENTIFIER_PATTERN)
    created_at: datetime
