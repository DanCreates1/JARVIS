from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis.config import Settings
from jarvis.core import PermissionLevel
from jarvis.permissions import (
    ActorContext,
    ApprovalRequest,
    AuthenticationAssurance,
    InteractionInterface,
    RemoteBrowserApprovalSurface,
    approval_phrase,
)
from jarvis.remote import (
    BrowserOriginError,
    BrowserOriginPolicy,
    FixedWindowRateLimiter,
    RemoteIdentityContext,
    RemoteScope,
    RemoteSessionKind,
)
from tests.fakes.phase3 import action_definition, canonical_action

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)


def test_origin_policy_is_exact_and_never_accepts_null_duplicate_or_suffix() -> None:
    policy = BrowserOriginPolicy(("https://phone.jarvis.test",))

    assert policy.require(("https://phone.jarvis.test",)) == "https://phone.jarvis.test"
    assert policy.optional(()) is None
    for values in (
        (),
        ("null",),
        ("https://phone.jarvis.test.attacker.invalid",),
        ("https://phone.jarvis.test", "https://attacker.invalid"),
    ):
        with pytest.raises(BrowserOriginError):
            policy.require(values)


def test_rate_limiter_is_bounded_and_resets_fixed_window() -> None:
    current = 100.0
    limiter = FixedWindowRateLimiter(max_entries=2, window_seconds=60, clock=lambda: current)

    assert limiter.check("device-a", limit=2).allowed is True
    assert limiter.check("device-a", limit=2).allowed is True
    denied = limiter.check("device-a", limit=2)
    assert denied.allowed is False and denied.retry_after_seconds == 60
    assert limiter.check("device-b", limit=2).allowed is True
    assert limiter.check("device-c", limit=2).allowed is True
    assert limiter.entry_count == 2
    current += 61
    assert limiter.check("device-c", limit=2).allowed is True


def test_browser_origin_configuration_requires_exact_https_origins(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        trusted_browser_origins=("https://PHONE.jarvis.test:8443/",),
        _env_file=None,
    )
    assert settings.trusted_browser_origins == ("https://phone.jarvis.test:8443",)
    defaults = Settings(
        data_dir=tmp_path,
        trusted_browser_origins=("https://PHONE.jarvis.test:443", "https://[::1]:8443"),
        _env_file=None,
    )
    assert defaults.trusted_browser_origins == (
        "https://[::1]:8443",
        "https://phone.jarvis.test",
    )
    for origin in (
        "http://phone.jarvis.test",
        "https://user@phone.jarvis.test",
        "https://phone.jarvis.test/path",
        "https://phone.jarvis.test?query=1",
    ):
        with pytest.raises(ValidationError, match="exact HTTPS origins"):
            Settings(data_dir=tmp_path, trusted_browser_origins=(origin,), _env_file=None)


def test_remote_identity_rejects_naive_authentication_time() -> None:
    with pytest.raises(ValidationError, match="must include a timezone"):
        _identity(authenticated_at=NOW.replace(tzinfo=None))


def _actor(
    *,
    session_id: str = "session-browser",
    authenticated_at: datetime = NOW,
    capabilities: tuple[str, ...] = ("computer.test",),
) -> ActorContext:
    return ActorContext(
        host_id="host-1",
        session_id=session_id,
        device_id="device-1",
        interface=InteractionInterface.LOCAL_WEB,
        assurance=AuthenticationAssurance.RECENT_AUTH,
        authenticated_at=authenticated_at,
        capabilities=capabilities,
    )


def _approval(level: PermissionLevel, actor: ActorContext) -> ApprovalRequest:
    action = canonical_action(action_definition(level), action_actor=actor, now=NOW)
    return ApprovalRequest(
        approval_id=f"approval-{int(level)}",
        action=action,
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=1),
    )


def _identity(
    *,
    session_id: str = "session-browser",
    authenticated_at: datetime | None = NOW,
    risk_ceiling: int = 1,
    scopes: frozenset[RemoteScope] = frozenset({RemoteScope.APPROVAL_REVIEW}),
    kind: RemoteSessionKind = RemoteSessionKind.BROWSER,
) -> RemoteIdentityContext:
    return RemoteIdentityContext(
        host_id="host-1",
        session_id=session_id,
        device_id="device-1",
        key_version=1,
        audience="jarvis-api",
        scopes=scopes,
        session_kind=kind,
        risk_ceiling=risk_ceiling,
        authenticated_at=authenticated_at,
    )


@pytest.mark.asyncio
async def test_remote_approval_allows_only_exact_recent_low_risk_identity() -> None:
    actor = _actor()
    request = _approval(PermissionLevel.LEVEL_1, actor)
    surface = RemoteBrowserApprovalSurface(
        identity=_identity(),
        capabilities=("computer.test",),
        submitted_phrase=approval_phrase(request),
        now=lambda: NOW,
    )

    decision = await surface.review(request)

    assert decision.approved is True
    assert decision.action_fingerprint == request.action.fingerprint
    assert decision.approver.same_identity(actor)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("level", "ceiling", "session_id", "authenticated_at", "phrase", "reason"),
    (
        (PermissionLevel.LEVEL_2, 2, "session-browser", NOW, "exact", "local-host"),
        (PermissionLevel.LEVEL_1, 0, "session-browser", NOW, "exact", "risk ceiling"),
        (
            PermissionLevel.LEVEL_1,
            1,
            "other-session",
            NOW,
            "exact",
            "session",
        ),
        (
            PermissionLevel.LEVEL_1,
            1,
            "session-browser",
            NOW - timedelta(minutes=6),
            "exact",
            "recent",
        ),
        (PermissionLevel.LEVEL_1, 1, "session-browser", NOW, "wrong", "phrase"),
    ),
)
async def test_remote_approval_denials_fail_closed(
    level: PermissionLevel,
    ceiling: int,
    session_id: str,
    authenticated_at: datetime,
    phrase: str,
    reason: str,
) -> None:
    action_actor = _actor()
    request = _approval(level, action_actor)
    submitted = approval_phrase(request) if phrase == "exact" else phrase
    surface = RemoteBrowserApprovalSurface(
        identity=_identity(
            session_id=session_id,
            authenticated_at=authenticated_at,
            risk_ceiling=ceiling,
        ),
        capabilities=("computer.test",),
        submitted_phrase=submitted,
        now=lambda: NOW,
    )

    decision = await surface.review(request)

    assert decision.approved is False
    assert decision.reason is not None and reason in decision.reason


def test_remote_approval_constructor_rejects_wrong_session_or_missing_scope() -> None:
    with pytest.raises(ValueError, match="browser session"):
        RemoteBrowserApprovalSurface(
            identity=_identity(kind=RemoteSessionKind.SIGNED_API),
            capabilities=(),
            submitted_phrase="none",
        )
    with pytest.raises(ValueError, match=r"approval\.review"):
        RemoteBrowserApprovalSurface(
            identity=_identity(scopes=frozenset()),
            capabilities=(),
            submitted_phrase="none",
        )
