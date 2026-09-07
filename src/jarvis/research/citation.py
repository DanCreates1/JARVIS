"""Deterministic review and rendering for source-backed research drafts."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

from jarvis.research.models import (
    CitationValidationCode,
    CitationValidationIssue,
    CitationValidationReceipt,
    ClaimStatus,
    ResearchClaim,
    ResearchReport,
    ResearchSynthesisDraft,
    SourceRecord,
    SourceState,
)

_TEXT_LOCATOR = re.compile(r"^text:(0|[1-9][0-9]*)-(0|[1-9][0-9]*)$")
_UNVALIDATED_CITATION = re.compile(r"(?:https?://|\[source:[^\]]*\])", re.IGNORECASE)
_MAX_QUOTED_WORDS_PER_SOURCE = 25


class CitationValidationError(RuntimeError):
    """A synthesis draft failed deterministic claim-to-source validation."""

    def __init__(self, issues: Sequence[CitationValidationIssue]) -> None:
        if not issues:
            raise ValueError("citation validation error requires at least one issue")
        self.issues = tuple(issues)
        super().__init__(f"research citation validation failed with {len(self.issues)} issue(s)")


class CitationValidator:
    """Validate exact source spans, evidence coverage, and nearby answer markers."""

    def validate(
        self,
        *,
        objective: str,
        draft: ResearchSynthesisDraft,
        sources: Sequence[SourceRecord],
        generated_at: datetime | None = None,
    ) -> tuple[ResearchReport, CitationValidationReceipt]:
        issues: list[CitationValidationIssue] = []
        source_by_id = {source.id: source for source in sources}
        claim_by_id = {claim.id: claim for claim in draft.claims}
        quoted_words: dict[str, int] = defaultdict(int)

        for claim in draft.claims:
            if not claim.citations and not claim.uncertainty.strip():
                issues.append(
                    CitationValidationIssue(
                        code=CitationValidationCode.UNCERTAINTY_OMITTED,
                        claim_id=claim.id,
                        detail="uncited answer claim requires explicit uncertainty",
                    )
                )
            for citation in claim.citations:
                source = source_by_id.get(citation.source_id)
                if source is None:
                    issues.append(
                        CitationValidationIssue(
                            code=CitationValidationCode.UNKNOWN_SOURCE,
                            claim_id=claim.id,
                            source_id=citation.source_id,
                            detail="citation references a source outside the acquired evidence set",
                        )
                    )
                    continue
                if source.state is not SourceState.ACTIVE:
                    issues.append(
                        CitationValidationIssue(
                            code=CitationValidationCode.INACTIVE_SOURCE,
                            claim_id=claim.id,
                            source_id=source.id,
                            detail="citation source is not active",
                        )
                    )
                if citation.quote is None:
                    issues.append(
                        CitationValidationIssue(
                            code=CitationValidationCode.MISSING_QUOTE,
                            claim_id=claim.id,
                            source_id=source.id,
                            detail="answer claim citation requires an exact source quote",
                        )
                    )
                self._validate_span(
                    claim_id=claim.id,
                    source=source,
                    locator=citation.locator,
                    quote=citation.quote,
                    issues=issues,
                )
                if citation.quote is not None:
                    quoted_words[source.id] += len(citation.quote.split())

        for source_id, word_count in quoted_words.items():
            if word_count > _MAX_QUOTED_WORDS_PER_SOURCE:
                issues.append(
                    CitationValidationIssue(
                        code=CitationValidationCode.SOURCE_QUOTE_BUDGET_EXCEEDED,
                        source_id=source_id,
                        detail=(
                            f"source quote total {word_count} exceeds "
                            f"{_MAX_QUOTED_WORDS_PER_SOURCE}-word limit"
                        ),
                    )
                )

        referenced_claims: set[str] = set()
        for point in draft.points:
            if _UNVALIDATED_CITATION.search(point.text):
                issues.append(
                    CitationValidationIssue(
                        code=CitationValidationCode.UNVALIDATED_ANSWER_CITATION,
                        detail="answer point contains a provider-authored URL or source marker",
                    )
                )
            for claim_id in point.claim_ids:
                if claim_id not in claim_by_id:
                    issues.append(
                        CitationValidationIssue(
                            code=CitationValidationCode.UNKNOWN_CLAIM,
                            claim_id=claim_id,
                            detail="answer point references an unknown claim",
                        )
                    )
                else:
                    referenced_claims.add(claim_id)

        issues.extend(
            CitationValidationIssue(
                code=CitationValidationCode.MATERIAL_CLAIM_OMITTED,
                claim_id=claim.id,
                detail="material claim is absent from answer points",
            )
            for claim in draft.claims
            if claim.is_material and claim.id not in referenced_claims
        )
        if any(claim.status is ClaimStatus.CONFLICTING for claim in draft.claims) and not any(
            contradiction.strip() for contradiction in draft.contradictions
        ):
            issues.append(
                CitationValidationIssue(
                    code=CitationValidationCode.CONFLICT_SUMMARY_OMITTED,
                    detail="conflicting evidence requires an explicit contradiction summary",
                )
            )

        if issues:
            raise CitationValidationError(issues)

        answer = self._render_answer(draft, claim_by_id, source_by_id)
        timestamp = generated_at or datetime.now(UTC)
        report = ResearchReport(
            objective=objective,
            answer=answer,
            sources=tuple(sources),
            claims=draft.claims,
            contradictions=draft.contradictions,
            unanswered_questions=draft.unanswered_questions,
            generated_at=timestamp,
        )
        citation_count = sum(len(claim.citations) for claim in draft.claims)
        receipt = CitationValidationReceipt(
            source_count=len(sources),
            claim_count=len(draft.claims),
            material_claim_count=sum(claim.is_material for claim in draft.claims),
            citation_count=citation_count,
            quoted_word_count=sum(quoted_words.values()),
        )
        return report, receipt

    @staticmethod
    def _validate_span(
        *,
        claim_id: str,
        source: SourceRecord,
        locator: str,
        quote: str | None,
        issues: list[CitationValidationIssue],
    ) -> None:
        matched = _TEXT_LOCATOR.fullmatch(locator)
        if matched is None:
            issues.append(
                CitationValidationIssue(
                    code=CitationValidationCode.INVALID_LOCATOR,
                    claim_id=claim_id,
                    source_id=source.id,
                    detail="citation locator must use zero-based text:start-end syntax",
                )
            )
            return
        start, end = (int(value) for value in matched.groups())
        if start >= end or end > len(source.extracted_text):
            issues.append(
                CitationValidationIssue(
                    code=CitationValidationCode.INVALID_LOCATOR,
                    claim_id=claim_id,
                    source_id=source.id,
                    detail="citation locator is outside bounded source text",
                )
            )
            return
        if quote is not None and source.extracted_text[start:end] != quote:
            issues.append(
                CitationValidationIssue(
                    code=CitationValidationCode.QUOTE_MISMATCH,
                    claim_id=claim_id,
                    source_id=source.id,
                    detail="citation quote does not match its exact source span",
                )
            )

    @staticmethod
    def _render_answer(
        draft: ResearchSynthesisDraft,
        claim_by_id: dict[str, ResearchClaim],
        source_by_id: dict[str, SourceRecord],
    ) -> str:
        rendered: list[str] = []
        for point in draft.points:
            source_ids: list[str] = []
            uncertainty: list[str] = []
            for claim_id in point.claim_ids:
                claim = claim_by_id[claim_id]
                for citation in claim.citations:
                    if citation.source_id in source_by_id and citation.source_id not in source_ids:
                        source_ids.append(citation.source_id)
                claim_uncertainty = claim.uncertainty.strip()
                if claim_uncertainty and claim_uncertainty not in uncertainty:
                    uncertainty.append(claim_uncertainty)
            suffix = "".join(f" [source:{source_id}]" for source_id in source_ids)
            if uncertainty:
                suffix += f" [uncertainty: {'; '.join(uncertainty)}]"
            rendered.append(f"{point.text}{suffix}")
        return "\n\n".join(rendered)
