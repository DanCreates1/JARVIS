from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.permissions import (
    ActorContext,
    ApprovalRequest,
    AuthenticationAssurance,
    InteractionInterface,
)
from jarvis.permissions.trusted_cli import (
    LocalCliApprovalSurface,
    approval_phrase,
    render_approval_summary,
)
from tests.fakes.phase3 import action_definition, canonical_action

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def _actor(
    *,
    interface: InteractionInterface = InteractionInterface.LOCAL_CLI,
    session_id: str = "session-1",
    capabilities: tuple[str, ...] = ("computer.control",),
) -> ActorContext:
    return ActorContext(
        host_id="host-1",
        session_id=session_id,
        device_id="device-1",
        interface=interface,
        assurance=AuthenticationAssurance.LOCAL_SESSION,
        authenticated_at=NOW,
        capabilities=capabilities,
    )


def _request(*, actor: ActorContext, now: datetime = NOW) -> ApprovalRequest:
    action = canonical_action(
        action_definition(),
        action_actor=actor,
        now=now,
    )
    return ApprovalRequest(
        approval_id="approval-1",
        action=action,
        requested_at=now,
        expires_at=now + timedelta(minutes=1),
    )


@pytest.mark.asyncio
async def test_surface_approves_only_exact_same_identity_request() -> None:
    actor = _actor()
    request = _request(actor=actor)
    seen: list[str] = []
    surface = LocalCliApprovalSurface(
        approver=actor,
        prompt=lambda _request, phrase: seen.append(phrase) is None,
        now=lambda: NOW,
    )

    decision = await surface.review(request)

    assert decision.approved is True
    assert seen == [approval_phrase(request)]
    assert request.action.fingerprint in render_approval_summary(request)
    assert request.action.human_effect in render_approval_summary(request)


@pytest.mark.asyncio
async def test_surface_denies_cross_session_without_prompting() -> None:
    actor = _actor()
    request = _request(actor=actor)
    prompted = False

    def prompt(_request: object, _phrase: str) -> bool:
        nonlocal prompted
        prompted = True
        return True

    surface = LocalCliApprovalSurface(
        approver=_actor(session_id="session-2"), prompt=prompt, now=lambda: NOW
    )

    decision = await surface.review(request)

    assert decision.approved is False
    assert decision.reason is not None and "session" in decision.reason
    assert prompted is False


@pytest.mark.asyncio
async def test_surface_denies_capability_downgrade_without_prompting() -> None:
    request = _request(actor=_actor())
    prompted = False

    def prompt(_request: object, _phrase: str) -> bool:
        nonlocal prompted
        prompted = True
        return True

    surface = LocalCliApprovalSurface(
        approver=_actor(capabilities=()),
        prompt=prompt,
        now=lambda: NOW,
    )

    decision = await surface.review(request)

    assert decision.approved is False
    assert decision.reason is not None and "capabilities" in decision.reason
    assert prompted is False


@pytest.mark.asyncio
async def test_surface_denies_expired_cancelled_and_naive_clock() -> None:
    actor = _actor()
    expired = _request(actor=actor, now=NOW - timedelta(minutes=10))
    expired_surface = LocalCliApprovalSurface(
        approver=actor, prompt=lambda _request, _phrase: True, now=lambda: NOW
    )
    assert (await expired_surface.review(expired)).approved is False

    current = _request(actor=actor)
    cancelled_surface = LocalCliApprovalSurface(
        approver=actor,
        prompt=lambda _request, _phrase: (_ for _ in ()).throw(KeyboardInterrupt),
        now=lambda: NOW,
    )
    cancelled = await cancelled_surface.review(current)
    assert cancelled.approved is False
    assert cancelled.reason is not None and "cancelled" in cancelled.reason

    naive_surface = LocalCliApprovalSurface(
        approver=actor,
        prompt=lambda _request, _phrase: True,
        now=lambda: NOW.replace(tzinfo=None),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        await naive_surface.review(current)


def test_surface_constructor_rejects_untrusted_interface_or_assurance() -> None:
    with pytest.raises(ValueError, match="local CLI"):
        LocalCliApprovalSurface(
            approver=_actor(interface=InteractionInterface.LOCAL_WEB),
            prompt=lambda _request, _phrase: True,
        )
    unauthenticated = ActorContext(
        host_id="host-1",
        session_id="session-1",
        device_id="device-1",
        interface=InteractionInterface.LOCAL_CLI,
        assurance=AuthenticationAssurance.UNAUTHENTICATED,
        capabilities=(),
    )
    with pytest.raises(ValueError, match="authenticated"):
        LocalCliApprovalSurface(
            approver=unauthenticated,
            prompt=lambda _request, _phrase: True,
        )
