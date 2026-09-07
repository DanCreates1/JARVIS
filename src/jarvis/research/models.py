"""Strict provider-neutral contracts for Phase 5 research."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier

UrlText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_048),
]
ContentDigest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class ResearchErrorCode(StrEnum):
    INVALID_URL = "invalid_url"
    PRIVATE_NETWORK_DENIED = "private_network_denied"
    DOMAIN_DENIED = "domain_denied"
    REDIRECT_LIMIT = "redirect_limit"
    RESPONSE_TOO_LARGE = "response_too_large"
    UNSUPPORTED_CONTENT = "unsupported_content"
    AUTHENTICATION_REQUIRED = "authentication_required"
    PAYWALL = "paywall"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    PROTOCOL_ERROR = "protocol_error"
    CANCELLED = "cancelled"
    PRIVACY_DENIED = "privacy_denied"
    APPROVAL_REQUIRED = "approval_required"


class ClaimStatus(StrEnum):
    VERIFIED = "verified"
    LIKELY = "likely"
    HYPOTHESIS = "hypothesis"
    OPINION = "opinion"
    STALE = "stale"
    CONFLICTING = "conflicting"


class SourceState(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class ClaimLifecycle(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class ResearchConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ResearchStage(StrEnum):
    SEARCH = "search"
    FETCH = "fetch"
    PARSE = "parse"
    SYNTHESIZE = "synthesize"
    REVALIDATE = "revalidate"


class ResearchInterface(StrEnum):
    LOCAL_CLI = "local_cli"
    LOCAL_WEB = "local_web"
    TRUSTED_API = "trusted_api"
    TEST = "test"


class ResearchReportState(StrEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"


class UnansweredQuestionStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    DISMISSED = "dismissed"


class CitationValidationCode(StrEnum):
    UNKNOWN_SOURCE = "unknown_source"
    INACTIVE_SOURCE = "inactive_source"
    MISSING_QUOTE = "missing_quote"
    INVALID_LOCATOR = "invalid_locator"
    QUOTE_MISMATCH = "quote_mismatch"
    SOURCE_QUOTE_BUDGET_EXCEEDED = "source_quote_budget_exceeded"
    UNKNOWN_CLAIM = "unknown_claim"
    MATERIAL_CLAIM_OMITTED = "material_claim_omitted"
    UNCERTAINTY_OMITTED = "uncertainty_omitted"
    CONFLICT_SUMMARY_OMITTED = "conflict_summary_omitted"
    UNVALIDATED_ANSWER_CITATION = "unvalidated_answer_citation"


class SearchRequest(CoreModel):
    query: Annotated[str, Field(min_length=1, max_length=1_000)]
    limit: Annotated[int, Field(ge=1, le=20)] = 10
    allowed_domains: Annotated[tuple[str, ...], Field(max_length=50)] = ()

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("research query cannot be blank")
        return normalized


class SearchResult(CoreModel):
    url: UrlText
    title: Annotated[str, Field(min_length=1, max_length=1_000)]
    snippet: Annotated[str, Field(max_length=4_000)] = ""
    publisher: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    published_at: datetime | None = None

    @field_validator("published_at")
    @classmethod
    def require_aware_publication_time(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value, "publication")


class FetchLimits(CoreModel):
    max_bytes: Annotated[int, Field(ge=1_024, le=10 * 1_024 * 1_024)] = 2 * 1_024 * 1_024
    timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 15
    max_redirects: Annotated[int, Field(ge=0, le=5)] = 3
    accepted_media_types: Annotated[tuple[str, ...], Field(min_length=1, max_length=20)] = (
        "text/html",
        "text/plain",
        "application/pdf",
    )

    @field_validator("accepted_media_types")
    @classmethod
    def normalize_media_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(media_type.strip().lower() for media_type in value)
        if any(not media_type or "/" not in media_type for media_type in normalized):
            raise ValueError("accepted media types must be nonblank MIME types")
        if len(normalized) != len(set(normalized)):
            raise ValueError("accepted media types must be distinct")
        return normalized


class FetchRequest(CoreModel):
    url: UrlText
    allowed_domains: Annotated[tuple[str, ...], Field(max_length=50)] = ()
    limits: FetchLimits = Field(default_factory=FetchLimits)


class FetchedDocument(CoreModel):
    requested_url: UrlText
    final_url: UrlText
    media_type: Annotated[str, Field(min_length=1, max_length=200)]
    encoding: Annotated[str, Field(min_length=1, max_length=100)] = "utf-8"
    body: Annotated[bytes, Field(min_length=1, max_length=10 * 1_024 * 1_024)]
    retrieved_at: datetime
    status_code: Annotated[int, Field(ge=200, le=299)]
    redirect_chain: Annotated[tuple[UrlText, ...], Field(max_length=5)] = ()
    etag: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    last_modified: Annotated[str, Field(min_length=1, max_length=500)] | None = None

    @field_validator("retrieved_at")
    @classmethod
    def require_aware_retrieval_time(cls, value: datetime) -> datetime:
        result = _require_aware(value, "retrieval")
        assert result is not None
        return result


class ParsedDocument(CoreModel):
    source_url: UrlText
    title: Annotated[str, Field(min_length=1, max_length=1_000)]
    text: Annotated[str, Field(min_length=1, max_length=500_000)]
    publisher: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    published_at: datetime | None = None
    language: Annotated[str, Field(min_length=2, max_length=35)] | None = None

    @field_validator("published_at")
    @classmethod
    def require_aware_publication_time(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value, "publication")


class SourceRecord(CoreModel):
    id: Identifier
    host_id: Identifier
    url: UrlText
    publisher: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    title: Annotated[str, Field(min_length=1, max_length=1_000)]
    topic: Annotated[str, Field(min_length=1, max_length=500)]
    media_type: Annotated[str, Field(min_length=1, max_length=200)]
    content_sha256: ContentDigest
    extracted_text: Annotated[str, Field(min_length=1, max_length=500_000)]
    retrieved_at: datetime
    published_at: datetime | None = None
    last_checked_at: datetime
    usage_notes: Annotated[str, Field(max_length=2_000)] = ""
    state: SourceState = SourceState.ACTIVE
    version: Annotated[int, Field(ge=1)] = 1
    supersedes_id: Identifier | None = None
    etag: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    last_modified: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    untrusted: bool = True

    @field_validator("retrieved_at", "published_at", "last_checked_at")
    @classmethod
    def require_aware_times(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value, "source")

    @model_validator(mode="after")
    def require_untrusted_source(self) -> Self:
        if not self.untrusted:
            raise ValueError("acquired research sources must remain untrusted")
        return self


class Citation(CoreModel):
    source_id: Identifier
    locator: Annotated[str, Field(min_length=1, max_length=500)]
    quote: Annotated[str, Field(max_length=1_000)] | None = None

    @field_validator("quote")
    @classmethod
    def bound_quote_words(cls, value: str | None) -> str | None:
        if value is not None and len(value.split()) > 25:
            raise ValueError("citation quote exceeds the 25-word per-source excerpt limit")
        return value


class ResearchClaim(CoreModel):
    id: Identifier
    statement: Annotated[str, Field(min_length=1, max_length=10_000)]
    status: ClaimStatus
    citations: Annotated[tuple[Citation, ...], Field(max_length=20)] = ()
    is_material: bool = True
    is_inference: bool = False
    uncertainty: Annotated[str, Field(max_length=2_000)] = ""

    @model_validator(mode="after")
    def require_evidence_shape(self) -> Self:
        source_ids = [citation.source_id for citation in self.citations]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("claim citations must use distinct sources")
        if (
            self.is_material
            and self.status not in {ClaimStatus.HYPOTHESIS, ClaimStatus.OPINION}
            and not self.citations
        ):
            raise ValueError("material factual claims require a citation")
        if self.status is ClaimStatus.CONFLICTING and len(source_ids) < 2:
            raise ValueError("conflicting claims require at least two distinct sources")
        if self.is_inference and not self.uncertainty.strip():
            raise ValueError("inferences require an explicit uncertainty explanation")
        return self


class ResearchClaimRecord(CoreModel):
    id: Identifier
    host_id: Identifier
    topic: Annotated[str, Field(min_length=1, max_length=500)]
    statement: Annotated[str, Field(min_length=1, max_length=10_000)]
    status: ClaimStatus
    lifecycle: ClaimLifecycle = ClaimLifecycle.ACTIVE
    citations: Annotated[tuple[Citation, ...], Field(max_length=20)] = ()
    is_material: bool = True
    is_inference: bool = False
    uncertainty: Annotated[str, Field(max_length=2_000)] = ""
    version: Annotated[int, Field(ge=1)] = 1
    supersedes_id: Identifier | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        result = _require_aware(value, "claim")
        assert result is not None
        return result

    @model_validator(mode="after")
    def require_evidence_shape(self) -> Self:
        ResearchClaim(
            id=self.id,
            statement=self.statement,
            status=self.status,
            citations=self.citations,
            is_material=self.is_material,
            is_inference=self.is_inference,
            uncertainty=self.uncertainty,
        )
        return self


class ResearchConflict(CoreModel):
    id: Identifier
    host_id: Identifier
    left_claim_id: Identifier
    right_claim_id: Identifier
    status: ResearchConflictStatus
    winner_claim_id: Identifier | None = None
    reason_code: Annotated[str, Field(min_length=1, max_length=100)]
    created_at: datetime
    resolved_at: datetime | None = None

    @field_validator("created_at", "resolved_at")
    @classmethod
    def require_aware_times(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value, "conflict")

    @model_validator(mode="after")
    def validate_claims(self) -> Self:
        if self.left_claim_id == self.right_claim_id:
            raise ValueError("research conflict requires two distinct claims")
        if self.winner_claim_id is not None and self.winner_claim_id not in {
            self.left_claim_id,
            self.right_claim_id,
        }:
            raise ValueError("conflict winner must be one of the conflicting claims")
        if self.status is ResearchConflictStatus.OPEN and self.winner_claim_id is not None:
            raise ValueError("open conflict cannot have a winner")
        return self


class ResearchExportReceipt(CoreModel):
    host_id: Identifier
    path: Annotated[str, Field(min_length=1, max_length=4_000)]
    source_count: Annotated[int, Field(ge=0)]
    claim_count: Annotated[int, Field(ge=0)]
    conflict_count: Annotated[int, Field(ge=0)]
    byte_count: Annotated[int, Field(ge=0)]
    exported_at: datetime

    @field_validator("exported_at")
    @classmethod
    def require_aware_export_time(cls, value: datetime) -> datetime:
        result = _require_aware(value, "export")
        assert result is not None
        return result


class ResearchDeletionReceipt(CoreModel):
    host_id: Identifier
    requested_source_id: Identifier
    deleted_source_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=10_000)]
    deleted_claim_ids: Annotated[tuple[Identifier, ...], Field(max_length=10_000)]
    source_rows: Annotated[int, Field(ge=1)]
    claim_rows: Annotated[int, Field(ge=0)]
    citation_rows: Annotated[int, Field(ge=0)]
    conflict_rows: Annotated[int, Field(ge=0)]
    fts_rows: Annotated[int, Field(ge=0)]
    tombstones_written: Annotated[int, Field(ge=1)]
    deleted_at: datetime

    @field_validator("deleted_at")
    @classmethod
    def require_aware_deletion_time(cls, value: datetime) -> datetime:
        result = _require_aware(value, "deletion")
        assert result is not None
        return result


class ResearchPlan(CoreModel):
    objective: Annotated[str, Field(min_length=1, max_length=2_000)]
    questions: Annotated[tuple[str, ...], Field(min_length=1, max_length=20)]
    max_sources: Annotated[int, Field(ge=1, le=50)] = 10
    max_queries: Annotated[int, Field(ge=1, le=20)] = 5
    max_fetches: Annotated[int, Field(ge=1, le=100)] = 20
    max_claims: Annotated[int, Field(ge=1, le=200)] = 50
    max_chars_per_source: Annotated[int, Field(ge=1_000, le=500_000)] = 50_000
    max_total_source_chars: Annotated[int, Field(ge=1_000, le=2_000_000)] = 200_000
    allowed_domains: Annotated[tuple[str, ...], Field(max_length=50)] = ()
    fetch_limits: FetchLimits = Field(
        default_factory=lambda: FetchLimits(
            accepted_media_types=("text/html", "text/plain", "application/pdf"),
        )
    )
    deadline_seconds: Annotated[float, Field(gt=0, le=600)] = 120

    @field_validator("objective")
    @classmethod
    def normalize_objective(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("research objective cannot be blank")
        return normalized

    @field_validator("questions")
    @classmethod
    def normalize_questions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(" ".join(question.split()) for question in value)
        if any(not question for question in normalized):
            raise ValueError("research questions cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("research questions must be distinct")
        return normalized

    @model_validator(mode="after")
    def validate_execution_bounds(self) -> Self:
        if self.max_sources > self.max_fetches:
            raise ValueError("max_sources cannot exceed max_fetches")
        return self


class ResearchAnswerPoint(CoreModel):
    text: Annotated[str, Field(min_length=1, max_length=10_000)]
    claim_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=20)]

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("research answer point cannot be blank")
        return normalized

    @model_validator(mode="after")
    def require_distinct_claims(self) -> Self:
        if len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("research answer point claim IDs must be distinct")
        return self


class ResearchSynthesisRequest(CoreModel):
    objective: Annotated[str, Field(min_length=1, max_length=2_000)]
    questions: Annotated[tuple[str, ...], Field(min_length=1, max_length=20)]
    sources: Annotated[tuple[SourceRecord, ...], Field(min_length=1, max_length=50)]
    max_claims: Annotated[int, Field(ge=1, le=200)]

    @model_validator(mode="after")
    def require_distinct_untrusted_sources(self) -> Self:
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("research synthesis source IDs must be distinct")
        if any(not source.untrusted for source in self.sources):
            raise ValueError("research synthesis sources must remain untrusted")
        return self


class ResearchSynthesisDraft(CoreModel):
    points: Annotated[tuple[ResearchAnswerPoint, ...], Field(min_length=1, max_length=100)]
    claims: Annotated[tuple[ResearchClaim, ...], Field(min_length=1, max_length=200)]
    contradictions: Annotated[tuple[str, ...], Field(max_length=100)] = ()
    unanswered_questions: Annotated[tuple[str, ...], Field(max_length=100)] = ()

    @model_validator(mode="after")
    def require_distinct_claims_and_bounded_answer(self) -> Self:
        claim_ids = [claim.id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("research synthesis claim IDs must be distinct")
        if sum(len(point.text) for point in self.points) > 80_000:
            raise ValueError("research synthesis answer text exceeds limit")
        return self


class ResearchFailure(CoreModel):
    stage: ResearchStage
    code: ResearchErrorCode
    target: Annotated[str, Field(min_length=1, max_length=2_048)]
    detail: Annotated[str, Field(min_length=1, max_length=500)]


class CitationValidationIssue(CoreModel):
    code: CitationValidationCode
    claim_id: Identifier | None = None
    source_id: Identifier | None = None
    detail: Annotated[str, Field(min_length=1, max_length=500)]


class ResearchReport(CoreModel):
    objective: Annotated[str, Field(min_length=1, max_length=2_000)]
    answer: Annotated[str, Field(min_length=1, max_length=100_000)]
    sources: Annotated[tuple[SourceRecord, ...], Field(min_length=1, max_length=50)]
    claims: Annotated[tuple[ResearchClaim, ...], Field(min_length=1, max_length=200)]
    contradictions: Annotated[tuple[str, ...], Field(max_length=100)] = ()
    unanswered_questions: Annotated[tuple[str, ...], Field(max_length=100)] = ()
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def require_aware_generation_time(cls, value: datetime) -> datetime:
        result = _require_aware(value, "generation")
        assert result is not None
        return result

    @model_validator(mode="after")
    def validate_source_links(self) -> Self:
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("research report source IDs must be distinct")
        known = set(source_ids)
        referenced = {citation.source_id for claim in self.claims for citation in claim.citations}
        missing = sorted(referenced - known)
        if missing:
            raise ValueError(f"claim citations reference unknown sources: {missing!r}")
        return self


class CitationValidationReceipt(CoreModel):
    source_count: Annotated[int, Field(ge=1, le=50)]
    claim_count: Annotated[int, Field(ge=1, le=200)]
    material_claim_count: Annotated[int, Field(ge=0, le=200)]
    citation_count: Annotated[int, Field(ge=0, le=4_000)]
    quoted_word_count: Annotated[int, Field(ge=0)]


class ResearchRunResult(CoreModel):
    plan: ResearchPlan
    report: ResearchReport
    validation: CitationValidationReceipt
    failures: Annotated[tuple[ResearchFailure, ...], Field(max_length=100)] = ()
    queries_attempted: Annotated[int, Field(ge=0, le=20)]
    search_results_considered: Annotated[int, Field(ge=0, le=400)]
    fetches_attempted: Annotated[int, Field(ge=0, le=100)]


class PendingResearchRun(CoreModel):
    id: Identifier
    host_id: Identifier
    report_sha256: ContentDigest
    result: ResearchRunResult
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def require_aware_expiry(cls, value: datetime) -> datetime:
        result = _require_aware(value, "pending research expiry")
        assert result is not None
        return result


class ResearchStorageApproval(CoreModel):
    host_id: Identifier
    pending_run_id: Identifier
    expected_report_sha256: ContentDigest
    interface: ResearchInterface
    approved_at: datetime
    supersedes_report_id: Identifier | None = None

    @field_validator("approved_at")
    @classmethod
    def require_aware_approval_time(cls, value: datetime) -> datetime:
        result = _require_aware(value, "research approval")
        assert result is not None
        return result


class StoredResearchReport(CoreModel):
    id: Identifier
    host_id: Identifier
    objective: Annotated[str, Field(min_length=1, max_length=2_000)]
    answer: Annotated[str, Field(min_length=1, max_length=100_000)]
    report_sha256: ContentDigest
    state: ResearchReportState
    supersedes_id: Identifier | None = None
    source_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=50)]
    claim_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=200)]
    approved_interface: ResearchInterface
    approved_at: datetime
    generated_at: datetime

    @field_validator("approved_at", "generated_at")
    @classmethod
    def require_aware_report_times(cls, value: datetime) -> datetime:
        result = _require_aware(value, "stored research report")
        assert result is not None
        return result


class ResearchApprovalReceipt(CoreModel):
    pending_run_id: Identifier
    report_sha256: ContentDigest
    stored: bool
    report_id: Identifier | None = None
    source_count: Annotated[int, Field(ge=0, le=50)] = 0
    claim_count: Annotated[int, Field(ge=0, le=200)] = 0
    unanswered_count: Annotated[int, Field(ge=0, le=100)] = 0

    @model_validator(mode="after")
    def validate_storage_result(self) -> Self:
        if self.stored != (self.report_id is not None):
            raise ValueError("stored approval receipts require exactly one report ID")
        return self


class UnansweredQuestionRecord(CoreModel):
    id: Identifier
    host_id: Identifier
    report_id: Identifier
    question: Annotated[str, Field(min_length=1, max_length=2_000)]
    status: UnansweredQuestionStatus
    answer_claim_id: Identifier | None = None
    version: Annotated[int, Field(ge=1)]
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_aware_question_times(cls, value: datetime) -> datetime:
        result = _require_aware(value, "unanswered question")
        assert result is not None
        return result

    @model_validator(mode="after")
    def validate_answer_reference(self) -> Self:
        if self.status is UnansweredQuestionStatus.ANSWERED and self.answer_claim_id is None:
            raise ValueError("answered research question requires an answer claim")
        if (
            self.status is not UnansweredQuestionStatus.ANSWERED
            and self.answer_claim_id is not None
        ):
            raise ValueError("only answered research questions may reference a claim")
        return self


class ResearchRevalidationReceipt(CoreModel):
    requested_source_id: Identifier
    current_source_id: Identifier
    changed: bool
    state: SourceState
    checked_at: datetime

    @field_validator("checked_at")
    @classmethod
    def require_aware_revalidation_time(cls, value: datetime) -> datetime:
        result = _require_aware(value, "research revalidation")
        assert result is not None
        return result


def _require_aware(value: datetime | None, label: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{label} timestamp must be timezone-aware")
    return value
