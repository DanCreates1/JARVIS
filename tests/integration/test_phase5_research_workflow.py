from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jarvis.research import (
    Citation,
    CitationValidationReceipt,
    ClaimStatus,
    FetchedDocument,
    ResearchClaim,
    ResearchErrorCode,
    ResearchFetchError,
    ResearchInterface,
    ResearchNotFoundError,
    ResearchPlan,
    ResearchReport,
    ResearchRunResult,
    ResearchStateError,
    ResearchStorageApproval,
    ResearchWorkflow,
    SourceRecord,
    SQLiteResearchStore,
    UnansweredQuestionStatus,
    UntrustedDocumentParser,
    research_report_digest,
)

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)
HOST = "host-workflow"


def run_result() -> ResearchRunResult:
    source = SourceRecord(
        id="source-pending",
        host_id=HOST,
        url="https://example.com/source",
        title="Fixture source",
        topic="Alpha",
        media_type="text/plain",
        content_sha256="a" * 64,
        extracted_text="Alpha evidence.",
        retrieved_at=NOW,
        last_checked_at=NOW,
    )
    claim = ResearchClaim(
        id="claim-pending",
        statement="Alpha is supported.",
        status=ClaimStatus.VERIFIED,
        citations=(Citation(source_id=source.id, locator="text:0-5", quote="Alpha"),),
    )
    plan = ResearchPlan(objective="Research Alpha", questions=("What is Alpha?",))
    return ResearchRunResult(
        plan=plan,
        report=ResearchReport(
            objective=plan.objective,
            answer="Alpha is supported. [source:source-pending]",
            sources=(source,),
            claims=(claim,),
            unanswered_questions=("What remains unknown?",),
            generated_at=NOW,
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


class FakeOrchestrator:
    def __init__(self, result: ResearchRunResult) -> None:
        self.result = result

    async def run(self, *, host_id: str, plan: ResearchPlan) -> ResearchRunResult:
        assert host_id == HOST
        assert plan.objective == self.result.plan.objective
        return self.result


class BlockingOrchestrator:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def run(self, **_kwargs):  # type: ignore[no-untyped-def]
        self.started.set()
        await asyncio.Event().wait()


class RevalidationFetcher:
    def __init__(self, *, text: str | None = None, error: ResearchFetchError | None = None) -> None:
        self.text = text
        self.error = error

    async def fetch(self, request):  # type: ignore[no-untyped-def]
        if self.error is not None:
            raise self.error
        assert self.text is not None
        return FetchedDocument(
            requested_url=request.url,
            final_url=request.url,
            media_type="text/plain",
            body=self.text.encode(),
            retrieved_at=NOW,
            status_code=200,
        )

    async def close(self) -> None:
        return None


def workflow(
    store: SQLiteResearchStore,
    orchestrator: object,
    *,
    fetcher: RevalidationFetcher | None = None,
) -> ResearchWorkflow:
    return ResearchWorkflow(
        orchestrator=orchestrator,  # type: ignore[arg-type]
        store=store,
        fetcher=fetcher or RevalidationFetcher(text="Alpha evidence."),
        parser=UntrustedDocumentParser(),
        clock=lambda: NOW,
    )


def approval(pending, *, digest: str | None = None):  # type: ignore[no-untyped-def]
    return ResearchStorageApproval(
        host_id=HOST,
        pending_run_id=pending.id,
        expected_report_sha256=digest or pending.report_sha256,
        interface=ResearchInterface.TEST,
        approved_at=NOW,
    )


@pytest.mark.asyncio
async def test_research_storage_requires_exact_approval_and_never_promotes_memory(
    tmp_path: Path,
) -> None:
    database = tmp_path / "research.db"
    async with SQLiteResearchStore(database) as store:
        service = workflow(store, FakeOrchestrator(run_result()))
        pending = await service.run(host_id=HOST, plan=run_result().plan)
        assert await store.list_sources(host_id=HOST) == ()
        assert await store.list_reports(host_id=HOST) == ()
        with pytest.raises(ResearchStateError, match="changed"):
            await service.approve(approval(pending, digest="b" * 64))
        receipt = await service.approve(approval(pending))
        assert receipt.stored is True
        report = (await store.list_reports(host_id=HOST))[0]
        assert "source-pending" not in report.answer
        assert report.source_ids[0] in report.answer
        questions = await store.list_unanswered_questions(host_id=HOST)
        assert [question.question for question in questions] == ["What remains unknown?"]

    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT count(*) FROM memory_items").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_approval_denial_discards_content_and_cannot_be_replayed(tmp_path: Path) -> None:
    async with SQLiteResearchStore(tmp_path / "research.db") as store:
        service = workflow(store, FakeOrchestrator(run_result()))
        pending = await service.run(host_id=HOST, plan=run_result().plan)
        receipt = await service.deny(
            host_id=HOST,
            pending_run_id=pending.id,
            expected_report_sha256=pending.report_sha256,
        )
        assert receipt.stored is False
        assert await store.list_sources(host_id=HOST) == ()
        assert await store.list_reports(host_id=HOST) == ()
        with pytest.raises(ResearchNotFoundError):
            await service.approve(approval(pending))


@pytest.mark.asyncio
async def test_restart_loses_pending_approval_but_preserves_approved_report(tmp_path: Path) -> None:
    database = tmp_path / "research.db"
    async with SQLiteResearchStore(database) as store:
        first = workflow(store, FakeOrchestrator(run_result()))
        abandoned = await first.run(host_id=HOST, plan=run_result().plan)
        approved = await first.run(host_id=HOST, plan=run_result().plan)
        receipt = await first.approve(approval(approved))

    async with SQLiteResearchStore(database) as reopened:
        restarted = workflow(reopened, FakeOrchestrator(run_result()))
        with pytest.raises(ResearchNotFoundError):
            await restarted.approve(approval(abandoned))
        stored = await reopened.get_report(host_id=HOST, report_id=receipt.report_id or "")
        assert stored is not None
        assert stored.report_sha256 == research_report_digest(run_result())


@pytest.mark.asyncio
async def test_workflow_cancellation_propagates_without_pending_or_storage(tmp_path: Path) -> None:
    async with SQLiteResearchStore(tmp_path / "research.db") as store:
        blocker = BlockingOrchestrator()
        service = workflow(store, blocker)
        task = asyncio.create_task(service.run(host_id=HOST, plan=run_result().plan))
        await asyncio.wait_for(blocker.started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await store.list_reports(host_id=HOST) == ()


@pytest.mark.asyncio
async def test_revalidation_update_failure_and_unanswered_question_workflows(
    tmp_path: Path,
) -> None:
    async with SQLiteResearchStore(tmp_path / "research.db") as store:
        service = workflow(store, FakeOrchestrator(run_result()))
        pending = await service.run(host_id=HOST, plan=run_result().plan)
        receipt = await service.approve(approval(pending))
        report = await store.get_report(host_id=HOST, report_id=receipt.report_id or "")
        assert report is not None

        changed_service = workflow(
            store,
            FakeOrchestrator(run_result()),
            fetcher=RevalidationFetcher(text="Beta evidence."),
        )
        changed = await changed_service.revalidate_source(
            host_id=HOST, source_id=report.source_ids[0]
        )
        assert changed.changed is True
        assert changed.current_source_id != changed.requested_source_id

        failed_service = workflow(
            store,
            FakeOrchestrator(run_result()),
            fetcher=RevalidationFetcher(
                error=ResearchFetchError(ResearchErrorCode.UNAVAILABLE, "offline")
            ),
        )
        failed = await failed_service.revalidate_source(
            host_id=HOST, source_id=changed.current_source_id
        )
        assert failed.state.value == "unavailable"

        question = (await store.list_unanswered_questions(host_id=HOST))[0]
        answered = await store.update_unanswered_question(
            host_id=HOST,
            question_id=question.id,
            expected_version=question.version,
            status=UnansweredQuestionStatus.ANSWERED,
            answer_claim_id=report.claim_ids[0],
            interface=ResearchInterface.TEST,
            now=NOW,
        )
        assert answered.status is UnansweredQuestionStatus.ANSWERED
        with pytest.raises(ResearchStateError):
            await store.update_unanswered_question(
                host_id=HOST,
                question_id=question.id,
                expected_version=question.version,
                status=UnansweredQuestionStatus.DISMISSED,
                interface=ResearchInterface.TEST,
            )


@pytest.mark.asyncio
async def test_approved_updated_report_supersedes_exact_current_report(tmp_path: Path) -> None:
    async with SQLiteResearchStore(tmp_path / "research.db") as store:
        first_service = workflow(store, FakeOrchestrator(run_result()))
        first_pending = await first_service.run(host_id=HOST, plan=run_result().plan)
        first_receipt = await first_service.approve(approval(first_pending))
        first_id = first_receipt.report_id or ""

        original = run_result()
        updated_report = original.report.model_copy(
            update={"answer": "Updated Alpha answer. [source:source-pending]"}
        )
        updated_result = original.model_copy(update={"report": updated_report})
        updated_service = workflow(store, FakeOrchestrator(updated_result))
        updated_pending = await updated_service.run(host_id=HOST, plan=updated_result.plan)
        updated_receipt = await updated_service.approve(
            ResearchStorageApproval(
                host_id=HOST,
                pending_run_id=updated_pending.id,
                expected_report_sha256=updated_pending.report_sha256,
                interface=ResearchInterface.TEST,
                approved_at=NOW,
                supersedes_report_id=first_id,
            )
        )

        old_report = await store.get_report(host_id=HOST, report_id=first_id)
        new_report = await store.get_report(host_id=HOST, report_id=updated_receipt.report_id or "")
        assert old_report is not None and old_report.state.value == "superseded"
        assert new_report is not None and new_report.supersedes_id == first_id
