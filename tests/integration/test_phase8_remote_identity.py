from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jarvis.remote import (
    DeviceState,
    DeviceType,
    EnrollmentCompletion,
    KeyRotationRequest,
    RemoteAuthenticationError,
    RemoteIdentityService,
    RemoteScope,
    RemoteStateError,
    SessionRequest,
    SignedRequest,
    SQLiteRemoteIdentityStore,
    build_enrollment_proof,
    build_rotation_proof,
    canonical_request,
    encode_base64url,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 9, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def _public_key(private_key: Ed25519PrivateKey) -> str:
    return encode_base64url(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def _signed_request(
    *,
    private_key: Ed25519PrivateKey,
    device_id: str,
    key_version: int,
    timestamp: datetime,
    nonce: str,
    body: bytes = b"{}",
    path: str = "/api/v1/identity",
    query: str = "",
    session_token: str | None = None,
    audience: str = "jarvis-api",
) -> tuple[SignedRequest, str]:
    request = SignedRequest(
        method="POST" if body != b"" else "GET",
        authority="localhost:8765",
        path=path,
        query=query,
        body=body,
        device_id=device_id,
        key_version=key_version,
        audience=audience,
        timestamp=timestamp,
        nonce=nonce,
        session_token=session_token,
    )
    return request, encode_base64url(private_key.sign(canonical_request(request)))


async def _enroll(
    service: RemoteIdentityService,
    private_key: Ed25519PrivateKey,
    *,
    scopes: tuple[RemoteScope, ...] = tuple(RemoteScope),
) -> tuple[str, str]:
    ticket = await service.create_enrollment(
        host_id="host:test",
        display_name="Synthetic phone",
        device_type=DeviceType.PHONE,
        approved_scopes=scopes,
        risk_ceiling=1,
    )
    public_key = _public_key(private_key)
    proof = private_key.sign(
        build_enrollment_proof(
            enrollment_id=ticket.id,
            challenge=ticket.challenge,
            public_key=public_key,
            protocol_version="1",
        )
    )
    device = await service.complete_enrollment(
        EnrollmentCompletion(
            enrollment_id=ticket.id,
            challenge=ticket.challenge,
            public_key=public_key,
            proof_signature=encode_base64url(proof),
        )
    )
    return device.id, ticket.challenge


async def _session(
    service: RemoteIdentityService,
    private_key: Ed25519PrivateKey,
    *,
    device_id: str,
    key_version: int,
    now: datetime,
    nonce: str,
    scopes: tuple[RemoteScope, ...],
):
    payload = SessionRequest(requested_scopes=scopes)
    body = payload.model_dump_json().encode()
    request, signature = _signed_request(
        private_key=private_key,
        device_id=device_id,
        key_version=key_version,
        timestamp=now,
        nonce=nonce,
        body=body,
        path="/api/v1/sessions",
    )
    return await service.create_session(request=request, signature=signature, payload=payload)


@pytest.mark.asyncio
async def test_enrollment_session_replay_restart_rotation_and_revocation(tmp_path: Path) -> None:
    database = tmp_path / "remote.db"
    clock = FakeClock()
    store = SQLiteRemoteIdentityStore(database)
    await store.initialize()
    service = RemoteIdentityService(store, clock=clock)
    old_key = Ed25519PrivateKey.generate()

    ticket = await service.create_enrollment(
        host_id="host:test",
        display_name="Synthetic phone",
        device_type=DeviceType.PHONE,
        approved_scopes=tuple(RemoteScope),
        risk_ceiling=1,
    )
    public_key = _public_key(old_key)
    completion = EnrollmentCompletion(
        enrollment_id=ticket.id,
        challenge=ticket.challenge,
        public_key=public_key,
        proof_signature=encode_base64url(
            old_key.sign(
                build_enrollment_proof(
                    enrollment_id=ticket.id,
                    challenge=ticket.challenge,
                    public_key=public_key,
                    protocol_version="1",
                )
            )
        ),
    )
    device = await service.complete_enrollment(completion)
    assert device.state is DeviceState.ACTIVE
    with pytest.raises(RemoteAuthenticationError):
        await service.complete_enrollment(completion)

    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            "SELECT challenge_sha256 FROM remote_enrollments WHERE id = ?", (ticket.id,)
        ).fetchone()
        assert stored is not None and stored[0] != ticket.challenge and len(stored[0]) == 64

    scopes = (
        RemoteScope.IDENTITY_READ,
        RemoteScope.EVENTS_READ,
        RemoteScope.SESSION_REVOKE,
        RemoteScope.KEY_ROTATE,
    )
    session = await _session(
        service,
        old_key,
        device_id=device.id,
        key_version=1,
        now=clock.now,
        nonce="A" * 22,
        scopes=scopes,
    )
    with sqlite3.connect(database) as connection:
        persisted = connection.execute(
            "SELECT token_sha256 FROM remote_sessions WHERE id = ?", (session.session_id,)
        ).fetchone()
        assert persisted is not None and persisted[0] != session.token and len(persisted[0]) == 64

    request, signature = _signed_request(
        private_key=old_key,
        device_id=device.id,
        key_version=1,
        timestamp=clock.now,
        nonce="B" * 22,
        body=b"",
        session_token=session.token,
    )
    context = await service.authenticate_request(
        request=request,
        signature=signature,
        required_scope=RemoteScope.IDENTITY_READ,
    )
    assert context.device_id == device.id
    with pytest.raises(RemoteAuthenticationError) as replay:
        await service.authenticate_request(request=request, signature=signature)
    assert replay.value.code == "replayed_nonce"

    await store.close()
    reopened_store = SQLiteRemoteIdentityStore(database)
    await reopened_store.initialize()
    reopened = RemoteIdentityService(reopened_store, clock=clock)
    with pytest.raises(RemoteAuthenticationError) as restart_replay:
        await reopened.authenticate_request(request=request, signature=signature)
    assert restart_replay.value.code == "replayed_nonce"

    new_key = Ed25519PrivateKey.generate()
    new_public_key = _public_key(new_key)
    rotated = await reopened.rotate_key(
        context=context,
        payload=KeyRotationRequest(
            new_public_key=new_public_key,
            new_key_proof=encode_base64url(
                new_key.sign(
                    build_rotation_proof(
                        device_id=device.id,
                        current_key_version=1,
                        new_public_key=new_public_key,
                    )
                )
            ),
        ),
    )
    assert rotated.key_version == 2
    stale, stale_signature = _signed_request(
        private_key=old_key,
        device_id=device.id,
        key_version=1,
        timestamp=clock.now,
        nonce="C" * 22,
        body=b"",
        session_token=session.token,
    )
    with pytest.raises(RemoteAuthenticationError):
        await reopened.authenticate_request(request=stale, signature=stale_signature)

    new_session = await _session(
        reopened,
        new_key,
        device_id=device.id,
        key_version=2,
        now=clock.now,
        nonce="D" * 22,
        scopes=(RemoteScope.IDENTITY_READ,),
    )
    assert await reopened.revoke_device(host_id="host:test", device_id=device.id)
    revoked, revoked_signature = _signed_request(
        private_key=new_key,
        device_id=device.id,
        key_version=2,
        timestamp=clock.now,
        nonce="E" * 22,
        body=b"",
        session_token=new_session.token,
    )
    with pytest.raises(RemoteAuthenticationError):
        await reopened.authenticate_request(request=revoked, signature=revoked_signature)
    events = await reopened_store.list_audit_events(device_id=device.id, limit=100)
    assert {event.event_type for event in events} >= {
        "enrollment.completed",
        "session.created",
        "device.key_rotated",
        "device.revoked",
        "request.denied",
    }
    await reopened_store.close()


@pytest.mark.asyncio
async def test_scope_expiry_skew_and_atomic_concurrent_replay_fail_closed(tmp_path: Path) -> None:
    clock = FakeClock()
    store = SQLiteRemoteIdentityStore(tmp_path / "abuse.db")
    await store.initialize()
    service = RemoteIdentityService(
        store,
        session_ttl=timedelta(minutes=1),
        allowed_clock_skew=timedelta(seconds=10),
        clock=clock,
    )
    key = Ed25519PrivateKey.generate()
    device_id, _ = await _enroll(
        service,
        key,
        scopes=(RemoteScope.IDENTITY_READ, RemoteScope.EVENTS_READ),
    )
    with pytest.raises(RemoteStateError) as expansion:
        await _session(
            service,
            key,
            device_id=device_id,
            key_version=1,
            now=clock.now,
            nonce="F" * 22,
            scopes=(RemoteScope.KEY_ROTATE,),
        )
    assert expansion.value.code == "scope_expansion"
    session = await _session(
        service,
        key,
        device_id=device_id,
        key_version=1,
        now=clock.now,
        nonce="G" * 22,
        scopes=(RemoteScope.IDENTITY_READ,),
    )
    request, signature = _signed_request(
        private_key=key,
        device_id=device_id,
        key_version=1,
        timestamp=clock.now,
        nonce="H" * 22,
        body=b"",
        session_token=session.token,
    )
    results = await asyncio.gather(
        *(service.authenticate_request(request=request, signature=signature) for _ in range(20)),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(isinstance(result, RemoteAuthenticationError) for result in results) == 19

    outside = replace(request, nonce="I" * 22, timestamp=clock.now - timedelta(seconds=11))
    outside_signature = encode_base64url(key.sign(canonical_request(outside)))
    with pytest.raises(RemoteAuthenticationError) as skew:
        await service.authenticate_request(request=outside, signature=outside_signature)
    assert skew.value.code == "timestamp_outside_window"

    fresh = replace(request, nonce="J" * 22)
    fresh_signature = encode_base64url(key.sign(canonical_request(fresh)))
    with pytest.raises(RemoteStateError) as scope:
        context = await service.authenticate_request(request=fresh, signature=fresh_signature)
        await service.list_device_events(context=context)
    assert scope.value.code == "scope_denied"

    clock.advance(timedelta(minutes=1, microseconds=1))
    expired = replace(request, nonce="K" * 22, timestamp=clock.now)
    expired_signature = encode_base64url(key.sign(canonical_request(expired)))
    with pytest.raises(RemoteAuthenticationError) as expiry:
        await service.authenticate_request(request=expired, signature=expired_signature)
    assert expiry.value.code == "session_expired"
    await store.close()


@pytest.mark.asyncio
async def test_invalid_enrollment_proof_and_challenge_leave_no_device(tmp_path: Path) -> None:
    clock = FakeClock()
    store = SQLiteRemoteIdentityStore(tmp_path / "enrollment-denial.db")
    await store.initialize()
    service = RemoteIdentityService(store, clock=clock)
    key = Ed25519PrivateKey.generate()
    ticket = await service.create_enrollment(
        host_id="host:test",
        display_name="Phone",
        device_type=DeviceType.PHONE,
        approved_scopes=(RemoteScope.IDENTITY_READ,),
    )
    public_key = _public_key(key)
    invalid = EnrollmentCompletion(
        enrollment_id=ticket.id,
        challenge="Z" * 43,
        public_key=public_key,
        proof_signature=encode_base64url(b"x" * 64),
    )
    with pytest.raises(RemoteAuthenticationError):
        await service.complete_enrollment(invalid)
    assert await service.list_devices(host_id="host:test") == ()
    clock.advance(timedelta(minutes=5, microseconds=1))
    expired_proof = key.sign(
        build_enrollment_proof(
            enrollment_id=ticket.id,
            challenge=ticket.challenge,
            public_key=public_key,
            protocol_version="1",
        )
    )
    with pytest.raises(RemoteAuthenticationError):
        await service.complete_enrollment(
            EnrollmentCompletion(
                enrollment_id=ticket.id,
                challenge=ticket.challenge,
                public_key=public_key,
                proof_signature=encode_base64url(expired_proof),
            )
        )
    assert await service.list_devices(host_id="host:test") == ()
    await store.close()


def test_session_request_rejects_duplicates_and_empty_scope() -> None:
    with pytest.raises(ValueError):
        SessionRequest(requested_scopes=())
    with pytest.raises(ValueError):
        SessionRequest(requested_scopes=(RemoteScope.IDENTITY_READ, RemoteScope.IDENTITY_READ))
