"""Freshness and offline-fallback boundary for live knowledge answers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier
from jarvis.research.models import ClaimStatus, ResearchReport, UrlText


class KnowledgeRetrievalMode(StrEnum):
    LIVE = "live"
    FRESH_CACHE = "fresh_cache"
    STALE_OFFLINE = "stale_offline"


class KnowledgeFreshnessErrorCode(StrEnum):
    LIVE_REFRESH_REQUIRED = "live_refresh_required"
    OFFLINE_CACHE_EXPIRED = "offline_cache_expired"
    CONFLICT_NOT_DISCLOSED = "conflict_not_disclosed"


class KnowledgeFreshnessError(RuntimeError):
    def __init__(self, code: KnowledgeFreshnessErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class KnowledgeRequest(CoreModel):
    query: Annotated[str, Field(min_length=1, max_length=2_000)]
    max_age_seconds: Annotated[int, Field(ge=60, le=86_400)] = 3_600
    stale_if_offline_seconds: Annotated[int, Field(ge=0, le=604_800)] = 86_400
    citations_required: Literal[True] = True
    conflict_disclosure_required: Literal[True] = True

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("knowledge query cannot be blank")
        return normalized


class KnowledgeSourceStamp(CoreModel):
    source_id: Identifier
    url: UrlText
    retrieved_at: datetime
    published_at: datetime | None = None
    last_checked_at: datetime
    expires_at: datetime

    @field_validator("retrieved_at", "published_at", "last_checked_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("knowledge source timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_expiry(self) -> Self:
        if self.last_checked_at < self.retrieved_at:
            raise ValueError("source check cannot precede retrieval")
        if self.expires_at <= self.last_checked_at:
            raise ValueError("source expiry must follow its last check")
        return self


class KnowledgeSnapshot(CoreModel):
    request: KnowledgeRequest
    report: ResearchReport
    mode: KnowledgeRetrievalMode
    evaluated_at: datetime
    fresh_until: datetime
    source_stamps: Annotated[tuple[KnowledgeSourceStamp, ...], Field(min_length=1, max_length=50)]
    expired_source_ids: Annotated[tuple[Identifier, ...], Field(max_length=50)] = ()
    offline: bool
    conflicts_visible: bool
    citations_present: Literal[True] = True

    @field_validator("evaluated_at", "fresh_until")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("knowledge snapshot timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        report_ids = {source.id for source in self.report.sources}
        stamp_ids = {stamp.source_id for stamp in self.source_stamps}
        if report_ids != stamp_ids or len(stamp_ids) != len(self.source_stamps):
            raise ValueError("knowledge source stamps must exactly match report sources")
        if self.fresh_until != min(stamp.expires_at for stamp in self.source_stamps):
            raise ValueError("knowledge freshness must use the earliest source expiry")
        expected_expired = tuple(
            sorted(
                stamp.source_id
                for stamp in self.source_stamps
                if stamp.expires_at <= self.evaluated_at
            )
        )
        if self.expired_source_ids != expected_expired:
            raise ValueError("expired knowledge source IDs do not match timestamps")
        if self.mode is KnowledgeRetrievalMode.LIVE and (self.offline or expected_expired):
            raise ValueError("live knowledge must be online and fresh")
        if self.mode is KnowledgeRetrievalMode.FRESH_CACHE and expected_expired:
            raise ValueError("fresh-cache knowledge must be unexpired")
        if self.mode is KnowledgeRetrievalMode.STALE_OFFLINE and (
            not self.offline or not expected_expired
        ):
            raise ValueError("stale knowledge requires an expired offline cache")
        has_conflict = any(claim.status is ClaimStatus.CONFLICTING for claim in self.report.claims)
        if self.conflicts_visible is not has_conflict:
            raise ValueError("knowledge conflict visibility does not match report claims")
        return self


def evaluate_knowledge_report(
    report: ResearchReport,
    request: KnowledgeRequest,
    *,
    now: datetime,
    online: bool,
    retrieved_live: bool = False,
) -> KnowledgeSnapshot:
    """Classify a cited Phase 5 report without treating stale cache as live knowledge."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("knowledge evaluation time must include a timezone")
    if retrieved_live and not online:
        raise ValueError("live retrieval cannot be asserted while offline")
    evaluated_at = now.astimezone(UTC)
    has_conflict = any(claim.status is ClaimStatus.CONFLICTING for claim in report.claims)
    if has_conflict and not report.contradictions:
        raise KnowledgeFreshnessError(
            KnowledgeFreshnessErrorCode.CONFLICT_NOT_DISCLOSED,
            "conflicting knowledge requires a visible contradiction summary",
        )

    stamps = tuple(
        KnowledgeSourceStamp(
            source_id=source.id,
            url=source.url,
            retrieved_at=source.retrieved_at,
            published_at=source.published_at,
            last_checked_at=source.last_checked_at,
            expires_at=source.last_checked_at + timedelta(seconds=request.max_age_seconds),
        )
        for source in report.sources
    )
    expired = tuple(sorted(stamp.source_id for stamp in stamps if stamp.expires_at <= evaluated_at))
    if not expired:
        mode = KnowledgeRetrievalMode.LIVE if retrieved_live else KnowledgeRetrievalMode.FRESH_CACHE
    elif online:
        raise KnowledgeFreshnessError(
            KnowledgeFreshnessErrorCode.LIVE_REFRESH_REQUIRED,
            "cached knowledge expired while live retrieval is available",
        )
    elif any(
        evaluated_at > stamp.expires_at + timedelta(seconds=request.stale_if_offline_seconds)
        for stamp in stamps
        if stamp.source_id in expired
    ):
        raise KnowledgeFreshnessError(
            KnowledgeFreshnessErrorCode.OFFLINE_CACHE_EXPIRED,
            "offline knowledge cache exceeded its explicit stale allowance",
        )
    else:
        mode = KnowledgeRetrievalMode.STALE_OFFLINE

    return KnowledgeSnapshot(
        request=request,
        report=report,
        mode=mode,
        evaluated_at=evaluated_at,
        fresh_until=min(stamp.expires_at for stamp in stamps),
        source_stamps=stamps,
        expired_source_ids=expired,
        offline=not online,
        conflicts_visible=has_conflict,
    )
