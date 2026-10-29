from __future__ import annotations

import asyncio
import io
import sqlite3
import time
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from PIL import Image

from jarvis.attachments import AttachmentService
from jarvis.config import Settings
from jarvis.planning import SQLiteTaskStore
from jarvis.web import create_app
from tests.integration.test_phase6_task_store import graph
from tests.integration.test_phase8_pwa_web import (
    ALL_SCOPES,
    HOST_ID,
    ORIGIN,
    _bootstrap,
    _runtime_factory,
)
from tests.security.test_attachment_processing import pdf

UPLOAD = "/api/v1/client/attachments/" + "1" * 32


@pytest.fixture(params=["standard", "private-files"])
def workflows(tmp_path: Path, request):
    settings = Settings(
        data_dir=tmp_path,
        attachments_enabled=True,
        runtime_profile=request.param,
        trusted_browser_origins=(ORIGIN,),
        _env_file=None,
    )
    key = Ed25519PrivateKey.generate()
    created = {}
    base = _runtime_factory(tmp_path, settings, key, created)

    async def factory(config):
        runtime = await base(config)
        runtime.attachments = AttachmentService(
            runtime.store.database_path, host_id=HOST_ID, enabled=True
        )
        await runtime.attachments.initialize()
        runtime.task_store = SQLiteTaskStore(runtime.store.database_path)
        await runtime.task_store.initialize()
        await runtime.task_store.create_task(graph(host_id=HOST_ID))
        await runtime.task_store.create_task(graph(task_id="task-foreign", host_id="other-host"))
        return runtime

    app = create_app(settings, runtime_factory=factory)
    with TestClient(app, base_url="https://testserver") as client:
        csrf = _bootstrap(
            client, key, str(created["device_id"]), [scope.value for scope in ALL_SCOPES]
        )
        headers = {
            "Origin": ORIGIN,
            "X-Jarvis-CSRF": csrf,
            "Content-Type": "text/plain",
            "X-Jarvis-Filename": "fixture.txt",
        }
        yield client, headers, app, key, created


def terminal(client, headers, request_id="request:f14"):
    for _ in range(300):
        result = client.get(f"/api/v1/client/chat/{request_id}", headers={"Origin": ORIGIN})
        assert result.status_code == 200, result.text
        if result.json()["status"] != "running":
            return result.json()
        time.sleep(0.01)
    raise AssertionError("Core did not finish synthetic request")


@pytest.mark.parametrize("kind", ["text", "pdf", "png", "jpeg"])
def test_upload_explicit_send_processing_history_and_search(workflows, kind):
    client, headers, app, *_ = workflows
    capability = client.get("/api/v1/client/status", headers={"Origin": ORIGIN})
    assert capability.status_code == 200
    assert capability.json()["attachments"] == {
        "available": True,
        "max_bytes": 1_048_576,
        "vision_configured": False,
    }
    body = b"synthetic source"
    filename = "fixture.txt"
    media_type = "text/plain"
    if kind == "pdf":
        body = pdf()
        filename = "fixture.pdf"
        media_type = "application/pdf"
    if kind in {"png", "jpeg"}:
        image = io.BytesIO()
        Image.new("RGB", (12, 12), "red").save(image, kind.upper())
        body = image.getvalue()
        filename = f"fixture.{kind}"
        media_type = f"image/{kind}"
    response = client.post(
        UPLOAD,
        headers={**headers, "X-Jarvis-Filename": filename, "Content-Type": media_type},
        content=body,
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    assert (
        client.get("/api/v1/client/conversations", headers={"Origin": ORIGIN}).json()[
            "conversations"
        ]
        == []
    )
    with sqlite3.connect(app.state.runtime.store.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM attachments").fetchone()[0] == 0
    subscription = client.post(
        "/api/v1/client/subscriptions", headers=headers, json={"topics": ["chat"]}
    )
    # json needs its declared content type; upload headers deliberately declare text/plain.
    if subscription.status_code != 201:
        subscription = client.post(
            "/api/v1/client/subscriptions",
            headers={**headers, "Content-Type": "application/json"},
            json={"topics": ["chat"]},
        )
    assert subscription.status_code == 201, subscription.text
    payload = {
        "request_id": "request:f14",
        "subscription_id": subscription.json()["id"],
        "message": "synthetic query",
        "upload_ids": ["1" * 32],
    }
    submitted = client.post(
        "/api/v1/client/chat", headers={**headers, "Content-Type": "application/json"}, json=payload
    )
    assert submitted.status_code in {200, 202}, submitted.text
    result = terminal(client, headers)
    assert result["status"] == "completed", result
    cid = result["conversation_id"]
    with sqlite3.connect(app.state.runtime.store.database_path) as db:
        assert db.execute("SELECT status FROM attachments").fetchone()[0] == "ready"
        assert (
            db.execute(
                "SELECT attachment_device_id FROM conversations WHERE id=?", (cid,)
            ).fetchone()[0]
            is not None
        )
    assert (
        client.post(
            "/api/v1/client/chat",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        ).json()
        == result
    )
    assert app.state.runtime.service.calls == 1
    searched = client.post(
        "/api/v1/client/conversations/search",
        headers={**headers, "Content-Type": "application/json"},
        json={"query": "synthetic query"},
    )
    assert len(searched.json()["results"]) == 2
    assert searched.headers["cache-control"] == "no-store"
    assert (
        client.get(
            f"/api/v1/client/conversations/{cid}/messages", headers={"Origin": ORIGIN}
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "change,status",
    [
        ({"X-Jarvis-CSRF": ""}, 401),
        ({"Origin": "https://evil.test"}, 403),
        ({"Authorization": "Bearer invalid"}, 400),
        ({"X-Jarvis-Filename": "../secret.txt"}, 422),
        ({"X-Jarvis-Filename": "wrong.pdf"}, 422),
        ({"Content-Type": "application/octet-stream"}, 422),
        ({"Content-Length": "1048577"}, 413),
    ],
)
def test_upload_auth_metadata_denials_never_stage_source(workflows, change, status):
    client, headers, app, *_ = workflows
    response = client.post(UPLOAD, headers={**headers, **change}, content=b"fixture")
    assert response.status_code == status, response.text
    assert all(item is None for _, item in app.state.pwa_chat.uploads._items.values())


def test_cancel_overtakes_upload_duplicate_id_and_logout_cleanup(workflows):
    client, headers, app, *_ = workflows
    assert client.delete(UPLOAD, headers=headers).status_code == 200
    assert client.post(UPLOAD, headers=headers, content=b"late").status_code == 409
    second = UPLOAD[:-1] + "2"
    assert client.post(second, headers=headers, content=b"fixture").status_code == 201
    assert client.post(second, headers=headers, content=b"replacement").status_code == 409
    assert client.delete("/api/v1/sessions/current", headers=headers).status_code == 200
    assert not app.state.pwa_chat.uploads._items
    assert client.post(UPLOAD, headers=headers, content=b"no").status_code == 401


def test_stages_do_not_cross_renewed_sessions_or_exceed_count(workflows):
    client, headers, app, key, created = workflows
    for number in range(4):
        assert (
            client.post(UPLOAD[:-1] + str(number), headers=headers, content=b"fixture").status_code
            == 201
        )
    assert client.post(UPLOAD[:-1] + "9", headers=headers, content=b"over").status_code == 409
    csrf = _bootstrap(
        client,
        key,
        str(created["device_id"]),
        [scope.value for scope in ALL_SCOPES],
        nonce="R" * 22,
    )
    renewed = {**headers, "X-Jarvis-CSRF": csrf, "Content-Type": "application/json"}
    subscription = client.post(
        "/api/v1/client/subscriptions", headers=renewed, json={"topics": ["chat"]}
    ).json()
    response = client.post(
        "/api/v1/client/chat",
        headers=renewed,
        json={
            "request_id": "request:f14",
            "subscription_id": subscription["id"],
            "message": "read",
            "upload_ids": ["1" * 31 + "0"],
        },
    )
    assert response.json()["status"] == "failed"
    assert app.state.runtime.service.calls == 0


def test_search_task_scopes_bounds_read_only_controls_and_disabled_upload(workflows):
    client, headers, app, key, created = workflows
    task = client.get("/api/v1/client/tasks/task-a", headers={"Origin": ORIGIN})
    assert task.status_code == 200, task.text
    assert task.json()["nodes"][0]["status"] == "proposed"
    assert task.json()["cancellation"]["supported"] is False
    assert not any(
        key in task.text for key in ("arguments", "approval_grant_id", "output", "provenance")
    )
    assert (
        client.get("/api/v1/client/tasks/task-foreign", headers={"Origin": ORIGIN}).status_code
        == 404
    )
    assert client.get("/api/v1/client/tasks/missing", headers={"Origin": ORIGIN}).status_code == 404
    assert client.post("/api/v1/client/tasks/task-a/cancel", headers=headers).status_code == 404
    assert len(client.get("/api/v1/client/tasks?limit=1", headers={"Origin": ORIGIN}).json()) == 1
    assert client.get("/api/v1/client/tasks?offset=1", headers={"Origin": ORIGIN}).json() == []
    for payload in (
        {"query": "x" * 201},
        {"query": "x", "before": 0},
        {"query": "x", "extra": "bad"},
    ):
        assert (
            client.post(
                "/api/v1/client/conversations/search",
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
            ).status_code
            == 422
        )
    app.state.runtime.attachments.enabled = False
    assert client.post(UPLOAD, headers=headers, content=b"fixture").status_code == 503
    app.state.runtime.attachments.enabled = True
    scopes = [
        scope.value
        for scope in ALL_SCOPES
        if scope.value not in {"client.chat", "client.tasks.read"}
    ]
    csrf = _bootstrap(client, key, str(created["device_id"]), scopes, nonce="Q" * 22)
    reduced = {**headers, "X-Jarvis-CSRF": csrf}
    assert client.post(UPLOAD, headers=reduced, content=b"fixture").status_code == 403
    assert (
        client.post(
            "/api/v1/client/conversations/search",
            headers={**reduced, "Content-Type": "application/json"},
            json={"query": "x"},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/client/tasks/task-a", headers={"Origin": ORIGIN}).status_code == 403


def test_upload_admission_deadline_stream_bounds_and_revalidation(workflows, monkeypatch):
    client, headers, app, *_ = workflows
    monkeypatch.setattr("jarvis.web.UPLOAD_SECONDS", 0.01)

    async def check():
        cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
        consumed = []

        async def slow():
            consumed.append(True)
            await asyncio.sleep(0.1)
            yield b"fixture"

        async def excess():
            yield b"x" * 600000
            yield b"x" * 600000

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://testserver"
        ) as ac:
            assert (await ac.post(UPLOAD, headers=headers, content=slow())).status_code == 401
            assert not consumed
            assert (
                await ac.post(UPLOAD, headers={**headers, "Cookie": cookie}, content=slow())
            ).status_code == 408
            assert (
                await ac.post(
                    UPLOAD[:-1] + "2", headers={**headers, "Cookie": cookie}, content=excess()
                )
            ).status_code == 413
            assert all(item is None for _, item in app.state.pwa_chat.uploads._items.values())

    client.portal.call(check)
