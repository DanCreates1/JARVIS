from __future__ import annotations

from datetime import timedelta

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
