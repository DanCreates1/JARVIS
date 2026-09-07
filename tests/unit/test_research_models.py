from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jarvis.research import (
    Citation,
    ClaimStatus,
    ResearchClaim,
    ResearchReport,
    SearchRequest,
    SourceRecord,
)


def source(source_id: str = "source-1") -> SourceRecord:
    return SourceRecord(
        id=source_id,
        host_id="host-1",
        url=f"https://example.com/{source_id}",
        title="Primary source",
        topic="test topic",
        media_type="text/html",
        content_sha256="a" * 64,
        extracted_text="Bounded source text",
        retrieved_at=datetime.now(UTC),
        last_checked_at=datetime.now(UTC),
    )


def test_search_request_normalizes_query() -> None:
    request = SearchRequest(query="  current   topic\n evidence  ")
    assert request.query == "current topic evidence"


def test_material_factual_claim_requires_citation() -> None:
    with pytest.raises(ValidationError, match="material factual claims require a citation"):
        ResearchClaim(id="claim-1", statement="A factual claim", status=ClaimStatus.VERIFIED)


def test_conflicting_claim_requires_two_distinct_sources() -> None:
    with pytest.raises(ValidationError, match="at least two distinct sources"):
        ResearchClaim(
            id="claim-1",
            statement="Sources conflict",
            status=ClaimStatus.CONFLICTING,
            citations=(Citation(source_id="source-1", locator="section 1"),),
        )


def test_inference_requires_explicit_uncertainty() -> None:
    with pytest.raises(ValidationError, match="explicit uncertainty"):
        ResearchClaim(
            id="claim-1",
            statement="Likely implication",
            status=ClaimStatus.LIKELY,
            citations=(Citation(source_id="source-1", locator="section 1"),),
            is_inference=True,
        )


def test_citation_quote_is_bounded_to_25_words() -> None:
    with pytest.raises(ValidationError, match="25-word"):
        Citation(source_id="source-1", locator="paragraph 1", quote="word " * 26)


def test_acquired_source_cannot_be_marked_trusted() -> None:
    values = source().model_dump()
    values["untrusted"] = False
    with pytest.raises(ValidationError, match="must remain untrusted"):
        SourceRecord.model_validate(values)


def test_report_rejects_unknown_claim_source() -> None:
    claim = ResearchClaim(
        id="claim-1",
        statement="Supported statement",
        status=ClaimStatus.VERIFIED,
        citations=(Citation(source_id="source-missing", locator="section 1"),),
    )
    with pytest.raises(ValidationError, match="unknown sources"):
        ResearchReport(
            objective="Answer question",
            answer="Answer with citation.",
            sources=(source(),),
            claims=(claim,),
            generated_at=datetime.now(UTC),
        )


def test_report_accepts_complete_source_links() -> None:
    claim = ResearchClaim(
        id="claim-1",
        statement="Supported statement",
        status=ClaimStatus.VERIFIED,
        citations=(Citation(source_id="source-1", locator="section 1"),),
    )
    report = ResearchReport(
        objective="Answer question",
        answer="Answer with citation.",
        sources=(source(),),
        claims=(claim,),
        generated_at=datetime.now(UTC),
    )
    assert report.claims == (claim,)
