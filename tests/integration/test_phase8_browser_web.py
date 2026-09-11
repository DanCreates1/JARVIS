from __future__ import annotations

import json
import sqlite3
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

ORIGIN = "https://phone.jarvis.test"


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


def _public_key(key: Ed25519PrivateKey) -> str:
    return encode_base64url(
        key.public_key().public_bytes(
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
    token: str | None = None,
) -> dict[str, str]:
    timestamp = datetime.now(UTC)
    signed = SignedRequest(
        method=method,
        authority="testserver",
        path=path,
        query="",
        body=body,
        device_id=device_id,
        key_version=1,
        audience="jarvis-api",
        timestamp=timestamp,
        nonce=nonce,
        session_token=token,
    )
    headers = {
        "X-Jarvis-Audience": "jarvis-api",
        "X-Jarvis-Date": timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "X-Jarvis-Device": device_id,
        "X-Jarvis-Key-Version": "1",
        "X-Jarvis-Nonce": nonce,
        "X-Jarvis-Signature": encode_base64url(key.sign(canonical_request(signed))),
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def test_browser_cookie_csrf_origin_cors_csp_logout_and_secret_storage(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        trusted_browser_origins=(ORIGIN,),
        _env_file=None,
    )
    key = Ed25519PrivateKey.generate()
    database = tmp_path / "browser-web.db"
    created: dict[str, object] = {}

    async def runtime_factory(_settings: Settings) -> RuntimeComponents:
        store = SQLiteConversationStore(database)
        remote_store = SQLiteRemoteIdentityStore(database)
        await store.initialize()
        await remote_store.initialize()
        remote = RemoteIdentityService(remote_store)
        ticket = await remote.create_enrollment(
            host_id="host:browser-web",
            display_name="Synthetic browser",
            device_type=DeviceType.BROWSER,
            approved_scopes=(
                RemoteScope.BROWSER_SESSION,
                RemoteScope.IDENTITY_READ,
                RemoteScope.EVENTS_READ,
                RemoteScope.SESSION_REVOKE,
            ),
            risk_ceiling=1,
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

    with TestClient(
        create_app(settings, runtime_factory=runtime_factory), base_url="https://testserver"
    ) as client:
        device_id = str(created["device_id"])
        body = json.dumps(
            {
                "requested_scopes": [
                    "browser.session",
                    "identity.read",
                    "events.read",
                    "session.revoke",
                ],
                "audience": "jarvis-api",
            },
            separators=(",", ":"),
        ).encode()
        issued = client.post(
            "/api/v1/browser/sessions",
            content=body,
            headers={
                **_headers(
                    key=key,
                    method="POST",
                    path="/api/v1/browser/sessions",
                    device_id=device_id,
                    nonce="J" * 22,
                    body=body,
                ),
                "Content-Type": "application/json",
                "Origin": ORIGIN,
            },
        )
        assert issued.status_code == 201
        payload = issued.json()
        csrf_token = payload["csrf_token"]
        assert "cookie_token" not in payload
        set_cookie = issued.headers["set-cookie"]
        assert "__Host-jarvis-session=" in set_cookie
        assert (
            "Secure" in set_cookie and "HttpOnly" in set_cookie and "SameSite=strict" in set_cookie
        )
        assert "Domain=" not in set_cookie
        assert issued.headers["access-control-allow-origin"] == ORIGIN

        cookie_token = client.cookies.get("__Host-jarvis-session")
        assert cookie_token is not None
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT token_sha256, csrf_token_sha256, session_kind FROM remote_sessions"
            ).fetchone()
        assert row is not None and row[2] == "browser"
        assert cookie_token not in row and csrf_token not in row

        identity = client.get("/api/v1/identity", headers={"Origin": ORIGIN})
        assert identity.status_code == 200 and identity.json()["id"] == device_id
        assert identity.headers["access-control-allow-origin"] == ORIGIN
        assert "unsafe-inline" not in identity.headers["content-security-policy"]
        assert identity.headers["strict-transport-security"] == "max-age=31536000"

        ios_identity = client.get("/api/v1/identity", headers={"X-Jarvis-Browser-Origin": ORIGIN})
        assert ios_identity.status_code == 200 and ios_identity.json()["id"] == device_id
        assert ios_identity.headers["access-control-allow-origin"] == ORIGIN
        opaque_ios_identity = client.get(
            "/api/v1/identity",
            headers={"Origin": "null", "X-Jarvis-Browser-Origin": ORIGIN},
        )
        assert opaque_ios_identity.status_code == 200
        assert opaque_ios_identity.headers["access-control-allow-origin"] == ORIGIN

        assert client.get("/api/v1/identity").status_code == 403
        hostile = client.get(
            "/api/v1/identity", headers={"Origin": "https://phone.jarvis.test.attacker.invalid"}
        )
        assert hostile.status_code == 403
        assert "access-control-allow-origin" not in hostile.headers
        hostile_fallback = client.get(
            "/api/v1/identity",
            headers={
                "Origin": "null",
                "X-Jarvis-Browser-Origin": "https://phone.jarvis.test.attacker.invalid",
            },
        )
        assert hostile_fallback.status_code == 403
        assert "access-control-allow-origin" not in hostile_fallback.headers

        missing_csrf = client.delete("/api/v1/sessions/current", headers={"Origin": ORIGIN})
        assert missing_csrf.status_code == 401
        wrong_csrf = client.delete(
            "/api/v1/sessions/current",
            headers={"Origin": ORIGIN, "X-Jarvis-CSRF": "Z" * 43},
        )
        assert wrong_csrf.status_code == 401
        fallback_on_unsafe_method = client.delete(
            "/api/v1/sessions/current",
            headers={"X-Jarvis-Browser-Origin": ORIGIN, "X-Jarvis-CSRF": csrf_token},
        )
        assert fallback_on_unsafe_method.status_code == 403
        logout = client.delete(
            "/api/v1/sessions/current",
            headers={"Origin": ORIGIN, "X-Jarvis-CSRF": csrf_token},
        )
        assert logout.status_code == 200 and logout.json() == {"revoked": True}
        assert client.cookies.get("__Host-jarvis-session") is None

    assert isinstance(created["remote_store"], SQLiteRemoteIdentityStore)
    assert created["remote_store"]._connection is None  # type: ignore[union-attr]


def test_browser_preflight_rate_and_request_bounds_fail_closed(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        trusted_browser_origins=(ORIGIN,),
        remote_public_requests_per_minute=2,
        remote_authenticated_requests_per_minute=1,
        _env_file=None,
    )

    async def runtime_factory(_settings: Settings) -> RuntimeComponents:
        store = SQLiteConversationStore(tmp_path / "bounds.db")
        remote_store = SQLiteRemoteIdentityStore(tmp_path / "bounds.db")
        await store.initialize()
        await remote_store.initialize()
        return RuntimeComponents(
            settings=settings,
            store=store,
            provider=_FakeRouter(),  # type: ignore[arg-type]
            service=_FakeService(),  # type: ignore[arg-type]
            remote_store=remote_store,
            remote_identity=RemoteIdentityService(remote_store),
        )

    with TestClient(
        create_app(settings, runtime_factory=runtime_factory), base_url="https://testserver"
    ) as client:
        preflight = client.options(
            "/api/v1/identity",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Jarvis-CSRF",
            },
        )
        assert preflight.status_code == 204
        assert preflight.headers["access-control-allow-origin"] == ORIGIN
        assert "*" not in preflight.headers["access-control-allow-methods"]
        denied_preflight = client.options(
            "/api/v1/identity",
            headers={
                "Origin": "null",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert denied_preflight.status_code == 403

        first = client.get("/api/v1/identity")
        assert first.status_code == 401
        limited = client.get("/api/v1/identity")
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) >= 1

    separate = Settings(data_dir=tmp_path / "shape", _env_file=None)
    with TestClient(create_app(separate, runtime_factory=runtime_factory)) as client:
        oversized_query = client.get("/api/v1/identity?" + "a" * 8_193)
        assert oversized_query.status_code == 400
        oversized_header = client.get("/api/v1/identity", headers={"X-Fill": "a" * 33_000})
        assert oversized_header.status_code == 400
