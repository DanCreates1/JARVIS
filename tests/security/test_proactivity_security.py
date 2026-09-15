from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from pydantic import ValidationError

from jarvis.proactivity import (
    CandidateDispatch,
    CandidateOwnership,
    HostProactivityPolicy,
    LocalNotification,
    OwnershipKind,
    ProactivityBudget,
    ProactivityPolicyError,
    ProactivityProposal,
    ProactivityProvenance,
    ProactivityScope,
    ProposalSource,
    TriggerKind,
    TriggerSchedule,
    TrustedActivation,
    VisibleProactivityState,
)

NOW = datetime(2026, 9, 14, 14, 0, tzinfo=UTC)


def test_untrusted_fields_cannot_add_execution_notification_approval_or_cost() -> None:
    forbidden = (
        (ProactivityScope, {"effect_execution_allowed": True}),
        (ProactivityScope, {"notification_send_allowed": True}),
        (ProactivityScope, {"approval_creation_allowed": True}),
        (ProactivityScope, {"cloud_disclosure_allowed": True}),
        (ProactivityScope, {"retains_candidate_content": True}),
        (ProactivityBudget, {"max_cost_usd": 1}),
        (ProactivityBudget, {"max_concurrency": 2}),
        (ProactivityProvenance, {"source_type": "model", "source_id": "m:1", "untrusted": False}),
    )
    for model, values in forbidden:
        with pytest.raises(ValidationError):
            model.model_validate(values)


def test_unknown_and_extra_authority_fields_fail_closed() -> None:
    with pytest.raises(ValidationError):
        ProactivityScope.model_validate({"run_task": True})
    with pytest.raises(ValidationError):
        TrustedActivation.model_validate(
            {
                "approval_id": "approval:1",
                "host_id": "host:1",
                "rule_id": "rule:1",
                "expected_version": 1,
                "expected_proposal_sha256": "a" * 64,
                "interface": "model",
                "approved_at": NOW,
                "expires_at": NOW + timedelta(minutes=1),
            }
        )


def test_runner_contracts_reject_content_and_authority_injection() -> None:
    with pytest.raises(ValidationError):
        LocalNotification.model_validate(
            {
                "id": "notice:1",
                "host_id": "host:1",
                "rule_id": "rule:1",
                "candidate_id": "candidate:1",
                "dispatch_version": 1,
                "feature": "briefing",
                "state": "active",
                "available_at": NOW,
                "expires_at": NOW + timedelta(minutes=1),
                "created_at": NOW,
                "updated_at": NOW,
                "title": "secret content",
            }
        )
    with pytest.raises(ValidationError):
        CandidateDispatch.model_validate(
            {
                "candidate_id": "candidate:1",
                "host_id": "host:1",
                "rule_id": "rule:1",
                "state": "claimed",
                "version": 1,
                "attempts": 1,
                "expires_at": NOW + timedelta(minutes=1),
                "created_at": NOW,
                "updated_at": NOW,
                "execute_task": True,
            }
        )


def test_policy_rejects_host_ceiling_expansion_and_future_timestamp() -> None:
    policy = HostProactivityPolicy()
    proposal = ProactivityProposal(
        title="Bounded suggestion",
        feature="briefing",
        schedule=TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone="UTC",
            local_date=date(2026, 9, 14),
            local_time=time(14, 2),
        ),
        budget=ProactivityBudget(max_task_steps=10),
        provenance=ProactivityProvenance(
            source_type=ProposalSource.MODEL,
            source_id="model:1",
        ),
        created_at=NOW + timedelta(minutes=6),
        expires_at=NOW + timedelta(days=1),
    )
    with pytest.raises(ProactivityPolicyError, match="clock-skew"):
        policy.preview(proposal, now=NOW)
    with pytest.raises(ValueError):
        HostProactivityPolicy(max_task_steps=11)


def test_device_coordination_contracts_reject_content_and_inconsistent_owners() -> None:
    with pytest.raises(ValidationError):
        VisibleProactivityState.model_validate(
            {
                "candidate_id": "candidate:1",
                "feature": "task.checkin",
                "dispatch_state": "notified",
                "notification_state": "active",
                "owner_kind": "local_host",
                "owned_by_this_device": False,
                "ownership_version": 1,
                "available_at": NOW,
                "expires_at": NOW + timedelta(minutes=1),
                "title": "private",
            }
        )
    with pytest.raises(ValidationError):
        CandidateOwnership(
            candidate_id="candidate:1",
            host_id="host:1",
            rule_id="rule:1",
            owner_kind=OwnershipKind.DEVICE,
            owner_id="device:1",
            owner_device_id=None,
            version=1,
            lease_expires_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
