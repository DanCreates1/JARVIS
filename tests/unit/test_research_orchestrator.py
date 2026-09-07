from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from jarvis.research import (
    BoundedResearchOrchestrator,
    Citation,
    CitationValidationCode,
    CitationValidationError,
    CitationValidator,
    ClaimStatus,
    FetchedDocument,
    FetchRequest,
    ResearchAnswerPoint,
    ResearchClaim,
    ResearchErrorCode,
    ResearchFetchError,
    ResearchOrchestrationError,
    ResearchPlan,
    ResearchSynthesisDraft,
    ResearchSynthesisRequest,
    SearchRequest,
    SearchResult,
    SourceRecord,
    UntrustedDocumentParser,
)

NOW = datetime(2026, 9, 6, 12, tzinfo=UTC)


class FakeSearchProvider:
    def __init__(self, results: dict[str, Sequence[object]]) -> None:
        self.results = results
        self.requests: list[SearchRequest] = []

    async def search(self, request: SearchRequest) -> Sequence[SearchResult]:
        self.requests.append(request)
        return self.results.get(request.query, ())  # type: ignore[return-value]

    async def close(self) -> None:
        return None


class FakeDocumentFetcher:
    def __init__(self, responses: dict[str, bytes | BaseException]) -> None:
        self.responses = responses
        self.requests: list[FetchRequest] = []

    async def fetch(self, request: FetchRequest) -> FetchedDocument:
        self.requests.append(request)
        response = self.responses[request.url]
        if isinstance(response, BaseException):
            raise response
        return FetchedDocument(
            requested_url=request.url,
            final_url=request.url,
            media_type="text/plain",
            body=response,
            retrieved_at=NOW,
            status_code=200,
        )

    async def close(self) -> None:
        return None


class EvidenceSynthesizer:
    def __init__(self, *, bad_quote: bool = False) -> None:
        self.bad_quote = bad_quote
        self.requests: list[ResearchSynthesisRequest] = []

    async def synthesize(self, request: ResearchSynthesisRequest) -> ResearchSynthesisDraft:
        self.requests.append(request)
        claims: list[ResearchClaim] = []
        points: list[ResearchAnswerPoint] = []
        for index, source in enumerate(request.sources, start=1):
            quote = "fabricated provider evidence" if self.bad_quote else source.extracted_text
            end = (
                len(source.extracted_text)
                if not self.bad_quote
                else min(5, len(source.extracted_text))
            )
            claim_id = f"claim-{index}"
            claims.append(
                ResearchClaim(
                    id=claim_id,
                    statement=f"Supported finding {index}",
                    status=ClaimStatus.VERIFIED,
                    citations=(
                        Citation(
                            source_id=source.id,
                            locator=f"text:0-{end}",
                            quote=quote,
                        ),
                    ),
                )
            )
            points.append(
                ResearchAnswerPoint(
                    text=f"Supported finding {index}.",
                    claim_ids=(claim_id,),
                )
            )
        return ResearchSynthesisDraft(points=tuple(points), claims=tuple(claims))

    async def close(self) -> None:
        return None


class BlockingSearchProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def search(self, request: SearchRequest) -> Sequence[SearchResult]:
        self.started.set()
        await asyncio.Event().wait()
        return ()

    async def close(self) -> None:
        return None


def result(url: str, title: str) -> SearchResult:
    return SearchResult(url=url, title=title, publisher="Fixture publisher")


def orchestrator(
    search: object,
    fetcher: FakeDocumentFetcher,
    synthesizer: EvidenceSynthesizer,
) -> BoundedResearchOrchestrator:
    return BoundedResearchOrchestrator(
        search_provider=search,  # type: ignore[arg-type]
        fetcher=fetcher,
        parser=UntrustedDocumentParser(),
        synthesizer=synthesizer,
        clock=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_bounded_pipeline_uses_fake_providers_and_validates_nearby_citations() -> None:
    search = FakeSearchProvider(
        {
            "question one": (result("https://one.example/source", "One"),),
            "question two": (result("https://two.example/source", "Two"),),
        }
    )
    fetcher = FakeDocumentFetcher(
        {
            "https://one.example/source": b"First exact evidence.",
            "https://two.example/source": b"Second exact evidence.",
        }
    )
    synthesizer = EvidenceSynthesizer()
    plan = ResearchPlan(
        objective="Compare fixture evidence",
        questions=("question one", "question two"),
        max_queries=2,
        max_sources=2,
        max_fetches=2,
    )

    run = await orchestrator(search, fetcher, synthesizer).run(host_id="host-1", plan=plan)

    assert run.queries_attempted == 2
    assert run.fetches_attempted == 2
    assert run.validation.citation_count == 2
    assert run.validation.quoted_word_count == 6
    assert len(run.report.sources) == 2
    assert all(source.host_id == "host-1" and source.untrusted for source in run.report.sources)
    assert all(f"[source:{source.id}]" in run.report.answer for source in run.report.sources)
    assert len(synthesizer.requests) == 1
    assert synthesizer.requests[0].max_claims == plan.max_claims
    assert run.failures == ()


@pytest.mark.asyncio
async def test_fetch_attempts_and_queries_stop_at_plan_limits_after_safe_failures() -> None:
    urls = [f"https://fixture.example/{index}" for index in range(4)]
    search = FakeSearchProvider(
        {
            "first": tuple(result(url, str(index)) for index, url in enumerate(urls)),
            "never called": (result("https://unused.example/source", "Unused"),),
        }
    )
    fetcher = FakeDocumentFetcher(
        {
            urls[0]: ResearchFetchError(ResearchErrorCode.PAYWALL, "payment required"),
            urls[1]: ResearchFetchError(ResearchErrorCode.UNAVAILABLE, "source unavailable"),
            urls[2]: b"Usable exact evidence.",
            urls[3]: b"Must not be fetched.",
        }
    )
    plan = ResearchPlan(
        objective="Bound failures",
        questions=("first", "never called"),
        max_queries=1,
        max_sources=1,
        max_fetches=3,
    )

    run = await orchestrator(search, fetcher, EvidenceSynthesizer()).run(
        host_id="host-1", plan=plan
    )

    assert [request.query for request in search.requests] == ["first"]
    assert [request.url for request in fetcher.requests] == urls[:3]
    assert run.fetches_attempted == 3
    assert [failure.code for failure in run.failures] == [
        ResearchErrorCode.PAYWALL,
        ResearchErrorCode.UNAVAILABLE,
    ]


@pytest.mark.asyncio
async def test_invalid_search_result_is_skipped_without_expanding_fetch_budget() -> None:
    search = FakeSearchProvider(
        {
            "fixture": (
                {"url": "not-a-url"},
                result("https://fixture.example/good", "Good"),
            )
        }
    )
    fetcher = FakeDocumentFetcher({"https://fixture.example/good": b"Exact evidence."})
    plan = ResearchPlan(
        objective="Reject malformed result",
        questions=("fixture",),
        max_sources=1,
        max_fetches=1,
    )

    run = await orchestrator(search, fetcher, EvidenceSynthesizer()).run(
        host_id="host-1", plan=plan
    )

    assert len(fetcher.requests) == 1
    assert run.failures[0].code is ResearchErrorCode.PROTOCOL_ERROR
    assert run.search_results_considered == 2


@pytest.mark.asyncio
async def test_fake_synthesizer_cannot_fabricate_quote_or_locator() -> None:
    url = "https://fixture.example/source"
    search = FakeSearchProvider({"fixture": (result(url, "Fixture"),)})
    fetcher = FakeDocumentFetcher({url: b"Exact evidence only."})
    plan = ResearchPlan(
        objective="Validate evidence",
        questions=("fixture",),
        max_sources=1,
        max_fetches=1,
    )

    with pytest.raises(CitationValidationError) as caught:
        await orchestrator(search, fetcher, EvidenceSynthesizer(bad_quote=True)).run(
            host_id="host-1", plan=plan
        )

    assert CitationValidationCode.QUOTE_MISMATCH in {issue.code for issue in caught.value.issues}


def test_validator_enforces_aggregate_25_word_quote_limit_per_source() -> None:
    text = " ".join(f"word{index}" for index in range(26))
    source = SourceRecord(
        id="source-1",
        host_id="host-1",
        url="https://fixture.example/source",
        title="Fixture",
        topic="fixture",
        media_type="text/plain",
        content_sha256="a" * 64,
        extracted_text=text,
        retrieved_at=NOW,
        last_checked_at=NOW,
    )
    split = text.index("word13")
    claims = (
        ResearchClaim(
            id="claim-1",
            statement="First half",
            status=ClaimStatus.VERIFIED,
            citations=(
                Citation(
                    source_id=source.id, locator=f"text:0-{split - 1}", quote=text[: split - 1]
                ),
            ),
        ),
        ResearchClaim(
            id="claim-2",
            statement="Second half",
            status=ClaimStatus.VERIFIED,
            citations=(
                Citation(
                    source_id=source.id, locator=f"text:{split}-{len(text)}", quote=text[split:]
                ),
            ),
        ),
    )
    draft = ResearchSynthesisDraft(
        points=(
            ResearchAnswerPoint(text="First half.", claim_ids=("claim-1",)),
            ResearchAnswerPoint(text="Second half.", claim_ids=("claim-2",)),
        ),
        claims=claims,
    )

    with pytest.raises(CitationValidationError) as caught:
        CitationValidator().validate(objective="fixture", draft=draft, sources=(source,))

    assert CitationValidationCode.SOURCE_QUOTE_BUDGET_EXCEEDED in {
        issue.code for issue in caught.value.issues
    }


def test_uncited_answer_claim_requires_and_renders_explicit_uncertainty() -> None:
    source = SourceRecord(
        id="source-1",
        host_id="host-1",
        url="https://fixture.example/source",
        title="Fixture",
        topic="fixture",
        media_type="text/plain",
        content_sha256="a" * 64,
        extracted_text="Background evidence.",
        retrieved_at=NOW,
        last_checked_at=NOW,
    )
    point = ResearchAnswerPoint(text="Possible interpretation.", claim_ids=("claim-1",))
    uncertain = ResearchClaim(
        id="claim-1",
        statement="Possible interpretation",
        status=ClaimStatus.HYPOTHESIS,
        uncertainty="No direct source evidence establishes this interpretation.",
    )
    report, receipt = CitationValidator().validate(
        objective="fixture",
        draft=ResearchSynthesisDraft(points=(point,), claims=(uncertain,)),
        sources=(source,),
        generated_at=NOW,
    )

    assert receipt.citation_count == 0
    assert "[uncertainty: No direct source evidence" in report.answer

    unsupported = uncertain.model_copy(update={"uncertainty": ""})
    with pytest.raises(CitationValidationError) as caught:
        CitationValidator().validate(
            objective="fixture",
            draft=ResearchSynthesisDraft(points=(point,), claims=(unsupported,)),
            sources=(source,),
        )
    assert CitationValidationCode.UNCERTAINTY_OMITTED in {
        issue.code for issue in caught.value.issues
    }


@pytest.mark.asyncio
async def test_total_deadline_is_enforced_and_reported() -> None:
    search = BlockingSearchProvider()
    plan = ResearchPlan(
        objective="Timeout fixture",
        questions=("fixture",),
        max_sources=1,
        max_fetches=1,
        deadline_seconds=0.01,
    )

    with pytest.raises(ResearchOrchestrationError) as caught:
        await orchestrator(search, FakeDocumentFetcher({}), EvidenceSynthesizer()).run(
            host_id="host-1", plan=plan
        )

    assert caught.value.code is ResearchErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_host_cancellation_propagates_without_conversion() -> None:
    search = BlockingSearchProvider()
    plan = ResearchPlan(
        objective="Cancellation fixture",
        questions=("fixture",),
        max_sources=1,
        max_fetches=1,
    )
    task = asyncio.create_task(
        orchestrator(search, FakeDocumentFetcher({}), EvidenceSynthesizer()).run(
            host_id="host-1", plan=plan
        )
    )
    await asyncio.wait_for(search.started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
