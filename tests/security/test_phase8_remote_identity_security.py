from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jarvis.remote import (
    DeviceType,
    EnrollmentCompletion,
    RemoteAuthenticationError,
    RemoteIdentityService,
    RemoteScope,
    SessionRequest,
    SignedRequest,
    SQLiteRemoteIdentityStore,
    build_enrollment_proof,
    canonical_request,
    encode_base64url,
)


def _public_key(key: Ed25519PrivateKey) -> str:
    return encode_base64url(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def _signed(
    key: Ed25519PrivateKey,
    *,
    device_id: str,
    nonce: str,
    token: str | None,
    path: str,
    body: bytes,
) -> tuple[SignedRequest, str]:
    request = SignedRequest(
        method="POST" if body else "GET",
        authority="localhost:8765",
        path=path,
        query="",
        body=body,
        device_id=device_id,
        key_version=1,
        audience="jarvis-api",
        timestamp=datetime.now(UTC),
        nonce=nonce,
        session_token=token,
    )
    return request, encode_base64url(key.sign(canonical_request(request)))


async def _enroll(
    service: RemoteIdentityService,
    key: Ed25519PrivateKey,
    *,
    name: str,
) -> str:
    ticket = await service.create_enrollment(
        host_id="host:security",
        display_name=name,
        device_type=DeviceType.PHONE,
        approved_scopes=(RemoteScope.IDENTITY_READ,),
    )
    public_key = _public_key(key)
    device = await service.complete_enrollment(
        EnrollmentCompletion(
            enrollment_id=ticket.id,
            challenge=ticket.challenge,
            public_key=public_key,
            proof_signature=encode_base64url(
                key.sign(
                    build_enrollment_proof(
                        enrollment_id=ticket.id,
                        challenge=ticket.challenge,
                        public_key=public_key,
                        protocol_version="1",
                    )
                )
            ),
        )
    )
    return device.id


@pytest.mark.asyncio
async def test_session_token_cannot_cross_device_identity(tmp_path: Path) -> None:
    store = SQLiteRemoteIdentityStore(tmp_path / "cross-device.db")
    await store.initialize()
    service = RemoteIdentityService(store)
    first_key = Ed25519PrivateKey.generate()
    second_key = Ed25519PrivateKey.generate()
    first_id = await _enroll(service, first_key, name="First phone")
    second_id = await _enroll(service, second_key, name="Second phone")
    payload = SessionRequest(requested_scopes=(RemoteScope.IDENTITY_READ,))
    body = payload.model_dump_json().encode()
    session_request, session_signature = _signed(
        first_key,
        device_id=first_id,
        nonce="A" * 22,
        token=None,
        path="/api/v1/sessions",
        body=body,
    )
    session = await service.create_session(
        request=session_request,
        signature=session_signature,
        payload=payload,
    )

    stolen_request, stolen_signature = _signed(
        second_key,
        device_id=second_id,
        nonce="B" * 22,
        token=session.token,
        path="/api/v1/identity",
        body=b"",
    )
    with pytest.raises(RemoteAuthenticationError) as rejected:
        await service.authenticate_request(
            request=stolen_request,
            signature=stolen_signature,
            required_scope=RemoteScope.IDENTITY_READ,
        )
    assert rejected.value.code == "session_device_mismatch"
    await store.close()


@pytest.mark.asyncio
async def test_denial_audit_is_sanitized_bounded_and_update_protected(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    store = SQLiteRemoteIdentityStore(database)
    await store.initialize()
    service = RemoteIdentityService(store)
    key = Ed25519PrivateKey.generate()
    device_id = await _enroll(service, key, name="Audit phone")
    now = datetime.now(UTC)
    for _ in range(1_005):
        await store.append_denial(
            reason_code="invalid_signature",
            device_id=device_id,
            created_at=now,
        )
    await store.close()

    with sqlite3.connect(database) as connection:
        count = connection.execute(
            """
            SELECT COUNT(*) FROM remote_audit_events
            WHERE device_id = ? AND event_type = 'request.denied'
            """,
            (device_id,),
        ).fetchone()[0]
        assert count == 1_000
        columns = {row[1] for row in connection.execute("PRAGMA table_info(remote_audit_events)")}
        assert "token" not in columns
        assert "signature" not in columns
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE remote_audit_events SET reason_code = 'changed' WHERE device_id = ?",
                (device_id,),
            )
