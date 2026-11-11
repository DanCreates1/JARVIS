"""Actual reminder draft through canonical store; no alternate scheduler or effects."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.calendar.service import reminder_proposal
from jarvis.proactivity import (
    EvaluationCode,
    HostProactivityPolicy,
    ProactivityNotFoundError,
    RuleStatus,
    SQLiteProactivityStore,
    TrustedActivation,
)


async def test_calendar_reminder_exact_activation_restart_duplicate_disable_delete(tmp_path: Path):
    now = datetime(2026, 11, 1, 5, 0, tzinfo=UTC)
    due = now + timedelta(minutes=1)
    proposal = reminder_proposal(
        title="Private owner-authored reminder", at=due, timezone="America/Toronto", now=now
    )
    policy = HostProactivityPolicy(enabled=True, enabled_features=frozenset({"calendar.reminder"}))
    database = tmp_path / "core.db"
    async with SQLiteProactivityStore(database) as store:
        draft = await store.create_rule(
            host_id="host:calendar", preview=policy.preview(proposal, now=now), now=now
        )
        decision, candidate = await store.evaluate_and_record(
            host_id="host:calendar", rule_id=draft.id, policy=policy, now=due
        )
        assert decision.code is EvaluationCode.RULE_INACTIVE and candidate is None
        with pytest.raises(ProactivityNotFoundError):
            await store.require_rule(host_id="host:other", rule_id=draft.id)
        activated = await store.activate(
            TrustedActivation(
                approval_id="activation:calendar",
                host_id="host:calendar",
                rule_id=draft.id,
                expected_version=draft.version,
                expected_proposal_sha256=draft.proposal_sha256,
                approved_at=now,
                expires_at=now + timedelta(minutes=5),
            ),
            policy=policy,
            now=now,
        )
        assert activated.status is RuleStatus.ACTIVE
    async with SQLiteProactivityStore(database) as store:
        decision, candidate = await store.evaluate_and_record(
            host_id="host:calendar", rule_id=draft.id, policy=policy, now=due
        )
        assert decision.code is EvaluationCode.CANDIDATE_CREATED and candidate is not None
        assert not candidate.execution_authorized and not candidate.notification_sent
        assert "Private owner" not in candidate.model_dump_json()
        decision, duplicate = await store.evaluate_and_record(
            host_id="host:calendar", rule_id=draft.id, policy=policy, now=due
        )
        assert decision.code is EvaluationCode.DUPLICATE and duplicate is None
        disabled = await store.disable(
            host_id="host:calendar", rule_id=draft.id, expected_version=activated.version, now=due
        )
        assert disabled.status is RuleStatus.DISABLED
        await store.delete_rule(host_id="host:calendar", rule_id=draft.id, now=due)
    async with SQLiteProactivityStore(database) as store:
        with pytest.raises(ProactivityNotFoundError):
            await store.require_rule(host_id="host:calendar", rule_id=draft.id)
