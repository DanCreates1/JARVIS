from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
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
from jarvis.research import (
    Citation,
    CitationValidationReceipt,
    ClaimStatus,
    PendingResearchRun,
    ResearchApprovalReceipt,
    ResearchClaim,
    ResearchInterface,
    ResearchPlan,
    ResearchReport,
    ResearchRunResult,
    SourceRecord,
    SQLiteResearchStore,
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
            event=RuntimeEvent(
                sequence=2,
                type=RuntimeEventType.ASSISTANT_DELTA,
                content_delta="Streamed.",
            )
        )
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
        assert '"type":"assistant_delta"' in stream.text
        assert '"content_delta":"Streamed."' in stream.text

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


def _web_pending_research() -> PendingResearchRun:
    now = datetime(2026, 9, 6, 12, tzinfo=UTC)
    source = SourceRecord(
        id="source-web",
        host_id="host-web-research",
        url="https://example.com/source",
        title="Web source",
        topic="Alpha",
        media_type="text/plain",
        content_sha256="a" * 64,
        extracted_text="Alpha evidence.",
        retrieved_at=now,
        last_checked_at=now,
    )
    claim = ResearchClaim(
        id="claim-web",
        statement="Alpha.",
        status=ClaimStatus.VERIFIED,
        citations=(Citation(source_id=source.id, locator="text:0-5", quote="Alpha"),),
    )
    plan = ResearchPlan(objective="Research Alpha", questions=("What is Alpha?",))
    result = ResearchRunResult(
        plan=plan,
        report=ResearchReport(
            objective=plan.objective,
            answer="Alpha. [source:source-web]",
            sources=(source,),
            claims=(claim,),
            generated_at=now,
        ),
        validation=CitationValidationReceipt(
            source_count=1,
            claim_count=1,
            material_claim_count=1,
            citation_count=1,
            quoted_word_count=1,
        ),
        queries_attempted=1,
        search_results_considered=1,
        fetches_attempted=1,
    )
    return PendingResearchRun(
        id="pending-web",
        host_id="host-web-research",
        report_sha256="b" * 64,
        result=result,
        expires_at=now.replace(hour=13),
    )


def test_phase5_browser_research_run_explicit_approval_and_denial_interfaces(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    decisions: list[str] = []

    class FakeResearch:
        async def run(self, **_kwargs: object) -> PendingResearchRun:
            return _web_pending_research()

        async def deny(self, **_kwargs: object) -> ResearchApprovalReceipt:
            decisions.append("deny")
            return ResearchApprovalReceipt(
                pending_run_id="pending-web", report_sha256="b" * 64, stored=False
            )

        async def approve(self, approval) -> ResearchApprovalReceipt:  # type: ignore[no-untyped-def]
            assert approval.interface is ResearchInterface.LOCAL_WEB
            decisions.append("approve")
            return ResearchApprovalReceipt(
                pending_run_id="pending-web",
                report_sha256="b" * 64,
                stored=True,
                report_id="report-web",
                source_count=1,
                claim_count=1,
            )

        async def close(self) -> None:
            return None

    async def runtime_factory(_settings: Settings) -> RuntimeComponents:
        store = SQLiteConversationStore(tmp_path / "web-research.db")
        research_store = SQLiteResearchStore(tmp_path / "web-research.db")
        await store.initialize()
        await research_store.initialize()
        return RuntimeComponents(
            settings=settings,
            store=store,
            provider=FakeRouter(),  # type: ignore[arg-type]
            service=FakeService(),  # type: ignore[arg-type]
            research_store=research_store,
            research=FakeResearch(),  # type: ignore[arg-type]
            memory_host_id="host-web-research",
        )

    app = create_app(settings, runtime_factory=runtime_factory)
    with TestClient(app) as client:
        assert "Results stay volatile until exact local approval" in client.get("/").text
        first = client.post(
            "/api/research/runs",
            json={"objective": "Research Alpha", "questions": ["What is Alpha?"]},
        )
        assert first.status_code == 200
        pending = first.json()
        denied = client.post(
            f"/api/research/runs/{pending['id']}/approval",
            json={"decision": "deny", "expected_report_sha256": pending["report_sha256"]},
        )
        assert denied.status_code == 200
        assert denied.json()["stored"] is False

        pending = client.post(
            "/api/research/runs",
            json={"objective": "Research Alpha", "questions": ["What is Alpha?"]},
        ).json()
        approved = client.post(
            f"/api/research/runs/{pending['id']}/approval",
            json={"decision": "approve", "expected_report_sha256": pending["report_sha256"]},
        )
        assert approved.status_code == 200
        assert approved.json()["report_id"] == "report-web"
        assert client.get("/api/research/reports").json() == []

    assert decisions == ["deny", "approve"]


def test_phase5_browser_inspect_search_and_exact_delete_controls(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    identifiers: dict[str, str] = {}

    async def runtime_factory(_settings: Settings) -> RuntimeComponents:
        database = tmp_path / "web-research-controls.db"
        store = SQLiteConversationStore(database)
        research_store = SQLiteResearchStore(database)
        await store.initialize()
        await research_store.initialize()
        pending = _web_pending_research()
        stored = await research_store.store_approved_report(
            host_id=pending.host_id,
            report=pending.result.report,
            report_sha256=pending.report_sha256,
            interface=ResearchInterface.LOCAL_WEB,
            approved_at=datetime(2026, 9, 6, 12, tzinfo=UTC),
        )
        identifiers["report"] = stored.id
        identifiers["source"] = stored.source_ids[0]
        return RuntimeComponents(
            settings=settings,
            store=store,
            provider=FakeRouter(),  # type: ignore[arg-type]
            service=FakeService(),  # type: ignore[arg-type]
            research_store=research_store,
            memory_host_id=pending.host_id,
        )

    app = create_app(settings, runtime_factory=runtime_factory)
    with TestClient(app) as client:
        reports = client.get("/api/research/reports")
        assert reports.status_code == 200
        assert reports.json()[0]["id"] == identifiers["report"]
        report = client.get(f"/api/research/reports/{identifiers['report']}")
        assert "[source:" in report.json()["answer"]
        searched = client.get("/api/research/sources", params={"query": "Alpha"})
        assert searched.status_code == 200
        assert searched.json()[0]["id"] == identifiers["source"]
        mismatch = client.delete(
            f"/api/research/sources/{identifiers['source']}",
            params={"confirm_source_id": "wrong-source"},
        )
        assert mismatch.status_code == 409
        deleted = client.delete(
            f"/api/research/sources/{identifiers['source']}",
            params={"confirm_source_id": identifiers["source"]},
        )
        assert deleted.status_code == 200
        assert deleted.json()["source_rows"] == 1
        assert client.get(f"/api/research/reports/{identifiers['report']}").status_code == 404
