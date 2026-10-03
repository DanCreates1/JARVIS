from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jarvis.core import FreshnessDecision, FreshnessRoute, SensitivityClass
from jarvis.research import (
    AutomaticResearchProjector,
    Citation,
    ClaimStatus,
    ResearchClaim,
    ResearchErrorCode,
    ResearchReport,
    ResearchSearchError,
    SourceRecord,
)

NOW = datetime(2026, 9, 16, 15, tzinfo=UTC)


class FakeWorkflow:
    def __init__(self, report: ResearchReport) -> None:
        self.report = report
        self.calls: list[tuple[str, object]] = []

    async def run_volatile(self, *, host_id: str, plan: object) -> object:
        self.calls.append((host_id, plan))
        return type("Run", (), {"report": self.report})()


def _source(index: int, *, host: str | None = None) -> SourceRecord:
    hostname = host or f"source-{index}.example"
    return SourceRecord(
        id=f"source-{index}",
        host_id="host-1",
        url=f"https://{hostname}/evidence-{index}",
        publisher=hostname,
        title=f"Evidence {index}",
        topic="Current evidence",
        media_type="text/plain",
        content_sha256=f"{index}" * 64,
        extracted_text=f"Current public evidence {index}.",
        retrieved_at=NOW,
        published_at=NOW,
        last_checked_at=NOW,
    )


def _report(*sources: SourceRecord, answer: str | None = None) -> ResearchReport:
    claims = tuple(
        ResearchClaim(
            id=f"claim-{index}",
            statement=f"Supported current claim {index}.",
            status=ClaimStatus.VERIFIED,
            citations=(
                Citation(
                    source_id=source.id,
                    locator="text:0-7",
                    quote="Current",
                ),
            ),
        )
        for index, source in enumerate(sources, start=1)
    )
    rendered = answer or "\n\n".join(
        f"Supported current claim {index}. [source:{source.id}]"
        for index, source in enumerate(sources, start=1)
    )
    return ResearchReport(
        objective="What changed?",
        answer=rendered,
        sources=tuple(sources),
        claims=claims,
        generated_at=NOW,
    )


@pytest.mark.asyncio
async def test_projects_live_timestamped_citations_without_pending_storage() -> None:
    workflow = FakeWorkflow(_report(_source(1), _source(2)))
    projector = AutomaticResearchProjector(workflow, host_id="host-1")  # type: ignore[arg-type]

    projection = await projector.project(
        "Compare current evidence.",
        FreshnessDecision(
            route=FreshnessRoute.MULTI_SOURCE,
            reason="Current corroboration required.",
        ),
    )

    assert projection.sensitivity is SensitivityClass.PUBLIC
    assert projection.source == "volatile-automatic-research"
    assert projection.source_ids == ("source-1", "source-2")
    assert "evidence_status=sufficient" in projection.content
    assert "generated_at=2026-09-16T15:00:00+00:00" in projection.content
    assert "https://source-1.example/evidence-1" in projection.content
    assert "[source:source-1]" in projection.content
    assert "[source:source-1](<https://source-1.example/evidence-1>)" in projection.content
    assert len(workflow.calls) == 1
    assert workflow.calls[0][0] == "host-1"


@pytest.mark.asyncio
async def test_multi_source_same_host_is_explicitly_insufficient() -> None:
    workflow = FakeWorkflow(
        _report(_source(1, host="same.example"), _source(2, host="same.example"))
    )
    projector = AutomaticResearchProjector(workflow, host_id="host-1")  # type: ignore[arg-type]

    projection = await projector.project(
        "Compare current claim.",
        FreshnessDecision(
            route=FreshnessRoute.MULTI_SOURCE,
            reason="Current corroboration required.",
        ),
    )

    assert "evidence_status=insufficient" in projection.content
    assert "independent_source_hosts=1" in projection.content
    assert "Do not claim live verification" in projection.content


@pytest.mark.asyncio
async def test_non_live_route_cannot_trigger_research() -> None:
    workflow = FakeWorkflow(_report(_source(1)))
    projector = AutomaticResearchProjector(workflow, host_id="host-1")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="live-evidence route"):
        await projector.project(
            "Explain photosynthesis.",
            FreshnessDecision(route=FreshnessRoute.STATIC, reason="Stable knowledge."),
        )

    assert workflow.calls == []


@pytest.mark.asyncio
async def test_projection_is_bounded_without_losing_source_mapping() -> None:
    source = _source(1)
    workflow = FakeWorkflow(_report(source, answer=("Long supported point.\n\n" * 4_000)))
    projector = AutomaticResearchProjector(  # type: ignore[arg-type]
        workflow,
        host_id="host-1",
        max_projection_chars=12_000,
    )

    projection = await projector.project(
        "What is current?",
        FreshnessDecision(
            route=FreshnessRoute.WEB_REQUIRED,
            reason="Live evidence required.",
        ),
    )

    assert len(projection.content) <= 12_000
    assert "https://source-1.example/evidence-1" in projection.content


@pytest.mark.asyncio
async def test_projection_never_truncates_a_cited_claim_mid_sentence() -> None:
    source = _source(1)
    oversized_point = "Current claim " + ("details " * 1_600) + "[source:source-1]"
    workflow = FakeWorkflow(_report(source, answer=oversized_point))
    projector = AutomaticResearchProjector(  # type: ignore[arg-type]
        workflow,
        host_id="host-1",
        max_projection_chars=12_000,
    )

    projection = await projector.project(
        "What is current?",
        FreshnessDecision(route=FreshnessRoute.WEB_REQUIRED, reason="Live evidence required."),
    )

    assert "Cited answer omitted" in projection.content
    assert "[source:source-1] title=" in projection.content
    assert "Current claim details" not in projection.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    (
        "What is the latest news in my private account?",
        "What is the latest news about this?",
        "Latest news?",
    ),
)
async def test_private_or_uncertain_request_is_denied_before_workflow(query: str) -> None:
    workflow = FakeWorkflow(_report(_source(1)))
    projector = AutomaticResearchProjector(workflow, host_id="host-1")  # type: ignore[arg-type]

    with pytest.raises(ResearchSearchError) as caught:
        await projector.project(
            query,
            FreshnessDecision(
                route=FreshnessRoute.WEB_REQUIRED,
                reason="Live evidence required.",
            ),
        )

    assert caught.value.code is ResearchErrorCode.PRIVACY_DENIED
    assert workflow.calls == []
