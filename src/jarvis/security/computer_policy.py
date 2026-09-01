"""Runtime policy that turns model tool calls into durable proposals only."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from jarvis.computer.actions import ActionCanonicalizer
from jarvis.computer.registry import ComputerActionRegistry
from jarvis.core import (
    Conversation,
    PermissionLevel,
    PolicyDecision,
    ToolCall,
    ToolDefinition,
)
from jarvis.permissions import (
    ActionCoordinatorResult,
    ActionCoordinatorStatus,
    ActorContext,
    ApprovalSource,
    sha256_fingerprint,
)

from .policy import DenyByDefaultPolicy


class ProposalCoordinator(Protocol):
    async def propose(
        self,
        canonicalizer: ActionCanonicalizer,
        raw_arguments: BaseModel,
        *,
        actor: ActorContext,
        source: ApprovalSource | str,
        conversation_id: str | None = None,
        tool_call_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ActionCoordinatorResult: ...


class ComputerProposalPolicy:
    """Allow reads explicitly; persist side-effect calls as approval requests."""

    def __init__(
        self,
        *,
        registry: ComputerActionRegistry,
        coordinator: ProposalCoordinator,
        actor: ActorContext,
        allowed_read_tool_names: frozenset[str],
    ) -> None:
        missing = set(registry.required_capabilities).difference(actor.capabilities)
        if missing:
            raise ValueError("computer actor lacks fixed registry capabilities")
        self._registry = registry
        self._coordinator = coordinator
        self._actor = actor
        self._read_policy = DenyByDefaultPolicy(allowed_read_tool_names)

    async def authorize(
        self,
        *,
        conversation: Conversation,
        call: ToolCall,
        tool: ToolDefinition,
        arguments: BaseModel,
    ) -> PolicyDecision:
        if tool.permission_level is PermissionLevel.LEVEL_0:
            return await self._read_policy.authorize(
                conversation=conversation,
                call=call,
                tool=tool,
                arguments=arguments,
            )
        action = self._registry.action(call.name)
        if action is None or call.name != tool.name:
            return PolicyDecision(
                allowed=False,
                reason="Tool is not a fixed registered computer action.",
            )
        if action.definition.tool != tool:
            return PolicyDecision(
                allowed=False,
                reason="Tool definition differs from the fixed broker registration.",
            )
        idempotency_key = "tool-" + sha256_fingerprint(
            {
                "conversation_id": conversation.id,
                "tool_call_id": call.id,
                "action_id": call.name,
                "arguments": arguments.model_dump(mode="json"),
            }
        ).removeprefix("sha256:")
        result = await self._coordinator.propose(
            action,
            arguments,
            actor=self._actor,
            source=ApprovalSource.CHAT,
            conversation_id=conversation.id,
            tool_call_id=call.id,
            idempotency_key=idempotency_key,
        )
        if result.status in {
            ActionCoordinatorStatus.PENDING,
            ActionCoordinatorStatus.APPROVED,
        }:
            assert result.approval_id is not None
            detail = (
                "Action is already approved; execute its one-use grant from the trusted local "
                "computer command."
                if result.status is ActionCoordinatorStatus.APPROVED
                else "Review this exact action in the trusted local computer approval command."
            )
            return PolicyDecision(
                allowed=False,
                reason=detail,
                approval_required=True,
                approval_id=result.approval_id,
            )
        if result.status is ActionCoordinatorStatus.EXECUTED:
            return PolicyDecision(
                allowed=False,
                reason="Exact action already has a terminal broker receipt; it will not run again.",
            )
        return PolicyDecision(
            allowed=False,
            reason=f"Computer action denied by deterministic policy ({result.code or 'denied'}).",
        )
