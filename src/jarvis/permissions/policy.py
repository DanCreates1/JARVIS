"""Deterministic Phase 3 permission engine independent from model output."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from hmac import compare_digest

from jarvis.core import ApprovalRule, PermissionLevel

from .canonical import sha256_fingerprint
from .models import (
    ActionDefinition,
    ActionPolicyDecision,
    ActorContext,
    AuthenticationAssurance,
    CanonicalAction,
    PolicyDisposition,
)

Now = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PermissionEngine:
    """Apply fixed level semantics; neither prompts nor confidence can widen them."""

    def __init__(
        self,
        *,
        policy_version: str,
        enabled_level_one_actions: Iterable[str] = (),
        recent_auth_max_age: timedelta = timedelta(minutes=5),
        now: Now = _utc_now,
    ) -> None:
        if not policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if recent_auth_max_age <= timedelta(0) or recent_auth_max_age > timedelta(hours=1):
            raise ValueError("recent_auth_max_age must be in (0, 1 hour]")
        self.policy_version = policy_version.strip()
        self.enabled_level_one_actions = frozenset(enabled_level_one_actions)
        self.recent_auth_max_age = recent_auth_max_age
        self._now = now

    async def decide(
        self,
        *,
        action: CanonicalAction,
        definition: ActionDefinition,
        actor: ActorContext,
    ) -> ActionPolicyDecision:
        denial = self._common_denial(action, definition, actor)
        if denial is not None:
            return denial

        level = action.permission_level
        if level is PermissionLevel.LEVEL_0:
            return self._decision(
                level,
                PolicyDisposition.ALLOW,
                "level_0_authenticated_read",
                "Authenticated Level 0 action is allowed within its declared capability.",
            )
        if level is PermissionLevel.LEVEL_1:
            if definition.dispatch_key not in self.enabled_level_one_actions:
                return self._decision(
                    level,
                    PolicyDisposition.APPROVAL_REQUIRED,
                    "level_1_exact_approval",
                    "Level 1 action requires exact trusted review when not explicitly enabled.",
                )
            return self._decision(
                level,
                PolicyDisposition.ALLOW,
                "level_1_explicit_enablement",
                "Level 1 action and required capability are explicitly enabled.",
            )
        if level is PermissionLevel.LEVEL_2:
            return self._decision(
                level,
                PolicyDisposition.APPROVAL_REQUIRED,
                "level_2_exact_approval",
                "Level 2 action requires exact trusted approval for this operation.",
            )
        if level is PermissionLevel.LEVEL_3:
            if not self._has_recent_authentication(actor):
                return self._decision(
                    level,
                    PolicyDisposition.DENY,
                    "level_3_recent_auth_missing",
                    "Level 3 action requires recent trusted authentication before approval.",
                )
            return self._decision(
                level,
                PolicyDisposition.APPROVAL_REQUIRED,
                "level_3_recent_auth_and_exact_approval",
                "Level 3 action requires exact approval after recent authentication.",
            )
        return self._decision(
            PermissionLevel.LEVEL_4,
            PolicyDisposition.DENY,
            "level_4_disabled",
            "Level 4 administrative and critical actions are disabled in Phase 3.",
        )

    def _common_denial(
        self,
        action: CanonicalAction,
        definition: ActionDefinition,
        actor: ActorContext,
    ) -> ActionPolicyDecision | None:
        level = action.permission_level
        if not compare_digest(
            action.fingerprint,
            sha256_fingerprint(action.fingerprint_payload()),
        ):
            return self._decision(
                level,
                PolicyDisposition.DENY,
                "action_fingerprint_mismatch",
                "Canonical action fingerprint is invalid.",
            )
        if action.policy_version != self.policy_version:
            return self._decision(
                level,
                PolicyDisposition.DENY,
                "policy_version_mismatch",
                "Action was canonicalized under a different policy version.",
            )
        if not action.actor.same_identity(actor):
            return self._decision(
                level,
                PolicyDisposition.DENY,
                "actor_mismatch",
                "Action actor, session, or device does not match the active actor.",
            )
        if actor.assurance is AuthenticationAssurance.UNAUTHENTICATED:
            return self._decision(
                level,
                PolicyDisposition.DENY,
                "actor_unauthenticated",
                "Unauthenticated actors cannot execute tools.",
            )
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("permission clock must return a timezone-aware datetime")
        if action.expires_at <= now.astimezone(UTC):
            return self._decision(
                level,
                PolicyDisposition.DENY,
                "action_expired",
                "Canonical action has expired.",
            )
        if (
            action.action_id != definition.action_id
            or action.action_version != definition.version
            or action.permission_level is not definition.tool.permission_level
            or action.approval_rule is not definition.tool.approval_rule
        ):
            return self._decision(
                level,
                PolicyDisposition.DENY,
                "definition_mismatch",
                "Canonical action does not match the fixed registered definition.",
            )
        missing = set(definition.tool.required_capabilities).difference(actor.capabilities)
        if missing:
            return self._decision(
                level,
                PolicyDisposition.DENY,
                "capability_missing",
                "Actor lacks a capability required by the fixed action definition.",
            )
        if definition.tool.approval_rule is ApprovalRule.DISABLED:
            return self._decision(
                level,
                PolicyDisposition.DENY,
                "action_disabled",
                "Action is disabled by its registered approval rule.",
            )
        return None

    def _has_recent_authentication(self, actor: ActorContext) -> bool:
        if actor.assurance < AuthenticationAssurance.RECENT_AUTH:
            return False
        if actor.authenticated_at is None:
            return False
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("permission clock must return a timezone-aware datetime")
        age = now.astimezone(UTC) - actor.authenticated_at
        return timedelta(0) <= age <= self.recent_auth_max_age

    def _decision(
        self,
        level: PermissionLevel,
        disposition: PolicyDisposition,
        rule_id: str,
        reason: str,
    ) -> ActionPolicyDecision:
        return ActionPolicyDecision(
            disposition=disposition,
            permission_level=level,
            policy_version=self.policy_version,
            rule_id=rule_id,
            reason=reason,
        )
