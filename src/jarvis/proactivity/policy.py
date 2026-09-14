"""Deterministic Phase 11A clock, scope, and suggestion policy."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import (
    EvaluationCode,
    EvaluationDecision,
    ProactivityProposal,
    ProactivityRule,
    RulePreview,
    RuleStatus,
    TriggerEvent,
    TriggerKind,
)


class ProactivityPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HostProactivityPolicy:
    enabled: bool = False
    enabled_features: frozenset[str] = frozenset()
    max_candidates_per_hour: int = 6
    max_candidates_per_day: int = 24
    max_attention_seconds_per_day: int = 300
    max_rule_lifetime_days: int = 30
    clock_skew_seconds: int = 300
    max_task_steps: int = 10
    max_provider_requests: int = 2
    max_tool_calls: int = 5
    max_tokens: int = 10_000
    max_cost_usd: int = 0
    max_concurrency: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.max_candidates_per_hour <= 6:
            raise ValueError("host hourly candidate ceiling must be 1 through 6")
        if not self.max_candidates_per_hour <= self.max_candidates_per_day <= 24:
            raise ValueError("host daily candidate ceiling must include hourly and be at most 24")
        if not 1 <= self.max_attention_seconds_per_day <= 300:
            raise ValueError("host attention ceiling must be 1 through 300 seconds")
        if not 1 <= self.max_rule_lifetime_days <= 30:
            raise ValueError("host rule lifetime must be 1 through 30 days")
        if not 0 <= self.clock_skew_seconds <= 300:
            raise ValueError("host clock skew ceiling must be 0 through 300 seconds")
        if not 0 <= self.max_task_steps <= 10:
            raise ValueError("host task-step ceiling must be 0 through 10")
        if not 0 <= self.max_provider_requests <= 2:
            raise ValueError("host provider-request ceiling must be 0 through 2")
        if not 0 <= self.max_tool_calls <= 5 or not 0 <= self.max_tokens <= 10_000:
            raise ValueError("host tool/token ceiling exceeds Phase 11A")
        if self.max_cost_usd != 0 or self.max_concurrency != 1:
            raise ValueError("Phase 11A requires zero cost and one candidate concurrency")

    def preview(self, proposal: ProactivityProposal, *, now: datetime) -> RulePreview:
        timestamp = _aware(now)
        if proposal.created_at > timestamp + timedelta(seconds=self.clock_skew_seconds):
            raise ProactivityPolicyError("proposal creation time exceeds clock-skew allowance")
        if proposal.expires_at <= timestamp:
            raise ProactivityPolicyError("proposal is already expired")
        if proposal.expires_at - proposal.created_at > timedelta(days=self.max_rule_lifetime_days):
            raise ProactivityPolicyError("proposal lifetime exceeds host ceiling")
        budget = proposal.budget
        if (
            budget.max_candidates_per_hour > self.max_candidates_per_hour
            or budget.max_candidates_per_day > self.max_candidates_per_day
            or budget.max_attention_seconds_per_day > self.max_attention_seconds_per_day
            or budget.max_task_steps > self.max_task_steps
            or budget.max_provider_requests > self.max_provider_requests
            or budget.max_tool_calls > self.max_tool_calls
            or budget.max_tokens > self.max_tokens
            or budget.max_cost_usd > self.max_cost_usd
            or budget.max_concurrency > self.max_concurrency
        ):
            raise ProactivityPolicyError("proposal budget exceeds host ceiling")
        timezone = _timezone(proposal.schedule.timezone)
        next_occurrence = _next_occurrence(proposal, now=timestamp, timezone=timezone)
        digest = hashlib.sha256(
            proposal.model_dump_json(exclude_none=False).encode("utf-8")
        ).hexdigest()
        return RulePreview(
            proposal=proposal,
            proposal_sha256=digest,
            next_occurrence_at=next_occurrence,
        )

    def evaluate(
        self,
        rule: ProactivityRule,
        *,
        now: datetime,
        event: TriggerEvent | None = None,
        hourly_count: int = 0,
        daily_count: int = 0,
        daily_attention_seconds: int = 0,
        active_candidates: int = 0,
        duplicate: bool = False,
    ) -> EvaluationDecision:
        timestamp = _aware(now)

        def denied(code: EvaluationCode) -> EvaluationDecision:
            return EvaluationDecision(rule_id=rule.id, code=code, eligible=False)

        if not self.enabled:
            return denied(EvaluationCode.GLOBAL_DISABLED)
        if rule.proposal.feature not in self.enabled_features:
            return denied(EvaluationCode.FEATURE_DISABLED)
        if rule.status is not RuleStatus.ACTIVE:
            return denied(EvaluationCode.RULE_INACTIVE)
        if timestamp >= rule.proposal.expires_at:
            return denied(EvaluationCode.RULE_EXPIRED)

        occurrence = self._resolve_occurrence(rule, now=timestamp, event=event)
        if isinstance(occurrence, EvaluationCode):
            return denied(occurrence)
        scheduled_for, occurrence_key = occurrence
        local = scheduled_for.astimezone(_timezone(rule.proposal.schedule.timezone))
        if any(_in_quiet_hours(local, quiet) for quiet in rule.proposal.quiet_hours):
            return denied(EvaluationCode.QUIET_HOURS)
        if duplicate:
            return denied(EvaluationCode.DUPLICATE)
        if active_candidates >= self.max_concurrency:
            return denied(EvaluationCode.CANDIDATE_BUSY)
        budget = rule.proposal.budget
        if hourly_count >= min(budget.max_candidates_per_hour, self.max_candidates_per_hour):
            return denied(EvaluationCode.HOURLY_LIMIT)
        if daily_count >= min(budget.max_candidates_per_day, self.max_candidates_per_day):
            return denied(EvaluationCode.DAILY_LIMIT)
        attention_limit = min(
            budget.max_attention_seconds_per_day, self.max_attention_seconds_per_day
        )
        if daily_attention_seconds + rule.proposal.estimated_attention_seconds > attention_limit:
            return denied(EvaluationCode.ATTENTION_LIMIT)
        return EvaluationDecision(
            rule_id=rule.id,
            code=EvaluationCode.CANDIDATE_CREATED,
            eligible=True,
            occurrence_key=occurrence_key,
            scheduled_for=scheduled_for,
        )

    def is_quiet_time(self, rule: ProactivityRule, *, at: datetime) -> bool:
        """Return whether an instant falls inside the rule's host-authored quiet hours."""
        local = _aware(at).astimezone(_timezone(rule.proposal.schedule.timezone))
        return any(_in_quiet_hours(local, quiet) for quiet in rule.proposal.quiet_hours)

    def _resolve_occurrence(
        self,
        rule: ProactivityRule,
        *,
        now: datetime,
        event: TriggerEvent | None,
    ) -> tuple[datetime, str] | EvaluationCode:
        schedule = rule.proposal.schedule
        if schedule.kind is TriggerKind.EVENT:
            if event is None:
                return EvaluationCode.EVENT_REQUIRED
            if event.name != schedule.event_name:
                return EvaluationCode.EVENT_MISMATCH
            delta = now - event.occurred_at
            if delta < -timedelta(seconds=self.clock_skew_seconds):
                return EvaluationCode.CLOCK_SKEW
            if delta > timedelta(seconds=self.clock_skew_seconds):
                return EvaluationCode.STALE_OCCURRENCE
            scheduled_for = event.occurred_at
            source = f"event\0{event.id}\0{event.name}\0{event.occurred_at.isoformat()}"
        else:
            timezone = _timezone(schedule.timezone)
            try:
                if schedule.kind is TriggerKind.ONCE:
                    assert schedule.local_date is not None and schedule.local_time is not None
                    scheduled_for = _resolve_wall_time(
                        schedule.local_date, schedule.local_time, timezone, schedule.fold
                    )
                else:
                    assert schedule.local_time is not None
                    scheduled_for = _resolve_wall_time(
                        now.astimezone(timezone).date(),
                        schedule.local_time,
                        timezone,
                        schedule.fold,
                    )
            except ProactivityPolicyError:
                return EvaluationCode.INVALID_LOCAL_TIME
            delta = now - scheduled_for
            if delta < -timedelta(seconds=self.clock_skew_seconds):
                return EvaluationCode.NOT_DUE
            if delta > timedelta(seconds=self.clock_skew_seconds):
                return EvaluationCode.STALE_OCCURRENCE
            source = f"schedule\0{rule.id}\0{scheduled_for.isoformat()}"
        return scheduled_for, hashlib.sha256(source.encode("utf-8")).hexdigest()


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ProactivityPolicyError("unknown IANA timezone") from exc


def _next_occurrence(
    proposal: ProactivityProposal, *, now: datetime, timezone: ZoneInfo
) -> datetime | None:
    schedule = proposal.schedule
    if schedule.kind is TriggerKind.EVENT:
        return None
    if schedule.kind is TriggerKind.ONCE:
        assert schedule.local_date is not None and schedule.local_time is not None
        occurrence = _resolve_wall_time(
            schedule.local_date, schedule.local_time, timezone, schedule.fold
        )
        if occurrence < now:
            raise ProactivityPolicyError("one-time schedule is already stale")
        if occurrence >= proposal.expires_at:
            raise ProactivityPolicyError("one-time schedule does not occur before expiry")
        return occurrence
    assert schedule.local_time is not None
    start = now.astimezone(timezone).date()
    for offset in range(32):
        local_date = start + timedelta(days=offset)
        try:
            occurrence = _resolve_wall_time(
                local_date, schedule.local_time, timezone, schedule.fold
            )
        except ProactivityPolicyError:
            continue
        if occurrence >= now and occurrence < proposal.expires_at:
            return occurrence
    raise ProactivityPolicyError("daily schedule has no valid occurrence before expiry")


def _resolve_wall_time(
    local_date: date,
    local_time: time,
    timezone: ZoneInfo,
    fold: int | None,
) -> datetime:
    naive = datetime.combine(local_date, local_time)
    candidates: list[datetime] = []
    for candidate_fold in (0, 1):
        aware = naive.replace(tzinfo=timezone, fold=candidate_fold)
        utc = aware.astimezone(UTC)
        if utc.astimezone(timezone).replace(tzinfo=None) == naive:
            candidates.append(utc)
    unique = tuple(dict.fromkeys(candidates))
    if not unique:
        raise ProactivityPolicyError("schedule uses a nonexistent DST wall time")
    if len(unique) == 2:
        if fold is None:
            raise ProactivityPolicyError("ambiguous DST wall time requires fold 0 or 1")
        return unique[fold]
    if fold is not None:
        raise ProactivityPolicyError("fold is allowed only for an ambiguous DST wall time")
    return unique[0]


def _in_quiet_hours(local: datetime, quiet: object) -> bool:
    from .models import QuietHours

    assert isinstance(quiet, QuietHours)
    current = local.time().replace(tzinfo=None)
    if quiet.start < quiet.end:
        return local.weekday() in quiet.weekdays and quiet.start <= current < quiet.end
    if current >= quiet.start:
        return local.weekday() in quiet.weekdays
    previous_day = (local.weekday() - 1) % 7
    return current < quiet.end and previous_day in quiet.weekdays


def local_day_bounds(now: datetime, timezone_name: str) -> tuple[datetime, datetime]:
    """Return UTC bounds for the local civil day, including 23/25-hour DST days."""
    timezone = _timezone(timezone_name)
    local_date = _aware(now).astimezone(timezone).date()
    start = datetime.combine(local_date, time.min, timezone).astimezone(UTC)
    end = datetime.combine(local_date + timedelta(days=1), time.min, timezone).astimezone(UTC)
    return start, end


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProactivityPolicyError("clock values must include a timezone")
    return value.astimezone(UTC)
