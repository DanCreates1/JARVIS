from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from pydantic import ValidationError

from jarvis.proactivity import (
    EvaluationCode,
    HostProactivityPolicy,
    ProactivityBudget,
    ProactivityPolicyError,
    ProactivityProposal,
    ProactivityProvenance,
    ProactivityRule,
    ProactivityScope,
    ProposalSource,
    QuietHours,
    RuleStatus,
    TriggerEvent,
    TriggerKind,
    TriggerSchedule,
)

NOW = datetime(2026, 9, 14, 14, 0, tzinfo=UTC)


def proposal(
    *,
    schedule: TriggerSchedule | None = None,
    feature: str = "daily.briefing",
    quiet_hours: tuple[QuietHours, ...] = (),
    budget: ProactivityBudget | None = None,
) -> ProactivityProposal:
    return ProactivityProposal(
        title="Daily public briefing",
        feature=feature,
        schedule=schedule
        or TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone="America/Toronto",
            local_date=date(2026, 9, 14),
            local_time=time(10, 1),
        ),
        quiet_hours=quiet_hours,
        budget=budget or ProactivityBudget(),
        scope=ProactivityScope(),
        estimated_attention_seconds=10,
        provenance=ProactivityProvenance(
            source_type=ProposalSource.HOST,
            source_id="host-request:1",
        ),
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def active_rule(value: ProactivityProposal | None = None) -> ProactivityRule:
    item = value or proposal()
    preview = HostProactivityPolicy().preview(item, now=NOW)
    return ProactivityRule(
        id="proactivity:1",
        host_id="host:1",
        proposal=item,
        proposal_sha256=preview.proposal_sha256,
        status=RuleStatus.ACTIVE,
        version=2,
        created_at=NOW,
        updated_at=NOW,
        activated_at=NOW,
    )


def enabled_policy(**changes: object) -> HostProactivityPolicy:
    values: dict[str, object] = {
        "enabled": True,
        "enabled_features": frozenset({"daily.briefing", "task.changed"}),
    }
    values.update(changes)
    return HostProactivityPolicy(**values)  # type: ignore[arg-type]


def test_preview_is_suggestion_only_and_digest_is_stable() -> None:
    policy = HostProactivityPolicy()
    first = policy.preview(proposal(), now=NOW)
    second = policy.preview(proposal(), now=NOW)
    assert first == second
    assert first.mode == "suggestion"
    assert first.execution_authorized is False
    assert first.next_occurrence_at == datetime(2026, 9, 14, 14, 1, tzinfo=UTC)


def test_global_and_feature_controls_are_default_deny() -> None:
    rule = active_rule()
    assert HostProactivityPolicy().evaluate(rule, now=NOW).code is EvaluationCode.GLOBAL_DISABLED
    assert (
        HostProactivityPolicy(enabled=True).evaluate(rule, now=NOW).code
        is EvaluationCode.FEATURE_DISABLED
    )


def test_due_schedule_creates_only_inert_candidate_decision() -> None:
    rule = active_rule()
    result = enabled_policy().evaluate(rule, now=NOW + timedelta(minutes=1))
    assert result.code is EvaluationCode.CANDIDATE_CREATED
    assert result.eligible is True
    assert result.execution_authorized is False
    assert result.occurrence_key is not None


@pytest.mark.parametrize(
    ("offset", "code"),
    ((-301, EvaluationCode.NOT_DUE), (301, EvaluationCode.STALE_OCCURRENCE)),
)
def test_clock_window_fails_closed(offset: int, code: EvaluationCode) -> None:
    scheduled = NOW + timedelta(minutes=1)
    result = enabled_policy().evaluate(active_rule(), now=scheduled + timedelta(seconds=offset))
    assert result.code is code


def test_event_requires_exact_fresh_content_free_identity() -> None:
    item = proposal(
        schedule=TriggerSchedule(
            kind=TriggerKind.EVENT,
            timezone="America/Toronto",
            event_name="task.changed",
        ),
        feature="task.changed",
    )
    rule = active_rule(item)
    policy = enabled_policy()
    assert policy.evaluate(rule, now=NOW).code is EvaluationCode.EVENT_REQUIRED
    wrong = TriggerEvent(id="event:1", name="daily.briefing", occurred_at=NOW)
    assert policy.evaluate(rule, now=NOW, event=wrong).code is EvaluationCode.EVENT_MISMATCH
    stale = TriggerEvent(
        id="event:1", name="task.changed", occurred_at=NOW - timedelta(seconds=301)
    )
    assert policy.evaluate(rule, now=NOW, event=stale).code is EvaluationCode.STALE_OCCURRENCE
    valid = TriggerEvent(id="event:1", name="task.changed", occurred_at=NOW)
    assert policy.evaluate(rule, now=NOW, event=valid).eligible is True


def test_quiet_hours_cross_midnight_uses_start_day() -> None:
    item = proposal(
        schedule=TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone="America/Toronto",
            local_date=date(2026, 9, 14),
            local_time=time(23, 0),
        ),
        quiet_hours=(QuietHours(start=time(22), end=time(7), weekdays=(0,)),),
    )
    rule = active_rule(item)
    result = enabled_policy().evaluate(rule, now=datetime(2026, 9, 15, 3, 0, tzinfo=UTC))
    assert result.code is EvaluationCode.QUIET_HOURS


def test_dst_gap_and_fold_fail_closed_without_exact_resolution() -> None:
    gap = proposal(
        schedule=TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone="America/Toronto",
            local_date=date(2026, 3, 8),
            local_time=time(2, 30),
        )
    ).model_copy(
        update={
            "created_at": datetime(2026, 3, 1, tzinfo=UTC),
            "expires_at": datetime(2026, 3, 9, tzinfo=UTC),
        }
    )
    with pytest.raises(ProactivityPolicyError, match="nonexistent"):
        HostProactivityPolicy().preview(gap, now=datetime(2026, 3, 1, tzinfo=UTC))

    fold = proposal(
        schedule=TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone="America/Toronto",
            local_date=date(2026, 11, 1),
            local_time=time(1, 30),
        )
    ).model_copy(
        update={
            "created_at": datetime(2026, 10, 25, tzinfo=UTC),
            "expires_at": datetime(2026, 11, 2, tzinfo=UTC),
        }
    )
    with pytest.raises(ProactivityPolicyError, match="ambiguous"):
        HostProactivityPolicy().preview(fold, now=datetime(2026, 10, 25, tzinfo=UTC))
    later = fold.model_copy(update={"schedule": fold.schedule.model_copy(update={"fold": 1})})
    preview = HostProactivityPolicy().preview(later, now=datetime(2026, 10, 25, tzinfo=UTC))
    assert preview.next_occurrence_at == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


def test_rule_and_host_budgets_deny_noise() -> None:
    rule = active_rule()
    policy = enabled_policy()
    assert policy.evaluate(rule, now=NOW + timedelta(minutes=1), hourly_count=1).code is (
        EvaluationCode.HOURLY_LIMIT
    )
    assert policy.evaluate(rule, now=NOW + timedelta(minutes=1), daily_count=3).code is (
        EvaluationCode.DAILY_LIMIT
    )
    assert (
        policy.evaluate(rule, now=NOW + timedelta(minutes=1), daily_attention_seconds=60).code
        is EvaluationCode.ATTENTION_LIMIT
    )
    assert policy.evaluate(rule, now=NOW + timedelta(minutes=1), active_candidates=1).code is (
        EvaluationCode.CANDIDATE_BUSY
    )


def test_lifetime_timezone_and_structural_authority_limits() -> None:
    with pytest.raises(ProactivityPolicyError, match="timezone"):
        HostProactivityPolicy().preview(
            proposal().model_copy(
                update={
                    "schedule": proposal().schedule.model_copy(update={"timezone": "Mars/Olympus"})
                }
            ),
            now=NOW,
        )
    with pytest.raises(ProactivityPolicyError, match="lifetime"):
        HostProactivityPolicy().preview(
            proposal().model_copy(update={"expires_at": NOW + timedelta(days=31)}), now=NOW
        )
    with pytest.raises(ValidationError):
        ProactivityScope(effect_execution_allowed=True)
    with pytest.raises(ValidationError):
        ProactivityBudget(max_cost_usd=1)


def test_model_and_research_provenance_can_never_claim_trust() -> None:
    with pytest.raises(ValidationError):
        ProactivityProvenance(
            source_type=ProposalSource.MODEL,
            source_id="model:1",
            untrusted=False,
        )
