"""Host-approved Phase 5 research, revalidation, and question workflows."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jarvis.research.contracts import DocumentFetcher, DocumentParser
from jarvis.research.fetch import ResearchFetchError
from jarvis.research.models import (
    FetchRequest,
    PendingResearchRun,
    ResearchApprovalReceipt,
    ResearchPlan,
    ResearchRevalidationReceipt,
    ResearchRunResult,
    ResearchStorageApproval,
    SourceState,
)
from jarvis.research.orchestrator import BoundedResearchOrchestrator
from jarvis.research.sqlite_store import (
    ResearchNotFoundError,
    ResearchStateError,
    SQLiteResearchStore,
)


class ResearchWorkflow:
    """Keep unapproved reports volatile and expose exact host-controlled transitions."""

    def __init__(
        self,
        *,
        orchestrator: BoundedResearchOrchestrator,
        store: SQLiteResearchStore,
        fetcher: DocumentFetcher,
        parser: DocumentParser,
        pending_ttl_seconds: int = 900,
        max_pending_runs: int = 10,
        clock: Callable[[], datetime] | None = None,
        closeables: Sequence[object] = (),
    ) -> None:
        if not 30 <= pending_ttl_seconds <= 3_600:
            raise ValueError("pending research TTL must be between 30 and 3600 seconds")
        if not 1 <= max_pending_runs <= 100:
            raise ValueError("max pending research runs must be between 1 and 100")
        self._orchestrator = orchestrator
        self._store = store
        self._fetcher = fetcher
        self._parser = parser
        self._pending_ttl = timedelta(seconds=pending_ttl_seconds)
        self._max_pending_runs = max_pending_runs
        self._clock = clock or (lambda: datetime.now(UTC))
        self._pending: dict[str, PendingResearchRun] = {}
        self._lock = asyncio.Lock()
        self._closeables = tuple(closeables)

    async def run(self, *, host_id: str, plan: ResearchPlan) -> PendingResearchRun:
        result = await self._orchestrator.run(host_id=host_id, plan=plan)
        now = _aware(self._clock())
        pending = PendingResearchRun(
            id=str(uuid4()),
            host_id=host_id,
            report_sha256=research_report_digest(result),
            result=result,
            expires_at=now + self._pending_ttl,
        )
        async with self._lock:
            self._purge_expired(now)
            if len(self._pending) >= self._max_pending_runs:
                oldest_id = next(iter(self._pending))
                del self._pending[oldest_id]
            self._pending[pending.id] = pending
        return pending

    async def approve(self, approval: ResearchStorageApproval) -> ResearchApprovalReceipt:
        now = _aware(approval.approved_at)
        async with self._lock:
            self._purge_expired(now)
            pending = self._pending.get(approval.pending_run_id)
            if pending is None or pending.host_id != approval.host_id:
                raise ResearchNotFoundError("pending research run not found")
            if pending.report_sha256 != approval.expected_report_sha256:
                raise ResearchStateError("pending research report changed")
            # Consume before durable work. A failed write requires a new reviewed run.
            del self._pending[pending.id]
        stored = await self._store.store_approved_report(
            host_id=approval.host_id,
            report=pending.result.report,
            report_sha256=pending.report_sha256,
            interface=approval.interface,
            approved_at=approval.approved_at,
            supersedes_report_id=approval.supersedes_report_id,
        )
        return ResearchApprovalReceipt(
            pending_run_id=pending.id,
            report_sha256=pending.report_sha256,
            stored=True,
            report_id=stored.id,
            source_count=len(stored.source_ids),
            claim_count=len(stored.claim_ids),
            unanswered_count=len(pending.result.report.unanswered_questions),
        )

    async def deny(
        self, *, host_id: str, pending_run_id: str, expected_report_sha256: str
    ) -> ResearchApprovalReceipt:
        now = _aware(self._clock())
        async with self._lock:
            self._purge_expired(now)
            pending = self._pending.get(pending_run_id)
            if pending is None or pending.host_id != host_id:
                raise ResearchNotFoundError("pending research run not found")
            if pending.report_sha256 != expected_report_sha256:
                raise ResearchStateError("pending research report changed")
            del self._pending[pending.id]
        return ResearchApprovalReceipt(
            pending_run_id=pending.id,
            report_sha256=pending.report_sha256,
            stored=False,
        )

    async def revalidate_source(
        self, *, host_id: str, source_id: str
    ) -> ResearchRevalidationReceipt:
        source = await self._store.get_source(host_id=host_id, source_id=source_id)
        if source is None:
            raise ResearchNotFoundError("research source not found")
        try:
            fetched = await self._fetcher.fetch(FetchRequest(url=source.url))
            parsed = self._parser.parse(fetched)
        except asyncio.CancelledError:
            raise
        except ResearchFetchError as exc:
            checked_at = _aware(self._clock())
            unavailable = await self._store.mark_source_unavailable(
                host_id=host_id,
                source_id=source.id,
                reason_code=f"revalidation_{exc.code.value}"[:100],
                now=checked_at,
            )
            return ResearchRevalidationReceipt(
                requested_source_id=source.id,
                current_source_id=unavailable.id,
                changed=False,
                state=SourceState.UNAVAILABLE,
                checked_at=checked_at,
            )
        current = await self._store.record_document(
            host_id=host_id,
            topic=source.topic,
            fetched=fetched,
            parsed=parsed,
            usage_notes=source.usage_notes,
        )
        return ResearchRevalidationReceipt(
            requested_source_id=source.id,
            current_source_id=current.id,
            changed=current.id != source.id,
            state=current.state,
            checked_at=current.last_checked_at,
        )

    async def close(self) -> None:
        async with self._lock:
            self._pending.clear()
        seen: set[int] = set()
        for closeable in self._closeables:
            if id(closeable) in seen:
                continue
            seen.add(id(closeable))
            close = getattr(closeable, "close", None)
            if close is not None:
                await close()

    def _purge_expired(self, now: datetime) -> None:
        expired = [run_id for run_id, run in self._pending.items() if run.expires_at <= now]
        for run_id in expired:
            del self._pending[run_id]


def research_report_digest(result: ResearchRunResult) -> str:
    encoded = result.report.model_dump_json().encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("research workflow clock must return a timezone-aware timestamp")
    return value.astimezone(UTC)
