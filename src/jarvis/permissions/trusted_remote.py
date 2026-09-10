"""Exact Phase 8B approval surface for an authenticated enrolled browser device."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from jarvis.core import ApprovalRule, PermissionLevel
from jarvis.remote import RemoteIdentityContext, RemoteScope, RemoteSessionKind

from .models import (
    ActorContext,
    ApprovalDecision,
    ApprovalRequest,
    AuthenticationAssurance,
    InteractionInterface,
)
from .trusted_cli import approval_phrase

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RemoteBrowserApprovalSurface:
    """Allow exact low-risk approval; escalate meaningful/sensitive effects locally."""

    def __init__(
        self,
        *,
        identity: RemoteIdentityContext,
        capabilities: tuple[str, ...],
        submitted_phrase: str,
        now: Clock = _utc_now,
        recent_auth_window: timedelta = timedelta(minutes=5),
    ) -> None:
        if identity.session_kind is not RemoteSessionKind.BROWSER:
            raise ValueError("remote approval requires a browser session")
        if RemoteScope.APPROVAL_REVIEW not in identity.scopes:
            raise ValueError("remote approval requires approval.review scope")
        if identity.authenticated_at is None:
            raise ValueError("remote browser identity lacks authentication time")
        if not timedelta(seconds=30) <= recent_auth_window <= timedelta(minutes=15):
            raise ValueError("recent authentication window must be 30 seconds to 15 minutes")
        self._approver = ActorContext(
            host_id=identity.host_id,
            session_id=identity.session_id,
            device_id=identity.device_id,
            interface=InteractionInterface.LOCAL_WEB,
            assurance=AuthenticationAssurance.RECENT_AUTH,
            authenticated_at=identity.authenticated_at,
            capabilities=capabilities,
        )
        self._device_risk_ceiling = identity.risk_ceiling
        self._submitted_phrase = submitted_phrase
        self._now = now
        self._recent_auth_window = recent_auth_window

    async def review(self, request: ApprovalRequest) -> ApprovalDecision:
        now = self._now_utc()
        reason = self._denial_reason(request, now)
        approved = reason is None
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
        authenticated_at = self._approver.authenticated_at
        if not action.actor.same_identity(self._approver):
            return "Approval actor, session, or device does not match the action actor."
        if not set(action.actor.capabilities).issubset(self._approver.capabilities):
            return "Approval context does not preserve the proposal actor's capabilities."
        if request.expires_at <= now or action.expires_at <= now:
            return "Approval request or canonical action has expired."
        if (
            authenticated_at is None
            or authenticated_at > now
            or now - authenticated_at > self._recent_auth_window
        ):
            return "Remote approval requires recent enrolled-device authentication."
        if action.approval_rule is ApprovalRule.DISABLED:
            return "Registered action is disabled."
        if action.permission_level >= PermissionLevel.LEVEL_2:
            return "Level 2-4 actions require exact trusted local-host approval."
        if int(action.permission_level) > self._device_risk_ceiling:
            return "Action exceeds the enrolled device risk ceiling."
        if self._submitted_phrase != approval_phrase(request):
            return "Remote approval phrase does not match the exact action fingerprint."
        return None

    def _now_utc(self) -> datetime:
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("approval clock must return a timezone-aware datetime")
        return now.astimezone(UTC)
