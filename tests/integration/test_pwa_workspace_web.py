from __future__ import annotations

import json
import sqlite3

import pytest

from jarvis.planning import TaskEventType, TaskStatus
from jarvis.planning.models import NodeStatus
from tests.integration.test_phase8_pwa_web import ALL_SCOPES, ORIGIN, _bootstrap
from tests.integration.test_pwa_workflows_web import UPLOAD, terminal
from tests.integration.test_pwa_workflows_web import workflows as workflows


def sent(client, headers, request_id, **fields):
    headers = {**headers, "Content-Type": "application/json"}
    subscription = getattr(client, "workspace_subscription", None)
    if subscription is None:
        subscription = client.post(
            "/api/v1/client/subscriptions", headers=headers, json={"topics": ["chat"]}
        ).json()["id"]
        client.workspace_subscription = subscription
    payload = {
        "request_id": request_id,
        "subscription_id": subscription,
        "message": "synthetic private marker",
        **fields,
    }
    response = client.post("/api/v1/client/chat", headers=headers, json=payload)
    assert response.status_code in {200, 202}, response.text
    return payload, terminal(client, headers, request_id)


def test_workspace_metadata_auth_csrf_conflict_private_isolation_and_no_history_mutation(workflows):
    client, headers, app, key, created = workflows
    _, result = sent(client, headers, "request:library")
    cid = result["conversation_id"]
    route = f"/api/v1/client/conversations/{cid}/metadata"
    edit = {
        "revision": 0,
        "title": "<script>untrusted title</script>",
        "pinned": True,
        "archived": True,
    }
    auth = {**headers, "Content-Type": "application/json"}
    assert client.post(route, headers={**auth, "X-Jarvis-CSRF": ""}, json=edit).status_code == 401
    assert (
        client.post(route, headers={**auth, "Origin": "https://evil.test"}, json=edit).status_code
        == 403
    )
    assert client.post(route, headers=auth, json=edit).status_code == 200
    assert client.post(route, headers=auth, json=edit).status_code == 409
    archived = client.post(
        "/api/v1/client/conversations/library", headers=auth, json={"archived": True}
    ).json()
    assert archived["conversations"][0]["title"] == edit["title"]
    assert client.get(
        f"/api/v1/client/conversations/{cid}/messages", headers={"Origin": ORIGIN}
    ).json()["messages"]
    assert (
        client.post(
            route, headers=auth, json={**edit, "revision": 1, "archived": False}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/client/conversations/library",
            headers=auth,
            json={"offset": 20, "revision": archived["revision"]},
        ).status_code
        == 409
    )
    for invalid in ({"offset": -1}, {"offset": 100001}, {"limit": 10000}):
        assert (
            client.post(
                "/api/v1/client/conversations/library", headers=auth, json=invalid
            ).status_code
            == 422
        )
    with sqlite3.connect(app.state.runtime.store.database_path) as db:
        db.execute("UPDATE conversations SET email_private=1 WHERE id=?", (cid,))
    assert client.post(route, headers=auth, json={**edit, "revision": 2}).status_code == 404
    assert not client.post("/api/v1/client/conversations/library", headers=auth, json={}).json()[
        "conversations"
    ]
    csrf = _bootstrap(
        client,
        key,
        str(created["device_id"]),
        [scope.value for scope in ALL_SCOPES if scope.value != "client.chat"],
        nonce="Z" * 22,
    )
    assert client.post(route, headers={**auth, "X-Jarvis-CSRF": csrf}, json=edit).status_code == 403


def test_attachment_metadata_reuse_replay_expiry_and_no_raw_download(workflows):
    client, headers, app, *_ = workflows
    assert client.post(UPLOAD, headers=headers, content=b"synthetic source").status_code == 201
    _, result = sent(client, headers, "request:upload", upload_ids=["1" * 32])
    cid = result["conversation_id"]
    route = f"/api/v1/client/conversations/{cid}/attachments"
    page = client.get(route, headers={"Origin": ORIGIN})
    assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
    attachment = page.json()["attachments"][0]
    assert attachment["status"] == "ready" and attachment["request_ids"] == ["request:upload"]
    assert "synthetic source" not in page.text
    assert not any(key in page.text for key in ('"body"', '"image"', '"sha256"', '"chunks"'))
    identifier = attachment["id"]
    payload, reused = sent(
        client, headers, "request:reuse", conversation_id=cid, attachment_ids=[identifier]
    )
    assert reused["status"] == "completed"
    calls = app.state.runtime.service.calls
    assert (
        client.post(
            "/api/v1/client/chat",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        ).json()
        == reused
    )
    assert app.state.runtime.service.calls == calls
    _, denied = sent(
        client, headers, "request:foreign", attachment_ids=[]
    )  # new owned conversation
    _, cross = sent(
        client,
        headers,
        "request:cross",
        conversation_id=denied["conversation_id"],
        attachment_ids=[identifier],
    )
    assert cross["status"] == "failed" and app.state.runtime.service.calls == calls + 1
    with sqlite3.connect(app.state.runtime.store.database_path) as db:
        db.execute(
            "UPDATE attachments SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (identifier,),
        )
    assert (
        client.get(route, headers={"Origin": ORIGIN}).json()["attachments"][0]["status"]
        == "expired"
    )
    _, expired = sent(
        client, headers, "request:expired", conversation_id=cid, attachment_ids=[identifier]
    )
    assert expired["error"]["code"] == "attachment_unavailable"
    assert client.get(
        f"/api/v1/client/attachments/{identifier}", headers={"Origin": ORIGIN}
    ).status_code in {404, 405}
    for fields in (
        {"attachment_ids": [identifier]},
        {"conversation_id": cid, "attachment_ids": [identifier] * 2},
        {
            "conversation_id": cid,
            "attachment_ids": [identifier],
            "upload_ids": [str(i) * 32 for i in range(4)],
        },
    ):
        invalid = {**payload, **fields, "conversation_id": fields.get("conversation_id")}
        assert (
            client.post(
                "/api/v1/client/chat",
                headers={**headers, "Content-Type": "application/json"},
                json=invalid,
            ).status_code
            == 422
        )
    with sqlite3.connect(app.state.runtime.store.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM attachments").fetchone()[0] == 1
        db.execute("UPDATE conversations SET attachment_device_id=NULL WHERE id=?", (cid,))
    assert client.get(route, headers={"Origin": ORIGIN}).status_code == 404
    assert "synthetic source" not in json.dumps(
        [r.detail for r in client.portal.call(app.state.runtime.store.list_audit_records)]
    )


def test_task_timeline_filters_sort_pagination_restart_and_sanitized_events(workflows):
    client, headers, app, key, created = workflows
    store = app.state.runtime.task_store

    async def populate():
        record = await store.get_task(
            host_id=created.get("host_id", "host:pwa-web"), task_id="task-a"
        )
        for _ in range(56):
            record = await store.save(
                record.model_copy(
                    update={
                        "status": TaskStatus.RUNNING,
                        "nodes": (
                            record.nodes[0].model_copy(update={"status": NodeStatus.VERIFYING}),
                        ),
                    }
                ),
                expected_version=record.version,
                event_type=TaskEventType.NODE_VERIFYING,
                node_id="first",
                reason_code="secret-private-argument",
            )

    client.portal.call(populate)
    response = client.get(
        "/api/v1/client/tasks?status=verifying&sort=oldest&limit=1", headers={"Origin": ORIGIN}
    )
    assert response.status_code == 200 and response.json()[0]["verifying_nodes"] == 1
    revision = response.headers["X-Jarvis-Task-Revision"]
    assert client.get("/api/v1/client/tasks?status=failed", headers={"Origin": ORIGIN}).json() == []
    timeline = client.get(
        "/api/v1/client/tasks/task-a/events?limit=50", headers={"Origin": ORIGIN}
    ).json()
    assert len(timeline["events"]) == 50 and timeline["has_more"]
    earlier = client.get(
        f"/api/v1/client/tasks/task-a/events?before={timeline['next_before']}",
        headers={"Origin": ORIGIN},
    ).json()
    assert len(earlier["events"]) == 7 and not earlier["has_more"]
    assert max(e["sequence"] for e in earlier["events"]) < min(
        e["sequence"] for e in timeline["events"]
    )
    assert "secret-private-argument" not in json.dumps(timeline)
    assert not any(
        key in json.dumps(timeline) for key in ("arguments", "output", "grant", "provenance")
    )
    assert (
        client.get(
            "/api/v1/client/tasks/task-foreign/events", headers={"Origin": ORIGIN}
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/client/tasks/task-a/events?limit=51", headers={"Origin": ORIGIN}
        ).status_code
        == 422
    )
    # Reopen the real SQLite adapter; persisted timeline and ownership survive restart.
    client.portal.call(store.close)
    client.portal.call(store.initialize)
    assert (
        client.get("/api/v1/client/tasks/task-a", headers={"Origin": ORIGIN}).json()["timeline"]
        == timeline
    )
    client.portal.call(populate)
    assert (
        client.get(
            f"/api/v1/client/tasks?offset=1&revision={revision}", headers={"Origin": ORIGIN}
        ).status_code
        == 409
    )
    for operation in ("cancel", "run", "approve", "resume"):
        assert (
            client.post(f"/api/v1/client/tasks/task-a/{operation}", headers=headers).status_code
            == 404
        )
    csrf = _bootstrap(
        client,
        key,
        str(created["device_id"]),
        [s.value for s in ALL_SCOPES if s.value != "client.tasks.read"],
        nonce="T" * 22,
    )
    assert (
        client.get("/api/v1/client/tasks/task-a/events", headers={"Origin": ORIGIN}).status_code
        == 403
    )
    assert csrf


@pytest.mark.parametrize("ending", ["expired", "revoked", "logout"])
def test_workspace_routes_fail_closed_after_identity_ends(workflows, ending):
    client, headers, app, *_ = workflows
    _, result = sent(client, headers, "request:identity")
    cid = result["conversation_id"]
    auth = {**headers, "Content-Type": "application/json"}
    if ending == "logout":
        assert client.delete("/api/v1/sessions/current", headers=headers).status_code == 200
    else:
        with sqlite3.connect(app.state.runtime.store.database_path) as db:
            if ending == "expired":
                db.execute("UPDATE remote_sessions SET expires_at='2000-01-01T00:00:00+00:00'")
            else:
                db.execute(
                    "UPDATE remote_devices SET state='revoked',"
                    "revoked_at='2000-01-01T00:00:00+00:00'"
                )
    for method, path, body in (
        ("POST", "/api/v1/client/conversations/library", {}),
        (
            "POST",
            f"/api/v1/client/conversations/{cid}/metadata",
            {"revision": 0, "title": "denied", "pinned": True, "archived": True},
        ),
        ("GET", f"/api/v1/client/conversations/{cid}/attachments", None),
        ("GET", "/api/v1/client/tasks/task-a/events", None),
    ):
        response = client.request(
            method, path, headers=auth, **({"json": body} if body is not None else {})
        )
        assert response.status_code == 401, response.text
    with sqlite3.connect(app.state.runtime.store.database_path) as db:
        assert (
            db.execute(
                "SELECT revision FROM pwa_conversation_owners WHERE conversation_id=?", (cid,)
            ).fetchone()[0]
            == 0
        )
