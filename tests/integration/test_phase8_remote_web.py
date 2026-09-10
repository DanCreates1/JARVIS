from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from jarvis.bootstrap import RuntimeComponents
from jarvis.config import Settings
from jarvis.core import (
    AssistantRequest,
    ModelRole,
    RuntimeResult,
    RuntimeStatus,
    RuntimeStreamFrame,
)
from jarvis.memory import SQLiteConversationStore
from jarvis.remote import (
    DeviceType,
    EnrollmentCompletion,
    RemoteIdentityService,
    RemoteScope,
    SignedRequest,
    SQLiteRemoteIdentityStore,
    build_enrollment_proof,
    canonical_request,
    encode_base64url,
)
from jarvis.web import create_app


class _FakeService:
    async def run(self, request: AssistantRequest) -> RuntimeResult:
        return RuntimeResult(status=RuntimeStatus.COMPLETED, reply=request.user_input)

    async def stream(self, request: AssistantRequest) -> AsyncIterator[RuntimeStreamFrame]:
        yield RuntimeStreamFrame(
            result=RuntimeResult(status=RuntimeStatus.COMPLETED, reply=request.user_input)
        )


class _FakeRouter:
    def __init__(self) -> None:
        self.providers = {ModelRole.LOCAL: object()}

    async def close(self) -> None:
        return None


def _public_key(private_key: Ed25519PrivateKey) -> str:
    return encode_base64url(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def _headers(
    *,
    key: Ed25519PrivateKey,
    method: str,
    path: str,
    device_id: str,
    nonce: str,
    body: bytes = b"",
    query: str = "",
    token: str | None = None,
    key_version: int = 1,
) -> dict[str, str]:
    timestamp = datetime.now(UTC)
    request = SignedRequest(
        method=method,
        authority="testserver",
        path=path,
        query=query,
        body=body,
        device_id=device_id,
        key_version=key_version,
        audience="jarvis-api",
        timestamp=timestamp,
        nonce=nonce,
        session_token=token,
    )
    headers = {
        "X-Jarvis-Audience": "jarvis-api",
        "X-Jarvis-Date": timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "X-Jarvis-Device": device_id,
        "X-Jarvis-Key-Version": str(key_version),
        "X-Jarvis-Nonce": nonce,
        "X-Jarvis-Signature": encode_base64url(key.sign(canonical_request(request))),
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def test_versioned_remote_api_enrollment_scope_replay_and_logout(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    key = Ed25519PrivateKey.generate()
    created: dict[str, object] = {}

    async def runtime_factory(_settings: Settings) -> RuntimeComponents:
        database = tmp_path / "remote-web.db"
        store = SQLiteConversationStore(database)
        remote_store = SQLiteRemoteIdentityStore(database)
        await store.initialize()
        await remote_store.initialize()
        remote = RemoteIdentityService(remote_store)
        ticket = await remote.create_enrollment(
            host_id="host:web-test",
            display_name="Synthetic web phone",
            device_type=DeviceType.PHONE,
            approved_scopes=(
                RemoteScope.IDENTITY_READ,
                RemoteScope.EVENTS_READ,
                RemoteScope.SESSION_REVOKE,
            ),
            risk_ceiling=0,
        )
        created.update(ticket=ticket, remote_store=remote_store)
        return RuntimeComponents(
            settings=settings,
            store=store,
            provider=_FakeRouter(),  # type: ignore[arg-type]
            service=_FakeService(),  # type: ignore[arg-type]
            remote_store=remote_store,
            remote_identity=remote,
        )

    app = create_app(settings, runtime_factory=runtime_factory)
    with TestClient(app) as client:
        missing = client.get("/api/v1/identity")
        assert missing.status_code == 401
        assert missing.headers["www-authenticate"] == 'Bearer realm="jarvis-api"'
        assert missing.headers["cache-control"] == "no-store"
        oversized = client.post(
            "/api/v1/enrollments/complete",
            content=b"x" * 1_048_577,
        )
        assert oversized.status_code == 413
        assert oversized.json() == {"detail": "Remote request body too large"}

        ticket = created["ticket"]
        public_key = _public_key(key)
        proof = key.sign(
            build_enrollment_proof(
                enrollment_id=ticket.id,  # type: ignore[union-attr]
                challenge=ticket.challenge,  # type: ignore[union-attr]
                public_key=public_key,
                protocol_version="1",
            )
        )
        enrolled = client.post(
            "/api/v1/enrollments/complete",
            json=EnrollmentCompletion(
                enrollment_id=ticket.id,  # type: ignore[union-attr]
                challenge=ticket.challenge,  # type: ignore[union-attr]
                public_key=public_key,
                proof_signature=encode_base64url(proof),
            ).model_dump(mode="json"),
        )
        assert enrolled.status_code == 201
        device_id = enrolled.json()["id"]

        session_body = json.dumps(
            {
                "requested_scopes": [
                    "identity.read",
                    "events.read",
                    "session.revoke",
                ],
                "audience": "jarvis-api",
            },
            separators=(",", ":"),
        ).encode()
        session_headers = _headers(
            key=key,
            method="POST",
            path="/api/v1/sessions",
            device_id=device_id,
            nonce="A" * 22,
            body=session_body,
        )
        issued = client.post(
            "/api/v1/sessions",
            content=session_body,
            headers={**session_headers, "Content-Type": "application/json"},
        )
        assert issued.status_code == 201
        credential = issued.json()
        token = credential["token"]

        identity_headers = _headers(
            key=key,
            method="GET",
            path="/api/v1/identity",
            device_id=device_id,
            nonce="B" * 22,
            token=token,
        )
        identity = client.get("/api/v1/identity", headers=identity_headers)
        assert identity.status_code == 200
        assert identity.json()["id"] == device_id
        replay = client.get("/api/v1/identity", headers=identity_headers)
        assert replay.status_code == 401
        assert replay.json() == {"detail": "Remote authentication failed"}

        events_query = "after=0&limit=100"
        events = client.get(
            f"/api/v1/events?{events_query}",
            headers=_headers(
                key=key,
                method="GET",
                path="/api/v1/events",
                query=events_query,
                device_id=device_id,
                nonce="C" * 22,
                token=token,
            ),
        )
        assert events.status_code == 200
        event_text = events.text
        assert "session.created" in event_text and "request.denied" in event_text
        assert token not in event_text and public_key not in event_text

        tampered_query = client.get(
            "/api/v1/events?after=1&limit=100",
            headers=_headers(
                key=key,
                method="GET",
                path="/api/v1/events",
                query=events_query,
                device_id=device_id,
                nonce="D" * 22,
                token=token,
            ),
        )
        assert tampered_query.status_code == 401

        logout = client.delete(
            "/api/v1/sessions/current",
            headers=_headers(
                key=key,
                method="DELETE",
                path="/api/v1/sessions/current",
                device_id=device_id,
                nonce="E" * 22,
                token=token,
            ),
        )
        assert logout.status_code == 200
        after_logout = client.get(
            "/api/v1/identity",
            headers=_headers(
                key=key,
                method="GET",
                path="/api/v1/identity",
                device_id=device_id,
                nonce="F" * 22,
                token=token,
            ),
        )
        assert after_logout.status_code == 401

    remote_store = created["remote_store"]
    assert isinstance(remote_store, SQLiteRemoteIdentityStore)
    assert remote_store._connection is None


def test_versioned_remote_api_rejects_scope_expansion_and_wrong_token_type(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    key = Ed25519PrivateKey.generate()
    created: dict[str, object] = {}

    async def runtime_factory(_settings: Settings) -> RuntimeComponents:
        database = tmp_path / "remote-scope.db"
        store = SQLiteConversationStore(database)
        remote_store = SQLiteRemoteIdentityStore(database)
        await store.initialize()
        await remote_store.initialize()
        remote = RemoteIdentityService(remote_store)
        ticket = await remote.create_enrollment(
            host_id="host:scope-test",
            display_name="Limited phone",
            device_type=DeviceType.PHONE,
            approved_scopes=(RemoteScope.IDENTITY_READ,),
        )
        public_key = _public_key(key)
        device = await remote.complete_enrollment(
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
        created.update(device_id=device.id, remote_store=remote_store)
        return RuntimeComponents(
            settings=settings,
            store=store,
            provider=_FakeRouter(),  # type: ignore[arg-type]
            service=_FakeService(),  # type: ignore[arg-type]
            remote_store=remote_store,
            remote_identity=remote,
        )

    with TestClient(create_app(settings, runtime_factory=runtime_factory)) as client:
        device_id = str(created["device_id"])
        body = b'{"requested_scopes":["events.read"],"audience":"jarvis-api"}'
        expanded = client.post(
            "/api/v1/sessions",
            content=body,
            headers={
                **_headers(
                    key=key,
                    method="POST",
                    path="/api/v1/sessions",
                    device_id=device_id,
                    nonce="G" * 22,
                    body=body,
                ),
                "Content-Type": "application/json",
            },
        )
        assert expanded.status_code == 403

        wrong_type_headers = _headers(
            key=key,
            method="GET",
            path="/api/v1/identity",
            device_id=device_id,
            nonce="H" * 22,
            token="A" * 43,
        )
        wrong_type_headers["Authorization"] = "Basic " + "A" * 43
        assert client.get("/api/v1/identity", headers=wrong_type_headers).status_code == 401
