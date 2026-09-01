from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from fastapi.testclient import TestClient

from jarvis.bootstrap import RuntimeComponents
from jarvis.config import Settings
from jarvis.core import (
    AssistantRequest,
    ModelRole,
    ReasoningLevel,
    RoutingDecision,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeResult,
    RuntimeStatus,
    RuntimeStreamFrame,
    SensitivityClass,
)
from jarvis.memory import (
    MemoryCategory,
    MemoryManager,
    ProvenanceSource,
    SQLiteConversationStore,
    SQLiteMemoryStore,
    untrusted_provenance,
)
from jarvis.web import create_app


class FakeService:
    def __init__(self) -> None:
        self.requests: list[AssistantRequest] = []

    async def run(self, request: AssistantRequest) -> RuntimeResult:
        self.requests.append(request)
        routing = RoutingDecision(
            chosen_role=ModelRole.FAST,
            reason="safe simple",
            sensitivity=SensitivityClass.PUBLIC,
            reasoning_level=ReasoningLevel.NONE,
            fallback_chain=(ModelRole.LOCAL,),
        )
        event = RuntimeEvent(
            sequence=1,
            type=RuntimeEventType.ROUTING_DECIDED,
            conversation_id="web-conversation",
            routing=routing,
        )
        return RuntimeResult(
            conversation_id="web-conversation",
            status=RuntimeStatus.COMPLETED,
            reply="Ready.",
            events=(event,),
        )

    async def stream(self, request: AssistantRequest) -> AsyncIterator[RuntimeStreamFrame]:
        self.requests.append(request)
        event = RuntimeEvent(sequence=1, type=RuntimeEventType.PROVIDER_REQUESTED)
        yield RuntimeStreamFrame(event=event)
        yield RuntimeStreamFrame(
            result=RuntimeResult(status=RuntimeStatus.COMPLETED, reply="Streamed.")
        )


class FakeRouter:
    def __init__(self) -> None:
        self.providers = {ModelRole.LOCAL: object()}

    async def close(self) -> None:
        return None


def test_loopback_web_chat_stream_memory_deletion_and_security_headers(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    created: dict[str, object] = {}

    async def runtime_factory(_settings: Settings) -> RuntimeComponents:
        store = SQLiteConversationStore(tmp_path / "web.db")
        await store.initialize()
        conversation = await store.create_conversation()
        service = FakeService()
        provider = FakeRouter()
        components = RuntimeComponents(
            settings=settings,
            store=store,
            provider=provider,  # type: ignore[arg-type]
            service=service,  # type: ignore[arg-type]
        )
        created.update(
            components=components,
            conversation_id=conversation.id,
            service=service,
        )
        return components

    app = create_app(settings, runtime_factory=runtime_factory)
    with TestClient(app) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert "Loopback browser chat" in index.text
        assert index.headers["cache-control"] == "no-store"
        assert index.headers["x-frame-options"] == "DENY"

        health = client.get("/api/health").json()
        assert health == {
            "status": "ready",
            "cloud_policy": "privacy_aware",
            "max_cloud_cost_usd": 0.0,
            "roles": ["local"],
        }

        chat = client.post(
            "/api/chat",
            json={"message": "Hello", "model_role": "fast", "reasoning_level": "none"},
        )
        assert chat.status_code == 200
        assert chat.json()["reply"] == "Ready."

        stream = client.post("/api/chat/stream", json={"message": "Hello stream"})
        assert stream.status_code == 200
        assert '"event"' in stream.text and '"result"' in stream.text

        memory = client.post(
            "/api/memories",
            json={"kind": "note", "content": "Remember this", "provenance": "user"},
        )
        assert memory.status_code == 201
        memory_id = memory.json()["id"]
        assert client.get("/api/memories").json()[0]["content"] == "Remember this"
        assert client.delete(f"/api/memories/{memory_id}").json() == {"deleted": True}
        assert client.delete(f"/api/memories/{memory_id}").status_code == 404

        assert client.get("/api/audit").json() == []
        conversation_id = created["conversation_id"]
        assert client.delete(f"/api/conversations/{conversation_id}").json() == {"deleted": True}
        assert client.delete(f"/api/conversations/{conversation_id}").status_code == 404

    components = created["components"]
    assert isinstance(components, RuntimeComponents)
    assert components.store._connection is None
    service = created["service"]
    assert isinstance(service, FakeService)
    assert service.requests[0].requested_model_role is ModelRole.FAST


def test_phase4_web_memory_inspection_confirmation_correction_and_deletion(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    created: dict[str, object] = {}
    host_id = "host-web-memory"

    async def runtime_factory(_settings: Settings) -> RuntimeComponents:
        store = SQLiteConversationStore(tmp_path / "phase4-web.db")
        memory_store = SQLiteMemoryStore(tmp_path / "phase4-web.db")
        await store.initialize()
        await memory_store.initialize()
        conversation = await store.create_conversation()
        candidate = await memory_store.propose(
            host_id=host_id,
            category=MemoryCategory.PROFILE,
            key="profile.web-candidate",
            content="Synthetic browser candidate",
            confidence=0.9,
            provenance=untrusted_provenance(
                source_type=ProvenanceSource.MESSAGE,
                source_id="web-message",
                source_label="synthetic browser message",
                conversation_id=conversation.id,
                message_id="web-message",
                source_content="Synthetic browser candidate",
            ),
        )
        components = RuntimeComponents(
            settings=settings,
            store=store,
            provider=FakeRouter(),  # type: ignore[arg-type]
            service=FakeService(),  # type: ignore[arg-type]
            memory_store=memory_store,
            memory=MemoryManager(memory_store, host_id=host_id),
            memory_host_id=host_id,
        )
        created.update(candidate=candidate, conversation=conversation)
        return components

    app = create_app(settings, runtime_factory=runtime_factory)
    with TestClient(app) as client:
        committed = client.post(
            "/api/memories",
            json={
                "category": "profile",
                "content": "Synthetic browser profile",
                "key": "profile.browser",
                "provenance": "explicit browser fixture",
            },
        )
        assert committed.status_code == 201
        committed_item = committed.json()
        assert committed_item["state"] == "committed"
        assert client.get("/api/memories").json()[0]["host_id"] == host_id
        search = client.get("/api/memory/search", params={"query": "browser profile"})
        assert search.status_code == 200
        assert search.json()[0]["item"]["id"] == committed_item["id"]

        correction = client.post(
            f"/api/memory/{committed_item['id']}/correct",
            json={
                "expected_version": committed_item["version"],
                "content": "Corrected synthetic browser profile",
            },
        )
        assert correction.status_code == 200
        assert correction.json()["supersedes_id"] == committed_item["id"]
        assert (
            client.post(
                f"/api/memory/{committed_item['id']}/correct",
                json={"expected_version": 1, "content": "stale"},
            ).status_code
            == 409
        )

        candidate = created["candidate"]
        promoted = client.post(
            f"/api/memory/candidates/{candidate.id}/promote",  # type: ignore[union-attr]
            json={
                "expected_version": candidate.version,  # type: ignore[union-attr]
                "expected_content_sha256": candidate.content_sha256,  # type: ignore[union-attr]
            },
        )
        assert promoted.status_code == 200
        assert promoted.json()["state"] == "committed"

        corrected_id = correction.json()["id"]
        assert client.delete(f"/api/memories/{corrected_id}").json() == {"deleted": True}
        assert client.delete(f"/api/memories/{corrected_id}").status_code == 404
        conversation = created["conversation"]
        assert client.delete(f"/api/conversations/{conversation.id}").json() == {  # type: ignore[union-attr]
            "deleted": True
        }

    assert client.app.state.runtime.memory_store._connection is None
