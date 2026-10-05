from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jarvis.bootstrap import build_runtime
from jarvis.config import Settings
from jarvis.web import create_app
from tests.integration.test_web import FakeService


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        attachments_enabled=True,
        cloud_policy="local_only",
        groq_api_key=None,
        gemini_api_key=None,
        nvidia_api_key=None,
        current_context_enabled=False,
    )

    async def factory(settings):
        components = await build_runtime(settings)
        components.service = FakeService()
        return components

    with TestClient(create_app(settings, runtime_factory=factory)) as active:
        yield active


def upload(client):
    response = client.post(
        "/api/attachments?filename=public.txt",
        content=b"synthetic private facts",
        headers={"content-type": "text/plain"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_web_upload_chat_metadata_list_inspect_delete_and_headers(client):
    record = upload(client)
    assert record["status"] == "ready" and "body" not in record
    path = f"/api/conversations/{record['conversation_id']}/attachments"
    assert client.get(path).json()[0]["id"] == record["id"]
    inspected = client.get(path + "/" + record["id"])
    assert inspected.status_code == 200 and inspected.headers["cache-control"] == "no-store"
    response = client.post(
        "/api/chat",
        json={
            "message": "read attachment",
            "conversation_id": record["conversation_id"],
            "attachment_ids": [record["id"]],
        },
    )
    assert response.status_code == 200
    request = client.app.state.runtime.service.requests[-1]
    assert request.attachment_ids == (record["id"],)
    assert request.metadata["interface"] == "browser"
    streamed = client.post(
        "/api/chat/stream",
        json={
            "message": "read",
            "conversation_id": record["conversation_id"],
            "attachment_ids": [record["id"]],
        },
    )
    assert streamed.status_code == 200 and "data:" in streamed.text
    assert client.delete(path + "/" + record["id"]).status_code == 200
    assert client.get(path + "/" + record["id"]).status_code == 404
    assert not client.get(path).json()


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "https://evil.example"},
        {"origin": "null"},
        {"sec-fetch-site": "cross-site"},
        {"host": "private-host.ts.net"},
        {"x-forwarded-for": "127.0.0.1"},
        {"x-forwarded-proto": "https"},
        {"cookie": "session=synthetic"},
        {"authorization": "Bearer synthetic"},
    ],
)
def test_attachment_routes_deny_remote_browser_proxy_and_auth(headers, client):
    record = upload(client)
    paths = [
        ("POST", "/api/attachments?filename=other.txt"),
        ("GET", f"/api/conversations/{record['conversation_id']}/attachments"),
        ("DELETE", f"/api/conversations/{record['conversation_id']}/attachments/{record['id']}"),
    ]
    for method, path in paths:
        response = client.request(
            method, path, headers={"content-type": "text/plain", **headers}, content=b"synthetic"
        )
        assert response.status_code == 403
    payload = {
        "message": "read",
        "conversation_id": record["conversation_id"],
        "attachment_ids": [record["id"]],
    }
    assert client.post("/api/chat", json=payload, headers=headers).status_code == 403
    assert client.post("/api/chat/stream", json=payload, headers=headers).status_code == 403


def test_metadata_body_scope_and_disabled_fail_closed(client):
    for name, content_type in [
        ("../a.txt", "text/plain"),
        ("a.exe", "text/plain"),
        ("a.txt", "text/html"),
    ]:
        assert (
            client.post(
                "/api/attachments",
                params={"filename": name},
                content=b"synthetic",
                headers={"content-type": content_type},
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/api/attachments?filename=a.txt", content=b"", headers={"content-type": "text/plain"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/attachments?filename=a.txt",
            content=b"x",
            headers={"content-type": "text/plain", "content-length": "5242881"},
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/attachments?filename=a.txt&conversation_id=missing",
            content=b"x",
            headers={"content-type": "text/plain"},
        ).status_code
        == 404
    )
    record = upload(client)
    assert client.get(f"/api/conversations/other/attachments/{record['id']}").status_code == 404
    assert (
        client.post(
            "/api/chat", json={"message": "read", "attachment_ids": [record["id"]]}
        ).status_code
        == 422
    )
    client.app.state.runtime.settings.attachments_enabled = False
    assert (
        client.post(
            "/api/attachments?filename=a.txt", content=b"x", headers={"content-type": "text/plain"}
        ).status_code
        == 503
    )


def test_browser_ui_uses_safe_text_and_attachment_controls(client):
    html = client.get("/")
    assert 'id="attachment-file"' in html.text
    assert "selectedAttachments" in html.text and "label.textContent" in html.text
    assert "attachment_ids:[...selectedAttachments]" in html.text
    # HTML must preserve JavaScript escapes; Python-expanded line breaks break the whole page.
    assert "buffer.split('\\n\\n')" in html.text
    assert "block.split('\\n')" in html.text
    assert "Content-Security-Policy" in html.headers
