from __future__ import annotations

from datetime import timedelta

import pytest

from jarvis.core import PermissionLevel
from jarvis.permissions import (
    AuthenticationAssurance,
    PermissionEngine,
    PolicyDisposition,
)
from tests.fakes.phase3 import (
    FIXED_NOW,
    POLICY_VERSION,
    action_definition,
    actor,
    canonical_action,
)


@pytest.mark.asyncio
async def test_permission_levels_zero_one_and_two_apply_exact_semantics() -> None:
    level_zero = action_definition(PermissionLevel.LEVEL_0, supports_rollback=False)
    level_one = action_definition(PermissionLevel.LEVEL_1)
    level_two = action_definition(PermissionLevel.LEVEL_2)
    current_actor = actor()
    engine = PermissionEngine(
        policy_version=POLICY_VERSION,
        enabled_level_one_actions={level_one.dispatch_key},
        now=lambda: FIXED_NOW,
    )

    zero = await engine.decide(
        action=canonical_action(level_zero),
        definition=level_zero,
        actor=current_actor,
    )
    one = await engine.decide(
        action=canonical_action(level_one),
        definition=level_one,
        actor=current_actor,
    )
    two = await engine.decide(
        action=canonical_action(level_two),
        definition=level_two,
        actor=current_actor,
    )
    assert zero.disposition is PolicyDisposition.ALLOW
    assert one.disposition is PolicyDisposition.ALLOW
    assert two.disposition is PolicyDisposition.APPROVAL_REQUIRED

    review_engine = PermissionEngine(policy_version=POLICY_VERSION, now=lambda: FIXED_NOW)
    review_required = await review_engine.decide(
        action=canonical_action(level_one),
        definition=level_one,
        actor=current_actor,
    )
    assert review_required.disposition is PolicyDisposition.APPROVAL_REQUIRED
    assert review_required.rule_id == "level_1_exact_approval"


@pytest.mark.asyncio
async def test_levels_three_and_four_require_auth_but_remain_gated() -> None:
    level_three = action_definition(PermissionLevel.LEVEL_3)
    level_four = action_definition(PermissionLevel.LEVEL_4, supports_rollback=False)
    engine = PermissionEngine(policy_version=POLICY_VERSION, now=lambda: FIXED_NOW)

    local_actor = actor()
    local = await engine.decide(
        action=canonical_action(level_three, action_actor=local_actor),
        definition=level_three,
        actor=local_actor,
    )
    assert local.disposition is PolicyDisposition.DENY
    assert local.rule_id == "level_3_recent_auth_missing"

    stale_actor = actor(
        assurance=AuthenticationAssurance.RECENT_AUTH,
        authenticated_at=FIXED_NOW - timedelta(minutes=6),
    )
    stale = await engine.decide(
        action=canonical_action(level_three, action_actor=stale_actor),
        definition=level_three,
        actor=stale_actor,
    )
    assert stale.disposition is PolicyDisposition.DENY

    recent_actor = actor(
        assurance=AuthenticationAssurance.RECENT_AUTH,
        authenticated_at=FIXED_NOW - timedelta(minutes=1),
    )
    recent = await engine.decide(
        action=canonical_action(level_three, action_actor=recent_actor),
        definition=level_three,
        actor=recent_actor,
    )
    assert recent.disposition is PolicyDisposition.APPROVAL_REQUIRED

    step_up_actor = actor(assurance=AuthenticationAssurance.STEP_UP)
    level_four_decision = await engine.decide(
        action=canonical_action(level_four, action_actor=step_up_actor),
        definition=level_four,
        actor=step_up_actor,
    )
    assert level_four_decision.disposition is PolicyDisposition.DENY
    assert level_four_decision.rule_id in {"action_disabled", "level_4_disabled"}


@pytest.mark.asyncio
async def test_policy_fails_closed_on_context_and_authority_mutation() -> None:
    definition = action_definition(PermissionLevel.LEVEL_2)
    current_actor = actor()
    engine = PermissionEngine(policy_version=POLICY_VERSION, now=lambda: FIXED_NOW)

    missing_capability_actor = actor(capabilities=())
    missing = await engine.decide(
        action=canonical_action(definition, action_actor=missing_capability_actor),
        definition=definition,
        actor=missing_capability_actor,
    )
    assert missing.rule_id == "capability_missing"

    cross_session = actor(session_id="other-session")
    wrong_actor = await engine.decide(
        action=canonical_action(definition),
        definition=definition,
        actor=cross_session,
    )
    assert wrong_actor.rule_id == "actor_mismatch"

    wrong_definition = action_definition(PermissionLevel.LEVEL_2, name="other_action")
    mismatch = await engine.decide(
        action=canonical_action(definition),
        definition=wrong_definition,
        actor=current_actor,
    )
    assert mismatch.rule_id == "definition_mismatch"

    wrong_policy = await engine.decide(
        action=canonical_action(definition, policy_version="old-policy"),
        definition=definition,
        actor=current_actor,
    )
    assert wrong_policy.rule_id == "policy_version_mismatch"

    expired_engine = PermissionEngine(
        policy_version=POLICY_VERSION,
        now=lambda: FIXED_NOW + timedelta(minutes=3),
    )
    expired = await expired_engine.decide(
        action=canonical_action(definition),
        definition=definition,
        actor=current_actor,
    )
    assert expired.rule_id == "action_expired"

    valid = canonical_action(definition)
    mutated = valid.model_copy(update={"normalized_arguments": {"value": "injected"}})
    fingerprint_denial = await engine.decide(
        action=mutated,
        definition=definition,
        actor=current_actor,
    )
    assert fingerprint_denial.rule_id == "action_fingerprint_mismatch"


def test_permission_engine_rejects_invalid_policy_and_recent_auth_bounds() -> None:
    with pytest.raises(ValueError, match="policy_version"):
        PermissionEngine(policy_version=" ")
    with pytest.raises(ValueError, match="recent_auth_max_age"):
        PermissionEngine(policy_version="v1", recent_auth_max_age=timedelta(0))
