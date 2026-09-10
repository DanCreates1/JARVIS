from __future__ import annotations

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
    RemoteStateError,
    SessionRequest,
    SignedRequest,
    SQLiteRemoteIdentityStore,
    build_enrollment_proof,
    canonical_request,
    encode_base64url,
)

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)


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
    path: str,
    device_id: str,
    nonce: str,
    body: bytes,
    token: str | None = None,
) -> tuple[SignedRequest, str]:
    request = SignedRequest(
        method="POST" if body else "GET",
        authority="jarvis.test",
        path=path,
        query="",
        body=body,
        device_id=device_id,
        key_version=1,
        audience="jarvis-api",
        timestamp=NOW,
        nonce=nonce,
        session_token=token,
    )
    return request, encode_base64url(key.sign(canonical_request(request)))


async def _enrolled(
    database: Path,
    key: Ed25519PrivateKey,
    *,
    device_type: DeviceType = DeviceType.BROWSER,
    scopes: tuple[RemoteScope, ...] = (
        RemoteScope.BROWSER_SESSION,
        RemoteScope.IDENTITY_READ,
        RemoteScope.SESSION_REVOKE,
        RemoteScope.APPROVAL_REVIEW,
    ),
) -> tuple[SQLiteRemoteIdentityStore, RemoteIdentityService, str]:
    store = SQLiteRemoteIdentityStore(database)
    await store.initialize()
    service = RemoteIdentityService(store, clock=lambda: NOW)
    ticket = await service.create_enrollment(
        host_id="host:browser-security",
        display_name="Browser security fixture",
        device_type=device_type,
        approved_scopes=scopes,
        risk_ceiling=1,
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
    return store, service, device.id


@pytest.mark.asyncio
async def test_browser_session_survives_restart_but_not_csrf_or_api_type_confusion(
    tmp_path: Path,
) -> None:
    database = tmp_path / "browser-security.db"
    key = Ed25519PrivateKey.generate()
    store, service, device_id = await _enrolled(database, key)
    payload = SessionRequest(
        requested_scopes=(
            RemoteScope.BROWSER_SESSION,
            RemoteScope.IDENTITY_READ,
            RemoteScope.SESSION_REVOKE,
            RemoteScope.APPROVAL_REVIEW,
        )
    )
    body = payload.model_dump_json().encode()
    request, signature = _signed(
        key,
        path="/api/v1/browser/sessions",
        device_id=device_id,
        nonce="A" * 22,
        body=body,
    )
    credential = await service.create_browser_session(
        request=request,
        signature=signature,
        payload=payload,
    )
    await store.close()

    reopened_store = SQLiteRemoteIdentityStore(database)
    await reopened_store.initialize()
    reopened = RemoteIdentityService(reopened_store, clock=lambda: NOW)
    context = await reopened.authenticate_browser_session(
        cookie_token=credential.cookie_token,
        required_scope=RemoteScope.IDENTITY_READ,
    )
    assert context.device_id == device_id
    assert context.authenticated_at == NOW
    assert context.risk_ceiling == 1

    with pytest.raises(RemoteAuthenticationError):
        await reopened.authenticate_browser_session(
            cookie_token=credential.cookie_token,
            csrf_token="Z" * 43,
            require_csrf=True,
        )
    valid = await reopened.authenticate_browser_session(
        cookie_token=credential.cookie_token,
        csrf_token=credential.csrf_token,
        require_csrf=True,
    )
    assert valid.session_id == credential.session_id

    confused, confused_signature = _signed(
        key,
        path="/api/v1/identity",
        device_id=device_id,
        nonce="B" * 22,
        body=b"",
        token=credential.cookie_token,
    )
    with pytest.raises(RemoteAuthenticationError) as error:
        await reopened.authenticate_request(
            request=confused,
            signature=confused_signature,
            required_scope=RemoteScope.IDENTITY_READ,
        )
    assert error.value.code == "invalid_session_type"

    assert await reopened.revoke_device(host_id="host:browser-security", device_id=device_id)
    with pytest.raises(RemoteAuthenticationError):
        await reopened.authenticate_browser_session(cookie_token=credential.cookie_token)
    events = await reopened_store.list_audit_events(device_id=device_id, limit=100)
    event_text = " ".join(f"{event.event_type}:{event.reason_code}" for event in events)
    assert "browser_device_signature_verified" in event_text
    assert "csrf_failed" in event_text
    assert credential.cookie_token not in event_text
    assert credential.csrf_token not in event_text
    await reopened_store.close()


@pytest.mark.asyncio
async def test_browser_bootstrap_rejects_wrong_device_type_scope_and_stolen_tokens(
    tmp_path: Path,
) -> None:
    key = Ed25519PrivateKey.generate()
    store, service, device_id = await _enrolled(
        tmp_path / "service-device.db",
        key,
        device_type=DeviceType.SERVICE,
    )
    payload = SessionRequest(requested_scopes=(RemoteScope.BROWSER_SESSION,))
    body = payload.model_dump_json().encode()
    request, signature = _signed(
        key,
        path="/api/v1/browser/sessions",
        device_id=device_id,
        nonce="C" * 22,
        body=body,
    )
    with pytest.raises(RemoteStateError) as wrong_type:
        await service.create_browser_session(
            request=request,
            signature=signature,
            payload=payload,
        )
    assert wrong_type.value.code == "browser_device_type_denied"
    with pytest.raises(RemoteAuthenticationError):
        await service.authenticate_browser_session(cookie_token="X" * 43)
    await store.close()

    second_key = Ed25519PrivateKey.generate()
    second_store, second, second_device = await _enrolled(
        tmp_path / "missing-scope.db",
        second_key,
        scopes=(RemoteScope.IDENTITY_READ,),
    )
    missing = SessionRequest(requested_scopes=(RemoteScope.IDENTITY_READ,))
    missing_body = missing.model_dump_json().encode()
    missing_request, missing_signature = _signed(
        second_key,
        path="/api/v1/browser/sessions",
        device_id=second_device,
        nonce="D" * 22,
        body=missing_body,
    )
    with pytest.raises(RemoteStateError) as scope_error:
        await second.create_browser_session(
            request=missing_request,
            signature=missing_signature,
            payload=missing,
        )
    assert scope_error.value.code == "scope_expansion"
    await second_store.close()
