"""Bounded provider-neutral Phase 5 research orchestration."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from itertools import islice
from urllib.parse import urldefrag

from pydantic import ValidationError

from jarvis.research.adapters import ResearchSearchError
from jarvis.research.citation import CitationValidator
from jarvis.research.contracts import (
    DocumentFetcher,
    DocumentParser,
    ResearchSynthesizer,
    SearchProvider,
)
from jarvis.research.fetch import ResearchFetchError
from jarvis.research.models import (
    FetchRequest,
    ResearchErrorCode,
    ResearchFailure,
    ResearchPlan,
    ResearchRunResult,
    ResearchStage,
    ResearchSynthesisDraft,
    ResearchSynthesisRequest,
    SearchRequest,
    SearchResult,
    SourceRecord,
)


class ResearchOrchestrationError(RuntimeError):
    """A bounded research run could not produce a reviewable report."""

    def __init__(
        self,
        code: ResearchErrorCode,
        message: str,
        *,
        failures: Sequence[ResearchFailure] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.failures = tuple(failures)


class BoundedResearchOrchestrator:
    """Run plan/search/fetch/parse/synthesize/review within fixed host bounds."""

    def __init__(
        self,
        *,
        search_provider: SearchProvider,
        fetcher: DocumentFetcher,
        parser: DocumentParser,
        synthesizer: ResearchSynthesizer,
        citation_validator: CitationValidator | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._search_provider = search_provider
        self._fetcher = fetcher
        self._parser = parser
        self._synthesizer = synthesizer
        self._citation_validator = citation_validator or CitationValidator()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run(self, *, host_id: str, plan: ResearchPlan) -> ResearchRunResult:
        try:
            async with asyncio.timeout(plan.deadline_seconds):
                return await self._run_bounded(host_id=host_id, plan=plan)
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise ResearchOrchestrationError(
                ResearchErrorCode.TIMEOUT,
                "research run exceeded its total deadline",
            ) from exc

    async def _run_bounded(self, *, host_id: str, plan: ResearchPlan) -> ResearchRunResult:
        failures: list[ResearchFailure] = []
        sources: list[SourceRecord] = []
        seen_candidate_urls: set[str] = set()
        seen_final_urls: set[str] = set()
        queries_attempted = 0
        search_results_considered = 0
        fetches_attempted = 0
        remaining_source_chars = plan.max_total_source_chars

        for query in plan.questions[: plan.max_queries]:
            if len(sources) >= plan.max_sources or fetches_attempted >= plan.max_fetches:
                break
            queries_attempted += 1
            request = SearchRequest(
                query=query,
                limit=20,
                allowed_domains=plan.allowed_domains,
            )
            try:
                raw_results = await self._search_provider.search(request)
            except asyncio.CancelledError:
                raise
            except ResearchSearchError as exc:
                failures.append(_failure(ResearchStage.SEARCH, exc.code, query, str(exc)))
                continue
            except Exception as exc:
                failures.append(
                    _failure(
                        ResearchStage.SEARCH,
                        ResearchErrorCode.UNAVAILABLE,
                        query,
                        f"search provider failed: {type(exc).__name__}",
                    )
                )
                continue

            for raw_result in islice(raw_results, request.limit):
                if len(sources) >= plan.max_sources or fetches_attempted >= plan.max_fetches:
                    break
                search_results_considered += 1
                try:
                    result = SearchResult.model_validate(raw_result)
                except (ValidationError, TypeError, ValueError):
                    failures.append(
                        _failure(
                            ResearchStage.SEARCH,
                            ResearchErrorCode.PROTOCOL_ERROR,
                            query,
                            "search provider returned an invalid result",
                        )
                    )
                    continue
                candidate_url = urldefrag(result.url).url
                if candidate_url in seen_candidate_urls:
                    continue
                seen_candidate_urls.add(candidate_url)
                fetches_attempted += 1
                try:
                    fetched = await self._fetcher.fetch(
                        FetchRequest(
                            url=result.url,
                            allowed_domains=plan.allowed_domains,
                            limits=plan.fetch_limits,
                        )
                    )
                except asyncio.CancelledError:
                    raise
                except ResearchFetchError as exc:
                    failures.append(
                        _failure(ResearchStage.FETCH, exc.code, candidate_url, str(exc))
                    )
                    continue
                except Exception as exc:
                    failures.append(
                        _failure(
                            ResearchStage.FETCH,
                            ResearchErrorCode.UNAVAILABLE,
                            candidate_url,
                            f"document fetcher failed: {type(exc).__name__}",
                        )
                    )
                    continue
                try:
                    parsed = self._parser.parse(fetched)
                except asyncio.CancelledError:
                    raise
                except ResearchFetchError as exc:
                    failures.append(
                        _failure(ResearchStage.PARSE, exc.code, candidate_url, str(exc))
                    )
                    continue
                except Exception as exc:
                    failures.append(
                        _failure(
                            ResearchStage.PARSE,
                            ResearchErrorCode.PROTOCOL_ERROR,
                            candidate_url,
                            f"document parser failed: {type(exc).__name__}",
                        )
                    )
                    continue

                final_url = urldefrag(parsed.source_url).url
                if final_url in seen_final_urls:
                    continue
                if remaining_source_chars <= 0:
                    break
                source_char_limit = min(plan.max_chars_per_source, remaining_source_chars)
                extracted_text = parsed.text[:source_char_limit]
                if not extracted_text:
                    continue
                source = SourceRecord(
                    id=_source_id(final_url, fetched.body),
                    host_id=host_id,
                    url=final_url,
                    publisher=parsed.publisher or result.publisher,
                    title=parsed.title,
                    topic=plan.objective[:500],
                    media_type=fetched.media_type,
                    content_sha256=hashlib.sha256(fetched.body).hexdigest(),
                    extracted_text=extracted_text,
                    retrieved_at=fetched.retrieved_at,
                    published_at=parsed.published_at or result.published_at,
                    last_checked_at=fetched.retrieved_at,
                    etag=fetched.etag,
                    last_modified=fetched.last_modified,
                )
                sources.append(source)
                seen_final_urls.add(final_url)
                remaining_source_chars -= len(extracted_text)

        if not sources:
            raise ResearchOrchestrationError(
                ResearchErrorCode.UNAVAILABLE,
                "research run acquired no usable sources",
                failures=failures,
            )

        synthesis_request = ResearchSynthesisRequest(
            objective=plan.objective,
            questions=plan.questions,
            sources=tuple(sources),
            max_claims=plan.max_claims,
        )
        try:
            raw_draft = await self._synthesizer.synthesize(synthesis_request)
            draft = ResearchSynthesisDraft.model_validate(raw_draft)
        except asyncio.CancelledError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise ResearchOrchestrationError(
                ResearchErrorCode.PROTOCOL_ERROR,
                f"research synthesizer returned an invalid draft: {str(exc)[:300]}",
                failures=failures,
            ) from exc
        except Exception as exc:
            failures.append(
                _failure(
                    ResearchStage.SYNTHESIZE,
                    ResearchErrorCode.UNAVAILABLE,
                    plan.objective,
                    f"research synthesizer failed: {type(exc).__name__}",
                )
            )
            raise ResearchOrchestrationError(
                ResearchErrorCode.UNAVAILABLE,
                "research synthesis failed",
                failures=failures,
            ) from exc
        if len(draft.claims) > plan.max_claims:
            raise ResearchOrchestrationError(
                ResearchErrorCode.PROTOCOL_ERROR,
                "research synthesizer exceeded claim limit",
                failures=failures,
            )
        report, validation = self._citation_validator.validate(
            objective=plan.objective,
            draft=draft,
            sources=sources,
            generated_at=self._clock(),
        )
        return ResearchRunResult(
            plan=plan,
            report=report,
            validation=validation,
            failures=tuple(failures),
            queries_attempted=queries_attempted,
            search_results_considered=search_results_considered,
            fetches_attempted=fetches_attempted,
        )


def _source_id(url: str, body: bytes) -> str:
    digest = hashlib.sha256(url.encode("utf-8") + b"\0" + body).hexdigest()
    return f"source-{digest[:32]}"


def _failure(
    stage: ResearchStage,
    code: ResearchErrorCode,
    target: str,
    detail: str,
) -> ResearchFailure:
    return ResearchFailure(
        stage=stage,
        code=code,
        target=target[:2_048] or "unknown",
        detail=detail[:500] or "research operation failed",
    )
