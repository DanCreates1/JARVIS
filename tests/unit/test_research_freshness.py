from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.research import (
    Citation,
    ClaimStatus,
    KnowledgeFreshnessError,
    KnowledgeFreshnessErrorCode,
    KnowledgeRequest,
    KnowledgeRetrievalMode,
    ResearchClaim,
    ResearchReport,
    SourceRecord,
    evaluate_knowledge_report,
)

NOW = datetime(2026, 9, 12, 4, 0, tzinfo=UTC)


def report(*, checked_at: datetime, conflicting: bool = False) -> ResearchReport:
    sources = tuple(
        SourceRecord(
            id=f"source:{index}",
            host_id="host:test",
            url=f"https://example.com/{index}",
            title=f"Source {index}",
            topic="current fact",
            media_type="text/html",
            content_sha256=str(index) * 64,
            extracted_text=f"Observed fact {index}.",
            retrieved_at=checked_at - timedelta(minutes=1),
            last_checked_at=checked_at,
        )
        for index in range(1, 3 if conflicting else 2)
    )
    citations = tuple(
        Citation(source_id=source.id, locator="text:0-10", quote="Observed fact")
        for source in sources
    )
    return ResearchReport(
        objective="Find current fact",
        answer="Sources disagree." if conflicting else "Observed fact.",
        sources=sources,
        claims=(
            ResearchClaim(
                id="claim:1",
                statement="Observed fact.",
                status=ClaimStatus.CONFLICTING if conflicting else ClaimStatus.VERIFIED,
                citations=citations,
            ),
        ),
        contradictions=("Official sources disagree.",) if conflicting else (),
        generated_at=checked_at,
    )


def test_live_report_has_citations_timestamps_and_expiry() -> None:
    request = KnowledgeRequest(query="What changed?", max_age_seconds=300)
    snapshot = evaluate_knowledge_report(
        report(checked_at=NOW - timedelta(seconds=30)),
        request,
        now=NOW,
        online=True,
        retrieved_live=True,
    )
    assert snapshot.mode is KnowledgeRetrievalMode.LIVE
    assert snapshot.offline is False
    assert snapshot.citations_present is True
    assert snapshot.expired_source_ids == ()
    assert snapshot.fresh_until == NOW + timedelta(seconds=270)
    assert snapshot.source_stamps[0].url == "https://example.com/1"
    with pytest.raises(ValueError, match="while offline"):
        evaluate_knowledge_report(
            report(checked_at=NOW),
            request,
            now=NOW,
            online=False,
            retrieved_live=True,
        )


def test_offline_fallback_distinguishes_fresh_and_stale_cache() -> None:
    request = KnowledgeRequest(
        query="What changed?", max_age_seconds=300, stale_if_offline_seconds=600
    )
    fresh = evaluate_knowledge_report(
        report(checked_at=NOW - timedelta(seconds=30)), request, now=NOW, online=False
    )
    stale = evaluate_knowledge_report(
        report(checked_at=NOW - timedelta(seconds=360)), request, now=NOW, online=False
    )
    assert fresh.mode is KnowledgeRetrievalMode.FRESH_CACHE
    assert stale.mode is KnowledgeRetrievalMode.STALE_OFFLINE
    assert stale.expired_source_ids == ("source:1",)


def test_expired_online_report_requires_live_refresh() -> None:
    with pytest.raises(KnowledgeFreshnessError) as error:
        evaluate_knowledge_report(
            report(checked_at=NOW - timedelta(hours=2)),
            KnowledgeRequest(query="Current status", max_age_seconds=300),
            now=NOW,
            online=True,
        )
    assert error.value.code is KnowledgeFreshnessErrorCode.LIVE_REFRESH_REQUIRED


def test_offline_cache_fails_after_explicit_stale_allowance() -> None:
    with pytest.raises(KnowledgeFreshnessError) as error:
        evaluate_knowledge_report(
            report(checked_at=NOW - timedelta(hours=2)),
            KnowledgeRequest(
                query="Current status",
                max_age_seconds=300,
                stale_if_offline_seconds=60,
            ),
            now=NOW,
            online=False,
        )
    assert error.value.code is KnowledgeFreshnessErrorCode.OFFLINE_CACHE_EXPIRED


def test_conflicts_must_remain_visible() -> None:
    request = KnowledgeRequest(query="Which source is correct?")
    visible = evaluate_knowledge_report(
        report(checked_at=NOW, conflicting=True),
        request,
        now=NOW,
        online=True,
        retrieved_live=True,
    )
    assert visible.conflicts_visible is True

    hidden = report(checked_at=NOW, conflicting=True).model_copy(update={"contradictions": ()})
    with pytest.raises(KnowledgeFreshnessError) as error:
        evaluate_knowledge_report(hidden, request, now=NOW, online=True)
    assert error.value.code is KnowledgeFreshnessErrorCode.CONFLICT_NOT_DISCLOSED
