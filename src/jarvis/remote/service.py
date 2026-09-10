"""Phase 8A device enrollment, session, rotation, and request authentication."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from jarvis.remote.models import (
    DeviceRecord,
    DeviceState,
    DeviceType,
    EnrollmentCompletion,
    EnrollmentTicket,
    KeyRotationRequest,
    RemoteAuditEvent,
    RemoteIdentityContext,
    RemoteScope,
    SessionCredential,
    SessionRequest,
)
from jarvis.remote.signing import (
    REQUEST_AUDIENCE,
    SignedRequest,
    build_enrollment_proof,
    build_rotation_proof,
    canonical_request,
    decode_base64url,
)
from jarvis.remote.sqlite_store import SQLiteRemoteIdentityStore, StoredDevice

Clock = Callable[[], datetime]


class RemoteAuthenticationError(RuntimeError):
    def __init__(self, code: str = "authentication_failed") -> None:
        super().__init__("remote request authentication failed")
        self.code = code


class RemoteStateError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RemoteIdentityService:
    """Own remote authority. Model/chat code receives no lifecycle methods."""

    def __init__(
        self,
        store: SQLiteRemoteIdentityStore,
        *,
        enrollment_ttl: timedelta = timedelta(minutes=5),
        session_ttl: timedelta = timedelta(minutes=15),
        credential_ttl: timedelta = timedelta(days=365),
        allowed_clock_skew: timedelta = timedelta(seconds=60),
        clock: Clock | None = None,
    ) -> None:
        if not timedelta(seconds=30) <= enrollment_ttl <= timedelta(minutes=15):
            raise ValueError("enrollment TTL must be between 30 seconds and 15 minutes")
        if not timedelta(minutes=1) <= session_ttl <= timedelta(hours=1):
            raise ValueError("session TTL must be between 1 minute and 1 hour")
        if not timedelta(days=1) <= credential_ttl <= timedelta(days=730):
            raise ValueError("credential TTL must be between 1 and 730 days")
        if not timedelta(seconds=5) <= allowed_clock_skew <= timedelta(minutes=5):
            raise ValueError("clock skew must be between 5 seconds and 5 minutes")
        self._store = store
        self._enrollment_ttl = enrollment_ttl
        self._session_ttl = session_ttl
        self._credential_ttl = credential_ttl
        self._allowed_clock_skew = allowed_clock_skew
        self._clock = clock or (lambda: datetime.now(UTC))
        self._operation_lock = asyncio.Lock()

    async def create_enrollment(
        self,
        *,
        host_id: str,
        display_name: str,
        device_type: DeviceType,
        approved_scopes: tuple[RemoteScope, ...],
        risk_ceiling: int = 0,
    ) -> EnrollmentTicket:
        """Trusted-local enrollment start. Never expose this through remote routes."""
        now = self._now()
        challenge = secrets.token_urlsafe(32)
        ticket = EnrollmentTicket(
            id=f"enrollment:{uuid4()}",
            challenge=challenge,
            host_id=host_id,
            display_name=display_name.strip(),
            device_type=device_type,
            approved_scopes=approved_scopes,
            risk_ceiling=risk_ceiling,
            expires_at=now + self._enrollment_ttl,
        )
        await self._store.create_enrollment(
            ticket,
            challenge_sha256=_sha256_hex(challenge.encode("ascii")),
            created_at=now,
        )
        return ticket

    async def complete_enrollment(self, completion: EnrollmentCompletion) -> DeviceRecord:
        async with self._operation_lock:
            now = self._now()
            enrollment = await self._store.get_enrollment(completion.enrollment_id)
            if enrollment is None:
                raise RemoteAuthenticationError("invalid_enrollment")
            if enrollment.consumed_at is not None:
                await self._store.append_denial(
                    reason_code="enrollment_replayed",
                    enrollment_id=enrollment.id,
                    created_at=now,
                )
                raise RemoteAuthenticationError("invalid_enrollment")
            if enrollment.expires_at <= now:
                await self._store.append_denial(
                    reason_code="enrollment_expired",
                    enrollment_id=enrollment.id,
                    created_at=now,
                )
                raise RemoteAuthenticationError("invalid_enrollment")
            supplied_hash = _sha256_hex(completion.challenge.encode("ascii"))
            if not secrets.compare_digest(supplied_hash, enrollment.challenge_sha256):
                await self._store.append_denial(
                    reason_code="enrollment_challenge_mismatch",
                    enrollment_id=enrollment.id,
                    created_at=now,
                )
                raise RemoteAuthenticationError("invalid_enrollment")
            try:
                public_key_bytes = decode_base64url(completion.public_key, expected_bytes=32)
                signature = decode_base64url(completion.proof_signature, expected_bytes=64)
                public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
                public_key.verify(
                    signature,
                    build_enrollment_proof(
                        enrollment_id=completion.enrollment_id,
                        challenge=completion.challenge,
                        public_key=completion.public_key,
                        protocol_version=completion.protocol_version,
                    ),
                )
            except (InvalidSignature, ValueError):
                await self._store.append_denial(
                    reason_code="enrollment_proof_invalid",
                    enrollment_id=enrollment.id,
                    created_at=now,
                )
                raise RemoteAuthenticationError("invalid_enrollment") from None
            record = await self._store.complete_enrollment(
                enrollment=enrollment,
                device_id=f"device:{uuid4()}",
                public_key=completion.public_key,
                key_fingerprint=_sha256_hex(public_key_bytes),
                protocol_version=completion.protocol_version,
                credential_expires_at=now + self._credential_ttl,
                completed_at=now,
            )
            if record is None:
                await self._store.append_denial(
                    reason_code="enrollment_credential_conflict",
                    enrollment_id=enrollment.id,
                    created_at=now,
                )
                raise RemoteAuthenticationError("invalid_enrollment")
            return record

    async def create_session(
        self,
        *,
        request: SignedRequest,
        signature: str,
        payload: SessionRequest,
    ) -> SessionCredential:
        if request.session_token is not None:
            raise RemoteAuthenticationError("unexpected_session_token")
        async with self._operation_lock:
            device = await self._authenticate_device_signature(
                request=request,
                signature=signature,
                session_id=None,
            )
            requested = frozenset(payload.requested_scopes)
            approved = frozenset(device.record.approved_scopes)
            if not requested.issubset(approved):
                await self._store.append_denial(
                    reason_code="scope_expansion",
                    device_id=device.record.id,
                    created_at=self._now(),
                )
                raise RemoteStateError("scope_expansion", "requested scope exceeds device scope")
            now = self._now()
            token = secrets.token_urlsafe(32)
            session_id = f"session:{uuid4()}"
            scopes = tuple(sorted(requested, key=str))
            expires_at = min(now + self._session_ttl, device.record.credential_expires_at)
            try:
                await self._store.create_session(
                    session_id=session_id,
                    token_sha256=_sha256_hex(token.encode("ascii")),
                    device=device.record,
                    audience=payload.audience,
                    scopes=scopes,
                    created_at=now,
                    expires_at=expires_at,
                )
            except RuntimeError:
                raise RemoteAuthenticationError("device_changed") from None
            return SessionCredential(
                session_id=session_id,
                token=token,
                device_id=device.record.id,
                key_version=device.record.key_version,
                audience=payload.audience,
                scopes=scopes,
                expires_at=expires_at,
            )

    async def authenticate_request(
        self,
        *,
        request: SignedRequest,
        signature: str,
        required_scope: RemoteScope | None = None,
    ) -> RemoteIdentityContext:
        if request.session_token is None:
            raise RemoteAuthenticationError("missing_session_token")
        async with self._operation_lock:
            now = self._now()
            token_sha256 = _sha256_hex(request.session_token.encode("ascii"))
            session = await self._store.get_session_by_token_sha256(token_sha256)
            if session is None:
                raise RemoteAuthenticationError("invalid_session")
            if session.device_id != request.device_id:
                await self._deny(
                    "session_device_mismatch",
                    device_id=session.device_id,
                    session_id=session.id,
                    created_at=now,
                )
            if session.revoked_at is not None:
                await self._deny(
                    "session_revoked",
                    device_id=session.device_id,
                    session_id=session.id,
                    created_at=now,
                )
            if session.expires_at <= now:
                await self._deny(
                    "session_expired",
                    device_id=session.device_id,
                    session_id=session.id,
                    created_at=now,
                )
            if session.audience != request.audience or request.audience != REQUEST_AUDIENCE:
                await self._deny(
                    "wrong_audience",
                    device_id=session.device_id,
                    session_id=session.id,
                    created_at=now,
                )
            if session.key_version != request.key_version:
                await self._deny(
                    "session_key_version_mismatch",
                    device_id=session.device_id,
                    session_id=session.id,
                    created_at=now,
                )
            device = await self._authenticate_device_signature(
                request=request,
                signature=signature,
                session_id=session.id,
            )
            session_scopes = frozenset(session.scopes)
            effective_scopes = session_scopes.intersection(device.record.approved_scopes)
            if required_scope is not None and required_scope not in effective_scopes:
                await self._store.append_denial(
                    reason_code="scope_denied",
                    device_id=device.record.id,
                    session_id=session.id,
                    created_at=now,
                )
                raise RemoteStateError("scope_denied", "remote scope is required")
            return RemoteIdentityContext(
                host_id=device.record.host_id,
                device_id=device.record.id,
                session_id=session.id,
                key_version=device.record.key_version,
                audience=session.audience,
                scopes=frozenset(effective_scopes),
            )

    async def rotate_key(
        self,
        *,
        context: RemoteIdentityContext,
        payload: KeyRotationRequest,
    ) -> DeviceRecord:
        if RemoteScope.KEY_ROTATE not in context.scopes:
            raise RemoteStateError("scope_denied", "key rotation scope is required")
        async with self._operation_lock:
            stored = await self._store.get_device(context.device_id)
            if stored is None or stored.record.key_version != context.key_version:
                raise RemoteAuthenticationError("device_changed")
            try:
                new_key_bytes = decode_base64url(payload.new_public_key, expected_bytes=32)
                new_key = Ed25519PublicKey.from_public_bytes(new_key_bytes)
                new_key.verify(
                    decode_base64url(payload.new_key_proof, expected_bytes=64),
                    build_rotation_proof(
                        device_id=context.device_id,
                        current_key_version=context.key_version,
                        new_public_key=payload.new_public_key,
                    ),
                )
            except (InvalidSignature, ValueError):
                raise RemoteAuthenticationError("new_key_proof_invalid") from None
            fingerprint = _sha256_hex(new_key_bytes)
            if secrets.compare_digest(fingerprint, stored.record.key_fingerprint):
                raise RemoteStateError("key_unchanged", "new key must differ from current key")
            now = self._now()
            record = await self._store.rotate_device_key(
                device_id=context.device_id,
                expected_key_version=context.key_version,
                new_public_key=payload.new_public_key,
                new_fingerprint=fingerprint,
                rotated_at=now,
                credential_expires_at=now + self._credential_ttl,
            )
            if record is None:
                await self._store.append_denial(
                    reason_code="key_rotation_conflict",
                    device_id=context.device_id,
                    session_id=context.session_id,
                    created_at=now,
                )
                raise RemoteAuthenticationError("device_changed")
            return record

    async def revoke_current_session(self, context: RemoteIdentityContext) -> bool:
        return await self._store.revoke_session(
            session_id=context.session_id,
            device_id=context.device_id,
            revoked_at=self._now(),
        )

    async def revoke_device(self, *, host_id: str, device_id: str) -> bool:
        """Trusted-local lost-device recovery. Never expose through remote routes in 8A."""
        return await self._store.revoke_device(
            device_id=device_id,
            host_id=host_id,
            revoked_at=self._now(),
        )

    async def list_devices(self, *, host_id: str) -> tuple[DeviceRecord, ...]:
        return await self._store.list_devices(host_id=host_id)

    async def list_device_events(
        self,
        *,
        context: RemoteIdentityContext,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[RemoteAuditEvent, ...]:
        if RemoteScope.EVENTS_READ not in context.scopes:
            raise RemoteStateError("scope_denied", "event-read scope is required")
        return await self._store.list_audit_events(
            device_id=context.device_id,
            after_sequence=after_sequence,
            limit=limit,
        )

    async def get_current_device(self, context: RemoteIdentityContext) -> DeviceRecord:
        if RemoteScope.IDENTITY_READ not in context.scopes:
            raise RemoteStateError("scope_denied", "identity-read scope is required")
        stored = await self._store.get_device(context.device_id)
        if stored is None or stored.record.state is not DeviceState.ACTIVE:
            raise RemoteAuthenticationError("device_unavailable")
        return stored.record

    async def _authenticate_device_signature(
        self,
        *,
        request: SignedRequest,
        signature: str,
        session_id: str | None,
    ) -> StoredDevice:
        now = self._now()
        device = await self._store.get_device(request.device_id)
        if device is None:
            raise RemoteAuthenticationError("unknown_device")
        record = device.record
        if record.state is not DeviceState.ACTIVE:
            await self._deny(
                "device_revoked",
                device_id=record.id,
                session_id=session_id,
                created_at=now,
            )
        if record.credential_expires_at <= now:
            await self._deny(
                "device_credential_expired",
                device_id=record.id,
                session_id=session_id,
                created_at=now,
            )
        if request.key_version != record.key_version:
            await self._deny(
                "wrong_key_version",
                device_id=record.id,
                session_id=session_id,
                created_at=now,
            )
        skew = abs(now - request.timestamp.astimezone(UTC))
        if skew > self._allowed_clock_skew:
            await self._deny(
                "timestamp_outside_window",
                device_id=record.id,
                session_id=session_id,
                created_at=now,
            )
        try:
            Ed25519PublicKey.from_public_bytes(
                decode_base64url(device.public_key, expected_bytes=32)
            ).verify(
                decode_base64url(signature, expected_bytes=64),
                canonical_request(request),
            )
        except (InvalidSignature, ValueError):
            await self._deny(
                "invalid_signature",
                device_id=record.id,
                session_id=session_id,
                created_at=now,
            )
        consumed = await self._store.consume_nonce(
            device_id=record.id,
            session_id=session_id,
            nonce=request.nonce,
            seen_at=now,
            expires_at=now + self._allowed_clock_skew * 2,
        )
        if not consumed:
            raise RemoteAuthenticationError("replayed_nonce")
        return device

    async def _deny(
        self,
        reason_code: str,
        *,
        created_at: datetime,
        device_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        await self._store.append_denial(
            reason_code=reason_code,
            device_id=device_id,
            session_id=session_id,
            created_at=created_at,
        )
        raise RemoteAuthenticationError(reason_code)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("remote identity clock returned a naive datetime")
        return value.astimezone(UTC)


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
