"""Phase 8 remote identity, enrollment, and request-authentication boundary."""

from jarvis.remote.browser import (
    BrowserOriginError,
    BrowserOriginPolicy,
    FixedWindowRateLimiter,
    RateLimitDecision,
)
from jarvis.remote.models import (
    BrowserSessionCredential,
    DeviceRecord,
    DeviceState,
    DeviceType,
    EnrollmentCompletion,
    EnrollmentTicket,
    KeyRotationRequest,
    RemoteAuditEvent,
    RemoteAuditOutcome,
    RemoteIdentityContext,
    RemoteScope,
    RemoteSessionKind,
    SessionCredential,
    SessionRequest,
)
from jarvis.remote.service import (
    RemoteAuthenticationError,
    RemoteIdentityService,
    RemoteStateError,
)
from jarvis.remote.signing import (
    REQUEST_AUDIENCE,
    SIGNATURE_HEADERS,
    SignedRequest,
    build_enrollment_proof,
    build_rotation_proof,
    canonical_request,
    encode_base64url,
)
from jarvis.remote.sqlite_store import SQLiteRemoteIdentityStore

__all__ = [
    "REQUEST_AUDIENCE",
    "SIGNATURE_HEADERS",
    "BrowserOriginError",
    "BrowserOriginPolicy",
    "BrowserSessionCredential",
    "DeviceRecord",
    "DeviceState",
    "DeviceType",
    "EnrollmentCompletion",
    "EnrollmentTicket",
    "FixedWindowRateLimiter",
    "KeyRotationRequest",
    "RateLimitDecision",
    "RemoteAuditEvent",
    "RemoteAuditOutcome",
    "RemoteAuthenticationError",
    "RemoteIdentityContext",
    "RemoteIdentityService",
    "RemoteScope",
    "RemoteSessionKind",
    "RemoteStateError",
    "SQLiteRemoteIdentityStore",
    "SessionCredential",
    "SessionRequest",
    "SignedRequest",
    "build_enrollment_proof",
    "build_rotation_proof",
    "canonical_request",
    "encode_base64url",
]
