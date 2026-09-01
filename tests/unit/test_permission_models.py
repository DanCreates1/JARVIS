from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jarvis.permissions import (
    ActorContext,
    ApprovalDecision,
    ApprovalGrant,
    ApprovalRequest,
    AuthenticationAssurance,
    CanonicalAction,
    InteractionInterface,
    canonical_json,
    sha256_fingerprint,
)
from tests.fakes.phase3 import (
    FIXED_NOW,
    action_definition,
    actor,
    approval_grant,
    canonical_action,
)


def test_canonical_json_normalizes_unicode_order_and_rejects_ambiguous_values() -> None:
    composed = {"label": "caf\N{LATIN SMALL LETTER E WITH ACUTE}", "n": -0.0}
    decomposed = {"n": 0.0, "label": "cafe\N{COMBINING ACUTE ACCENT}"}
    assert canonical_json(composed) == canonical_json(decomposed)
    assert sha256_fingerprint(composed) == sha256_fingerprint(decomposed)

    with pytest.raises(ValueError, match="duplicate"):
        canonical_json({"\N{LATIN SMALL LETTER E WITH ACUTE}": 1, "e\N{COMBINING ACUTE ACCENT}": 2})
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json({"value": float("nan")})
    with pytest.raises(TypeError, match="unsupported"):
        canonical_json({"value": b"secret"})


def test_actor_context_is_strict_frozen_and_requires_aware_authentication() -> None:
    context = actor()
    with pytest.raises(ValidationError):
        ActorContext(
            host_id="host",
            session_id="session",
            device_id="device",
            interface="test",  # type: ignore[arg-type]
            assurance=1,  # type: ignore[arg-type]
            authenticated_at=FIXED_NOW,
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        ActorContext(
            host_id="host",
            session_id="session",
            device_id="device",
            interface=InteractionInterface.TEST,
            assurance=AuthenticationAssurance.LOCAL_SESSION,
            authenticated_at=FIXED_NOW.replace(tzinfo=None),
        )
    with pytest.raises(ValidationError, match="require an authentication timestamp"):
        ActorContext(
            host_id="host",
            session_id="session",
            device_id="device",
            interface=InteractionInterface.TEST,
            assurance=AuthenticationAssurance.LOCAL_SESSION,
        )
    duplicate_capabilities = context.model_dump()
    duplicate_capabilities["capabilities"] = ("computer.test", "computer.test")
    with pytest.raises(ValidationError, match="distinct"):
        ActorContext.model_validate(duplicate_capabilities)
    with pytest.raises(ValidationError):
        context.host_id = "other"  # type: ignore[misc]


def test_action_fingerprint_binds_every_authority_value_and_normalizes_unicode() -> None:
    definition = action_definition()
    composed = canonical_action(
        definition,
        arguments={"label": "caf\N{LATIN SMALL LETTER E WITH ACUTE}"},
    )
    decomposed = canonical_action(
        definition,
        arguments={"label": "cafe\N{COMBINING ACUTE ACCENT}"},
    )
    assert composed.fingerprint == decomposed.fingerprint

    dumped = composed.model_dump()
    dumped["normalized_arguments"] = {"label": "mutated"}
    with pytest.raises(ValidationError, match="fingerprint"):
        CanonicalAction.model_validate(dumped)

    dumped = composed.model_dump()
    dumped["actor"] = actor(session_id="cross-session")
    with pytest.raises(ValidationError, match="fingerprint"):
        CanonicalAction.model_validate(dumped)


def test_action_approval_and_grant_enforce_aware_bounded_ttls_and_exact_fingerprint() -> None:
    definition = action_definition()
    action = canonical_action(definition)
    request = ApprovalRequest(
        approval_id="approval-1",
        action=action,
        requested_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(minutes=1),
    )
    assert request.expires_at <= action.expires_at

    with pytest.raises(ValidationError, match="action TTL"):
        CanonicalAction.create(
            request_id="request-long",
            action_id=definition.action_id,
            action_version=definition.version,
            actor=actor(),
            normalized_arguments={},
            permission_level=definition.tool.permission_level,
            approval_rule=definition.tool.approval_rule,
            policy_version="phase3-policy-v1",
            idempotency_key="long-ttl",
            human_effect="effect",
            recovery_limits="recovery",
            created_at=FIXED_NOW,
            expires_at=FIXED_NOW + timedelta(minutes=16),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        CanonicalAction.create(
            request_id="request-naive",
            action_id=definition.action_id,
            action_version=definition.version,
            actor=actor(),
            normalized_arguments={},
            permission_level=definition.tool.permission_level,
            approval_rule=definition.tool.approval_rule,
            policy_version="phase3-policy-v1",
            idempotency_key="naive",
            human_effect="effect",
            recovery_limits="recovery",
            created_at=FIXED_NOW.replace(tzinfo=None),
            expires_at=(FIXED_NOW + timedelta(minutes=1)).replace(tzinfo=None),
        )

    grant = approval_grant(action)
    values = grant.model_dump()
    values["nonce"] = "mutated-nonce"
    with pytest.raises(ValidationError, match="grant fingerprint"):
        ApprovalGrant.model_validate(values)
    with pytest.raises(ValidationError, match="cannot outlive"):
        ApprovalGrant.create(
            grant_id="grant-long",
            approval_id="approval-1",
            action=action,
            approved_by=action.actor,
            issued_at=FIXED_NOW,
            expires_at=action.expires_at + timedelta(seconds=1),
            nonce="nonce-long",
        )


def test_approval_decision_binds_fingerprint_and_requires_denial_reason() -> None:
    action = canonical_action(action_definition())
    approved = ApprovalDecision(
        approval_id="approval-1",
        action_fingerprint=action.fingerprint,
        approver=action.actor,
        approved=True,
        decided_at=datetime.now(UTC),
    )
    assert approved.approved
    with pytest.raises(ValidationError, match="denied approvals require a reason"):
        ApprovalDecision(
            approval_id="approval-1",
            action_fingerprint=action.fingerprint,
            approver=action.actor,
            approved=False,
            decided_at=FIXED_NOW,
        )
