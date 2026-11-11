"""Deny-by-default authorization independent from model instructions."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from jarvis.core import Conversation, PolicyDecision, ToolCall, ToolDefinition, ToolRisk


class DenyByDefaultPolicy:
    """Authorize only explicitly allowlisted tool names.

    The language model cannot add to this allowlist. Future side-effecting tools must use a
    richer approval policy; adding them here without an approval broker is intentionally not
    sufficient architecture for release.
    """

    def __init__(self, allowed_tool_names: Iterable[str] = ()) -> None:
        self._allowed_tool_names = frozenset(allowed_tool_names)

    @property
    def allowed_tool_names(self) -> frozenset[str]:
        return self._allowed_tool_names

    async def authorize(
        self,
        *,
        conversation: Conversation,
        call: ToolCall,
        tool: ToolDefinition,
        arguments: BaseModel,
    ) -> PolicyDecision:
        del conversation, arguments
        if call.name != tool.name:
            return PolicyDecision(
                allowed=False,
                reason="Tool call and registered definition do not match.",
            )
        if tool.name not in self._allowed_tool_names:
            return PolicyDecision(
                allowed=False,
                reason=f"Tool '{tool.name}' is not allowed by the active policy.",
            )
        if tool.risk is not ToolRisk.READ_ONLY or tool.requires_approval:
            return PolicyDecision(
                allowed=False,
                reason=f"Tool '{tool.name}' requires an approval-capable policy.",
            )
        return PolicyDecision(allowed=True)


def phase_one_policy() -> DenyByDefaultPolicy:
    """Authorize the single audited, read-only Phase 1 tool."""
    return DenyByDefaultPolicy({"get_current_time", "get_system_status", "read_text_file"})
