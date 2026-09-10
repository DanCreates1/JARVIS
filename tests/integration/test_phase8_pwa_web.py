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
    PWAEventHub,
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
HOST_ID = "host:pwa-web"
ALL_SCOPES = (
    RemoteScope.BROWSER_SESSION,
    RemoteScope.IDENTITY_READ,
    RemoteScope.EVENTS_READ,
    RemoteScope.SESSION_REVOKE,
    RemoteScope.CLIENT_CHAT,
    RemoteScope.CLIENT_TASKS_READ,
    RemoteScope.CLIENT_STATUS_READ,
)


class _FakeService:
    async def run(self, request: AssistantRequest) -> RuntimeResult:
        return RuntimeResult(status=RuntimeStatus.COMPLETED, reply=request.user_input)

    async def stream(self, request: AssistantRequest) -> AsyncIterator[RuntimeStreamFrame]:
        yield RuntimeStreamFrame(
            result=RuntimeResult(
                status=RuntimeStatus.COMPLETED,
                reply=f"echo:{request.user_input}",
                conversation_id="conversation:pwa",
            )
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


def _headers(*, key: Ed25519PrivateKey, body: bytes, device_id: str, nonce: str) -> dict[str, str]:
    timestamp = datetime.now(UTC)
    signed = SignedRequest(
        method="POST",
        authority="testserver",
        path="/api/v1/browser/sessions",
        query="",
        body=body,
        device_id=device_id,
        key_version=1,
        audience="jarvis-api",
        timestamp=timestamp,
        nonce=nonce,
        session_token=None,
    )
    return {
        "Content-Type": "application/json",
        "Origin": ORIGIN,
        "X-Jarvis-Audience": "jarvis-api",
        "X-Jarvis-Date": timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "X-Jarvis-Device": device_id,
        "X-Jarvis-Key-Version": "1",
        "X-Jarvis-Nonce": nonce,
        "X-Jarvis-Signature": encode_base64url(key.sign(canonical_request(signed))),
    }


def _runtime_factory(
    tmp_path: Path,
    settings: Settings,
    key: Ed25519PrivateKey,
    created: dict[str, object],
    *,
    scopes: tuple[RemoteScope, ...] = ALL_SCOPES,
) -> object:
    async def build(_settings: Settings) -> RuntimeComponents:
        database = tmp_path / "pwa-web.db"
        store = SQLiteConversationStore(database)
        remote_store = SQLiteRemoteIdentityStore(database)
        await store.initialize()
        await remote_store.initialize()
        remote = RemoteIdentityService(remote_store)
        ticket = await remote.create_enrollment(
            host_id=HOST_ID,
            display_name="Synthetic PWA",
            device_type=DeviceType.BROWSER,
            approved_scopes=scopes,
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
        created["device_id"] = device.id
        return RuntimeComponents(
            settings=settings,
            store=store,
            provider=_FakeRouter(),  # type: ignore[arg-type]
            service=_FakeService(),  # type: ignore[arg-type]
            memory_host_id=HOST_ID,
            remote_store=remote_store,
            remote_identity=remote,
        )

    return build


def _bootstrap(client: TestClient, key: Ed25519PrivateKey, device_id: str, scopes: object) -> str:
    body = json.dumps(
        {"requested_scopes": scopes, "audience": "jarvis-api"},
        separators=(",", ":"),
    ).encode()
    response = client.post(
        "/api/v1/browser/sessions",
        content=body,
        headers=_headers(key=key, body=body, device_id=device_id, nonce="P" * 22),
    )
    assert response.status_code == 201
    return str(response.json()["csrf_token"])


def test_pwa_shell_transport_resume_idempotency_and_logout_cleanup(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, trusted_browser_origins=(ORIGIN,), _env_file=None)
    key = Ed25519PrivateKey.generate()
    created: dict[str, object] = {}
    app = create_app(
        settings,
        runtime_factory=_runtime_factory(tmp_path, settings, key, created),  # type: ignore[arg-type]
    )

    with TestClient(app, base_url="https://testserver") as client:
        shell = client.get("/app/")
        assert shell.status_code == 200
        assert "serviceWorker" not in shell.text
        assert "unsafe-inline" not in shell.headers["content-security-policy"]
        assert shell.headers["cache-control"] == "no-cache"
        script = client.get("/app/app.js")
        worker = client.get("/app/sw.js")
        manifest = client.get("/app/manifest.webmanifest")
        assert script.status_code == worker.status_code == manifest.status_code == 200
        assert "localStorage" not in script.text
        assert "indexedDB" in script.text and '"JARVIS_LOGOUT"' in script.text
        assert "SHELL.includes(url.pathname)" in worker.text and "cache.put" in worker.text
        assert "ui.logout.disabled=!state.hasIdentity" in script.text
        assert manifest.json()["start_url"] == "/app/"
        asset_bytes = sum(
            len(client.get(path).content)
            for path in (
                "/app/",
                "/app/app.css",
                "/app/app.js",
                "/app/sw.js",
                "/app/manifest.webmanifest",
                "/app/icon.svg",
            )
        )
        assert asset_bytes <= 250 * 1024

        csrf = _bootstrap(
            client,
            key,
            str(created["device_id"]),
            [scope.value for scope in ALL_SCOPES],
        )
        auth = {"Origin": ORIGIN, "X-Jarvis-CSRF": csrf}
        subscribed = client.post(
            "/api/v1/client/subscriptions",
            headers=auth,
            json={"topics": ["chat", "tasks", "device"]},
        )
        assert subscribed.status_code == 201
        subscription_id = subscribed.json()["id"]

        status = client.get("/api/v1/client/status", headers={"Origin": ORIGIN})
        assert status.status_code == 200
        assert status.json()["device"]["id"] == created["device_id"]
        assert status.json()["notifications"] == {
            "supported": True,
            "private_preview": False,
        }
        assert client.get("/api/v1/client/tasks", headers={"Origin": ORIGIN}).json() == []

        request = {
            "request_id": "request:pwa-one",
            "subscription_id": subscription_id,
            "message": "hello",
        }
        first = client.post("/api/v1/client/chat", headers=auth, json=request)
        assert first.status_code == 200 and first.json()["reply"] == "echo:hello"
        repeated = client.post("/api/v1/client/chat", headers=auth, json=request)
        assert repeated.status_code == 200 and repeated.json() == first.json()

        events = client.get(
            "/api/v1/client/events",
            headers={"Origin": ORIGIN},
            params={"subscription_id": subscription_id, "after": 0},
        )
        assert events.status_code == 200
        assert events.text.count("event: chat.started") == 1
        assert events.text.count("event: chat.completed") == 1
        assert "echo:hello" in events.text
        cursor = int(events.headers["x-jarvis-next-cursor"])
        resumed = client.get(
            "/api/v1/client/events",
            headers={"Origin": ORIGIN},
            params={"subscription_id": subscription_id, "after": cursor},
        )
        assert resumed.status_code == 200 and resumed.text == ": keepalive\n\n"

        logout = client.delete("/api/v1/sessions/current", headers=auth)
        assert logout.status_code == 200
        assert logout.headers["clear-site-data"] == '"cache", "cookies", "storage"'
        hub = app.state.pwa_hub
        assert isinstance(hub, PWAEventHub)
        assert hub.subscription_count == 0 and hub.request_count == 0
        assert (
            client.get(
                "/api/v1/client/events",
                headers={"Origin": ORIGIN},
                params={"subscription_id": subscription_id},
            ).status_code
            == 401
        )


def test_pwa_topics_and_product_routes_require_exact_scopes(tmp_path: Path) -> None:
    scopes = (
        RemoteScope.BROWSER_SESSION,
        RemoteScope.EVENTS_READ,
        RemoteScope.SESSION_REVOKE,
    )
    settings = Settings(data_dir=tmp_path, trusted_browser_origins=(ORIGIN,), _env_file=None)
    key = Ed25519PrivateKey.generate()
    created: dict[str, object] = {}
    app = create_app(
        settings,
        runtime_factory=_runtime_factory(
            tmp_path,
            settings,
            key,
            created,
            scopes=scopes,
        ),  # type: ignore[arg-type]
    )
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _bootstrap(
            client,
            key,
            str(created["device_id"]),
            [scope.value for scope in scopes],
        )
        headers = {"Origin": ORIGIN, "X-Jarvis-CSRF": csrf}
        denied = client.post(
            "/api/v1/client/subscriptions",
            headers=headers,
            json={"topics": ["chat"]},
        )
        assert denied.status_code == 403
        assert client.get("/api/v1/client/status", headers={"Origin": ORIGIN}).status_code == 403
        assert client.get("/api/v1/client/tasks", headers={"Origin": ORIGIN}).status_code == 403
        assert (
            client.post(
                "/api/v1/client/chat",
                headers=headers,
                json={
                    "request_id": "request:denied",
                    "subscription_id": f"subscription:{'0' * 8}-0000-0000-0000-000000000000",
                    "message": "denied",
                },
            ).status_code
            == 403
        )
