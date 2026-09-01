from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import BaseModel, ConfigDict

from jarvis.computer.actions import PreparedAction
from jarvis.computer.registry import ComputerActionRegistry
from jarvis.core import (
    Conversation,
    PermissionLevel,
    ToolCall,
)
from jarvis.permissions import (
    ActionCoordinatorResult,
    ActionCoordinatorStatus,
    ActionPolicyDecision,
    ApprovalRequest,
    ApprovalSource,
    PolicyDisposition,
)
from jarvis.security.computer_policy import ComputerProposalPolicy
from tests.fakes.phase3 import (
    FIXED_NOW,
    FakeActionHandler,
    action_definition,
    actor,
    canonical_action,
)


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


class CanonicalHandler(FakeActionHandler):
    @property
    def input_model(self) -> type[BaseModel]:
        return Arguments

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        parsed = Arguments.model_validate(arguments)
        return PreparedAction(
            normalized_arguments={"value": parsed.value},
            human_effect="Apply fixed fake effect.",
            recovery_limits="Fake rollback only.",
        )


class FakeCoordinator:
    def __init__(self, result: ActionCoordinatorResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def propose(self, canonicalizer, raw_arguments, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(
            {
                "canonicalizer": canonicalizer,
                "arguments": raw_arguments,
                **kwargs,
            }
        )
        return self.result


def _policy(result: ActionCoordinatorResult):
    handler = CanonicalHandler(action_definition(PermissionLevel.LEVEL_1, name="fixed_action"))
    registry = ComputerActionRegistry((handler,))
    coordinator = FakeCoordinator(result)
    current_actor = actor(capabilities=("computer.test",))
    policy = ComputerProposalPolicy(
        registry=registry,
        coordinator=coordinator,
        actor=current_actor,
        allowed_read_tool_names=frozenset(),
    )
    return policy, coordinator, handler


def test_policy_rejects_actor_without_fixed_registry_capabilities() -> None:
    handler = CanonicalHandler(action_definition(PermissionLevel.LEVEL_1, name="fixed_action"))
    registry = ComputerActionRegistry((handler,))

    with pytest.raises(ValueError, match="lacks fixed registry capabilities"):
        ComputerProposalPolicy(
            registry=registry,
            coordinator=FakeCoordinator(
                ActionCoordinatorResult.model_construct(status=ActionCoordinatorStatus.DENIED)
            ),
            actor=actor(capabilities=()),
            allowed_read_tool_names=frozenset(),
        )


async def test_pending_result_returns_structured_approval_without_allowing_execution() -> None:
    handler = CanonicalHandler(action_definition(PermissionLevel.LEVEL_1, name="fixed_action"))
    exact_action = canonical_action(
        handler.definition,
        action_actor=actor(capabilities=("computer.test",)),
        now=FIXED_NOW,
    )
    request = ApprovalRequest(
        approval_id="approval-1",
        action=exact_action,
        requested_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(minutes=1),
    )
    pending = ActionCoordinatorResult(
        status=ActionCoordinatorStatus.PENDING,
        action=exact_action,
        request=request,
        decision=ActionPolicyDecision(
            disposition=PolicyDisposition.APPROVAL_REQUIRED,
            permission_level=PermissionLevel.LEVEL_1,
            policy_version="phase3-policy-v1",
            rule_id="level_1_exact_approval",
            reason="Exact approval required.",
        ),
        approval_id=request.approval_id,
    )
    registry = ComputerActionRegistry((handler,))
    coordinator = FakeCoordinator(pending)
    current_actor = exact_action.actor
    policy = ComputerProposalPolicy(
        registry=registry,
        coordinator=coordinator,
        actor=current_actor,
        allowed_read_tool_names=frozenset(),
    )
    call = ToolCall(id="call-1", name="fixed_action", arguments={"value": "safe"})

    decision = await policy.authorize(
        conversation=Conversation(id="conversation-1"),
        call=call,
        tool=handler.definition.tool,
        arguments=Arguments(value="safe"),
    )

    assert decision.allowed is False
    assert decision.approval_required is True
    assert decision.approval_id == "approval-1"
    assert coordinator.calls[0]["source"] is ApprovalSource.CHAT
    assert str(coordinator.calls[0]["idempotency_key"]).startswith("tool-")
    assert handler.execute_calls == 0


async def test_denial_or_definition_mismatch_never_proposes_or_allows() -> None:
    denied = ActionCoordinatorResult(
        status=ActionCoordinatorStatus.DENIED,
        code="capability_missing",
        message="Denied.",
    )
    policy, coordinator, handler = _policy(denied)
    call = ToolCall(id="call-1", name="fixed_action", arguments={"value": "safe"})
    denied_decision = await policy.authorize(
        conversation=Conversation(id="conversation-1"),
        call=call,
        tool=handler.definition.tool,
        arguments=Arguments(value="safe"),
    )
    assert denied_decision.allowed is False
    assert "capability_missing" in (denied_decision.reason or "")
    assert len(coordinator.calls) == 1

    altered = handler.definition.tool.model_copy(update={"description": "Altered definition."})
    mismatch = await policy.authorize(
        conversation=Conversation(id="conversation-1"),
        call=call,
        tool=altered,
        arguments=Arguments(value="safe"),
    )
    assert mismatch.allowed is False
    assert len(coordinator.calls) == 1


async def test_read_and_unregistered_actions_fail_closed_without_proposal() -> None:
    denied = ActionCoordinatorResult.model_construct(status=ActionCoordinatorStatus.DENIED)
    policy, coordinator, handler = _policy(denied)
    conversation = Conversation(id="conversation-1")
    arguments = Arguments(value="safe")

    read_tool = handler.definition.tool.model_copy(
        update={"permission_level": PermissionLevel.LEVEL_0}
    )
    read_decision = await policy.authorize(
        conversation=conversation,
        call=ToolCall(id="read-1", name=read_tool.name),
        tool=read_tool,
        arguments=arguments,
    )
    assert read_decision.allowed is False

    unknown_tool = handler.definition.tool.model_copy(update={"name": "unknown_action"})
    unknown_decision = await policy.authorize(
        conversation=conversation,
        call=ToolCall(id="unknown-1", name="unknown_action"),
        tool=unknown_tool,
        arguments=arguments,
    )
    assert unknown_decision.allowed is False
    assert "not a fixed registered" in (unknown_decision.reason or "")
    assert coordinator.calls == []


@pytest.mark.parametrize(
    ("status", "reason_fragment"),
    [
        (ActionCoordinatorStatus.APPROVED, "already approved"),
        (ActionCoordinatorStatus.EXECUTED, "terminal broker receipt"),
    ],
)
async def test_terminal_or_approved_action_is_never_reproposed_as_execution(
    status: ActionCoordinatorStatus,
    reason_fragment: str,
) -> None:
    result = ActionCoordinatorResult.model_construct(status=status, approval_id="approval-1")
    policy, coordinator, handler = _policy(result)

    decision = await policy.authorize(
        conversation=Conversation(id="conversation-1"),
        call=ToolCall(id="call-1", name="fixed_action"),
        tool=handler.definition.tool,
        arguments=Arguments(value="safe"),
    )

    assert decision.allowed is False
    assert reason_fragment in (decision.reason or "")
    assert len(coordinator.calls) == 1
