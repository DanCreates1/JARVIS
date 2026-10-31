from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from jarvis.config import Settings
from jarvis.voice.models import VoiceControl
from jarvis.voice.pwa import VOICE_PATH
from jarvis.web import create_app
from tests.integration.test_phase8_pwa_web import ALL_SCOPES, ORIGIN, _bootstrap, _runtime_factory
from tests.integration.test_phase8_remote_web import _headers as signed_headers
from tests.unit.test_pwa_voice import PCM, service


@pytest.fixture(params=["standard", "foreground-voice"])
def voice_web(tmp_path: Path, request):
    svc, stt = service(tmp_path, runtime_profile=request.param)
    settings = Settings(
        data_dir=tmp_path,
        runtime_profile=request.param,
        pwa_voice_enabled=True,
        trusted_browser_origins=(ORIGIN,),
        _env_file=None,
    )
    key = Ed25519PrivateKey.generate()
    created: dict[str, object] = {}
    app = create_app(
        settings,
        runtime_factory=_runtime_factory(tmp_path, settings, key, created),
        voice_service=svc,
    )
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _bootstrap(client, key, str(created["device_id"]), [s.value for s in ALL_SCOPES])
        headers = {
            "Origin": ORIGIN,
            "X-Jarvis-CSRF": csrf,
            "Content-Type": "application/octet-stream",
        }
        yield client, headers, svc, stt, app, key, created


def test_scoped_memory_only_draft_and_dynamic_document_policy(voice_web) -> None:
    client, headers, svc, stt, *_ = voice_web
    assert "microphone=(self)" in client.get("/app/").headers["permissions-policy"]
    assert "microphone=()" in client.get("/").headers["permissions-policy"]
    metadata = client.get("/api/v1/client/voice", headers={"Origin": ORIGIN})
    assert metadata.json()["available"] is True
    assert metadata.headers["cache-control"] == "no-store"
    response = client.post(VOICE_PATH, headers=headers, content=PCM)
    assert response.status_code == 200, response.text
    assert response.json() == {"text": "Synthetic transcript", "duration_ms": 200}
    assert response.headers["cache-control"] == "no-store"
    assert stt.started.is_set()
    assert (
        client.get("/api/v1/client/conversations", headers={"Origin": ORIGIN}).json()[
            "conversations"
        ]
        == []
    )
    svc.settings.voice_settings_path.write_text("broken", encoding="utf-8")
    assert "microphone=()" in client.get("/app/").headers["permissions-policy"]
    assert not client.get("/api/v1/client/voice", headers={"Origin": ORIGIN}).json()["available"]
    assert client.post(VOICE_PATH, headers=headers, content=PCM).status_code == 503


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ("csrf", 401),
        ("wrong_csrf", 401),
        ("duplicate_csrf", 401),
        ("origin", 403),
        ("bearer", 400),
        ("signed", 400),
        ("duplicate_length", 400),
        ("bad_length", 400),
        ("content_type", 415),
        ("method", 405),
        ("anonymous", 401),
    ],
)
def test_rejects_before_speech(voice_web, change: str, status: int) -> None:
    client, original, _, stt, *_ = voice_web
    headers = dict(original)
    if change == "csrf":
        del headers["X-Jarvis-CSRF"]
    elif change == "wrong_csrf":
        headers["X-Jarvis-CSRF"] = "x" * 43
    elif change == "origin":
        headers["Origin"] = "https://evil.test"
    elif change == "bearer":
        headers["Authorization"] = "Bearer " + "x" * 43
    elif change == "signed":
        headers["X-Jarvis-Device"] = "device:mixed"
    elif change == "duplicate_length":
        headers = [*headers.items(), ("Content-Length", "6400"), ("Content-Length", "6400")]
    elif change == "bad_length":
        headers["Content-Length"] = "bad"
    elif change == "duplicate_csrf":
        headers = [*headers.items(), ("X-Jarvis-CSRF", original["X-Jarvis-CSRF"])]
    elif change == "content_type":
        headers["Content-Type"] = "audio/wav"
    elif change == "anonymous":
        client.cookies.clear()
    response = client.request(
        "PUT" if change == "method" else "POST", VOICE_PATH, headers=headers, content=PCM
    )
    assert response.status_code == status, response.text
    assert not stt.started.is_set()


@pytest.mark.parametrize(
    "size,status", [(0, 400), (3838, 400), (3841, 400), (960002, 413), (1048577, 413)]
)
def test_body_limits_and_release(voice_web, size: int, status: int) -> None:
    client, headers, svc, stt, *_ = voice_web
    assert client.post(VOICE_PATH, headers=headers, content=b"x" * size).status_code == status
    assert not stt.started.is_set()
    assert not svc.metadata()["busy"]


def test_six_starts_per_device_and_missing_chat_scope(voice_web) -> None:
    client, headers, _, _, _, key, created = voice_web
    for _ in range(6):
        assert client.post(VOICE_PATH, headers=headers, content=PCM).status_code == 200
    assert client.post(VOICE_PATH, headers=headers, content=PCM).status_code == 429
    scopes = [s.value for s in ALL_SCOPES if s.value != "client.chat"]
    csrf = _bootstrap(client, key, str(created["device_id"]), scopes, nonce="S" * 22)
    denied = client.post(VOICE_PATH, headers={**headers, "X-Jarvis-CSRF": csrf}, content=PCM)
    assert denied.status_code == 403
    assert client.get("/api/v1/client/voice", headers={"Origin": ORIGIN}).status_code == 403


def test_revoked_cookie_cannot_admit_audio(voice_web) -> None:
    client, headers, _, stt, *_ = voice_web
    assert client.delete("/api/v1/sessions/current", headers=headers).status_code == 200
    assert client.post(VOICE_PATH, headers=headers, content=PCM).status_code == 401
    assert not stt.started.is_set()


def test_upload_deadline_stream_bound_and_unauthenticated_nonconsumption(
    voice_web, monkeypatch
) -> None:
    client, headers, svc, stt, app, *_ = voice_web
    monkeypatch.setattr("jarvis.web.UPLOAD_SECONDS", 0.02)

    async def check() -> None:
        transport = httpx.ASGITransport(app=app)
        cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
        consumed = False

        async def slow():
            nonlocal consumed
            consumed = True
            await asyncio.sleep(0.1)
            yield PCM

        async with httpx.AsyncClient(
            transport=transport, base_url="https://testserver"
        ) as async_client:
            assert (
                await async_client.post(VOICE_PATH, headers=headers, content=slow())
            ).status_code == 401
            assert not consumed
            response = await async_client.post(
                VOICE_PATH, headers={**headers, "Cookie": cookie}, content=slow()
            )
            assert response.status_code == 408
            assert not svc.metadata()["busy"]

            async def excess():
                yield b"x" * 500000
                yield b"x" * 500000

            response = await async_client.post(
                VOICE_PATH, headers={**headers, "Cookie": cookie}, content=excess()
            )
            assert response.status_code == 413
            assert not svc.metadata()["busy"]
            assert not stt.started.is_set()

    client.portal.call(check)


@pytest.mark.parametrize(
    "reason,status", [("revoke", 401), ("expiry", 401), ("kill", 503), ("timeout", 504)]
)
def test_identity_kill_timeout_and_capacity_during_api_inference(
    voice_web, reason: str, status: int
) -> None:
    client, headers, svc, stt, app, _, created = voice_web

    async def check() -> None:
        stt.finish.clear()
        cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://testserver"
        ) as ac:
            if reason == "timeout":
                svc.timeout = 0.02
            request = asyncio.create_task(
                ac.post(VOICE_PATH, headers={**headers, "Cookie": cookie}, content=PCM)
            )
            await stt.started.wait()
            busy = await ac.post(VOICE_PATH, headers={**headers, "Cookie": cookie}, content=PCM)
            assert busy.status_code == 409
            if reason == "revoke":
                assert (
                    await ac.delete(
                        "/api/v1/sessions/current", headers={**headers, "Cookie": cookie}
                    )
                ).status_code == 200
            elif reason == "expiry":
                app.state.runtime.remote_identity._clock = lambda: (
                    datetime.now(UTC) + timedelta(hours=2)
                )
            elif reason == "kill":
                svc.controls.save_control(VoiceControl(enabled=False))
            response = await request
            assert response.status_code == status, response.text
            assert "Synthetic transcript" not in response.text
            assert svc.metadata()["busy"] is True
            stt.finish.set()
            for _ in range(20):
                await asyncio.sleep(0)
            assert svc.metadata()["busy"] is False
            assert created["service"].calls == 0
            records = await app.state.runtime.store.list_audit_records(limit=20)
            assert all("Synthetic transcript" not in r.model_dump_json() for r in records)

    client.portal.call(check)


def test_signed_upload_requires_final_body_signature_and_token_admission(voice_web) -> None:
    client, _, svc, stt, _, key, created = voice_web
    client.cookies.clear()
    body = json.dumps({"requested_scopes": ["client.chat"], "audience": "jarvis-api"}).encode()
    credential = client.post(
        "/api/v1/sessions",
        content=body,
        headers={
            "Content-Type": "application/json",
            **signed_headers(
                key=key,
                method="POST",
                path="/api/v1/sessions",
                body=body,
                device_id=str(created["device_id"]),
                nonce="T" * 22,
            ),
        },
    )
    assert credential.status_code == 201, credential.text
    token = credential.json()["token"]
    headers = signed_headers(
        key=key,
        method="POST",
        path=VOICE_PATH,
        body=PCM,
        device_id=str(created["device_id"]),
        nonce="U" * 22,
        token=token,
    )
    headers["Content-Type"] = "application/octet-stream"
    invalid = client.post(VOICE_PATH, headers=headers, content=PCM[:-2])
    assert invalid.status_code == 401
    assert not stt.started.is_set() and not svc.metadata()["busy"]
    headers = signed_headers(
        key=key,
        method="POST",
        path=VOICE_PATH,
        body=PCM,
        device_id=str(created["device_id"]),
        nonce="V" * 22,
        token=token,
    )
    headers["Content-Type"] = "application/octet-stream"
    response = client.post(VOICE_PATH, headers=headers, content=PCM)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("reason,status", [("kill", 503), ("expiry", 401)])
def test_revalidates_after_audit_io_before_exposing_text(
    voice_web, monkeypatch, reason, status
) -> None:
    client, headers, svc, _, app, *_ = voice_web
    original = app.state.runtime.store.append_audit_record

    async def audit(**kwargs):
        result = await original(**kwargs)
        if kwargs["action"] == "pwa.voice":
            if reason == "kill":
                svc.controls.save_control(VoiceControl(enabled=False))
            else:
                app.state.runtime.remote_identity._clock = lambda: (
                    datetime.now(UTC) + timedelta(hours=2)
                )
        return result

    monkeypatch.setattr(app.state.runtime.store, "append_audit_record", audit)
    response = client.post(VOICE_PATH, headers=headers, content=PCM)
    assert response.status_code == status
    assert "Synthetic transcript" not in response.text
