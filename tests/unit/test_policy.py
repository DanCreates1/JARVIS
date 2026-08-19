import pytest
from pydantic import BaseModel

from jarvis.core import Conversation, ToolCall, ToolDefinition
from jarvis.security import DenyByDefaultPolicy, phase_one_policy


class EmptyArguments(BaseModel):
    pass


def definition(name: str) -> ToolDefinition:
    return ToolDefinition(name=name, description="test tool", input_schema={"type": "object"})


@pytest.mark.asyncio
async def test_policy_denies_everything_by_default() -> None:
    decision = await DenyByDefaultPolicy().authorize(
        conversation=Conversation(id="conversation"),
        call=ToolCall(id="call", name="get_current_time"),
        tool=definition("get_current_time"),
        arguments=EmptyArguments(),
    )

    assert decision.allowed is False
    assert "not allowed" in (decision.reason or "")


@pytest.mark.asyncio
async def test_phase_one_policy_allows_only_clock() -> None:
    policy = phase_one_policy()
    clock_decision = await policy.authorize(
        conversation=Conversation(id="conversation"),
        call=ToolCall(id="clock-call", name="get_current_time"),
        tool=definition("get_current_time"),
        arguments=EmptyArguments(),
    )
    other_decision = await policy.authorize(
        conversation=Conversation(id="conversation"),
        call=ToolCall(id="other-call", name="open_application"),
        tool=definition("open_application"),
        arguments=EmptyArguments(),
    )

    assert clock_decision.allowed is True
    assert other_decision.allowed is False
    assert policy.allowed_tool_names == frozenset({"get_current_time"})


@pytest.mark.asyncio
async def test_policy_denies_mismatched_registry_definition() -> None:
    decision = await phase_one_policy().authorize(
        conversation=Conversation(id="conversation"),
        call=ToolCall(id="call", name="get_current_time"),
        tool=definition("different_tool"),
        arguments=EmptyArguments(),
    )

    assert decision.allowed is False
    assert "do not match" in (decision.reason or "")
