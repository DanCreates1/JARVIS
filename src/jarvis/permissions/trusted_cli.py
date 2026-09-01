"""Trusted local-terminal approval surface for exact Phase 3 actions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from jarvis.core import ApprovalRule, PermissionLevel

from .canonical import canonical_json
from .models import (
    ActorContext,
    ApprovalDecision,
    ApprovalRequest,
    AuthenticationAssurance,
    InteractionInterface,
)

ApprovalPrompt = Callable[[ApprovalRequest, str], bool]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def approval_phrase(request: ApprovalRequest) -> str:
    """Return phrase that binds a human confirmation to one exact fingerprint."""
    return f"APPROVE {request.action.fingerprint.removeprefix('sha256:')[-16:]}"


def render_approval_summary(request: ApprovalRequest) -> str:
    """Render stable plain text suitable for a host-owned terminal."""
    action = request.action
    arguments = action.normalized_arguments
    lines = (
        f"Approval ID: {request.approval_id}",
        f"Action: {action.action_id}@{action.action_version}",
        f"Permission level: {int(action.permission_level)}",
        f"Risk: {_risk_label(action.permission_level)}",
        f"Effect: {action.human_effect}",
        f"Arguments: {canonical_json(arguments)}",
        f"Recovery limits: {action.recovery_limits}",
        f"Actor/session/device: {action.actor.host_id}/{action.actor.session_id}/"
        f"{action.actor.device_id}",
        f"Expires: {request.expires_at.isoformat()}",
        f"Fingerprint: {action.fingerprint}",
    )
    return "\n".join(lines)


def _risk_label(level: PermissionLevel) -> str:
    return {
        PermissionLevel.LEVEL_0: "read-only",
        PermissionLevel.LEVEL_1: "low-risk reversible",
        PermissionLevel.LEVEL_2: "meaningful reversible/external",
        PermissionLevel.LEVEL_3: "sensitive or destructive",
        PermissionLevel.LEVEL_4: "administrative/critical",
    }[level]


class LocalCliApprovalSurface:
    """Approve only from the same authenticated local OS terminal identity."""

    def __init__(
        self,
        *,
        approver: ActorContext,
        prompt: ApprovalPrompt,
        now: Clock = _utc_now,
    ) -> None:
        if approver.interface is not InteractionInterface.LOCAL_CLI:
            raise ValueError("trusted approval requires the local CLI interface")
        if approver.assurance < AuthenticationAssurance.LOCAL_SESSION:
            raise ValueError("trusted approval requires an authenticated local session")
        self._approver = approver
        self._prompt = prompt
        self._now = now

    async def review(self, request: ApprovalRequest) -> ApprovalDecision:
        now = self._now_utc()
        denial = self._denial_reason(request, now)
        approved = False
        reason: str | None = denial
        if denial is None:
            try:
                approved = bool(self._prompt(request, approval_phrase(request)))
            except (EOFError, KeyboardInterrupt):
                approved = False
            if not approved:
                reason = "Host declined or cancelled exact local approval."
        return ApprovalDecision(
            approval_id=request.approval_id,
            action_fingerprint=request.action.fingerprint,
            approver=self._approver,
            approved=approved,
            decided_at=now,
            reason=reason,
        )

    def _denial_reason(self, request: ApprovalRequest, now: datetime) -> str | None:
        action = request.action
        if not action.actor.same_identity(self._approver):
            return "Approval actor, session, or device does not match the action actor."
        if not set(action.actor.capabilities).issubset(self._approver.capabilities):
            return "Approval context does not preserve the proposal actor's capabilities."
        if request.expires_at <= now or action.expires_at <= now:
            return "Approval request or canonical action has expired."
        if action.permission_level is PermissionLevel.LEVEL_4:
            return "Level 4 actions are disabled."
        if action.approval_rule is ApprovalRule.DISABLED:
            return "Registered action is disabled."
        return None

    def _now_utc(self) -> datetime:
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("approval clock must return a timezone-aware datetime")
        return now.astimezone(UTC)
