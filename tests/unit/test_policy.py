import pytest
from pydantic import BaseModel

from jarvis.core import (
    ApprovalRule,
    Conversation,
    PermissionLevel,
    SensitivityClass,
    ToolCall,
    ToolConcurrency,
    ToolDefinition,
    ToolIdempotency,
    ToolRetryPolicy,
    ToolRisk,
    ToolSideEffect,
)
from jarvis.security import DenyByDefaultPolicy, phase_one_policy


class EmptyArguments(BaseModel):
    pass


def definition(
    name: str,
    *,
    permission_level: PermissionLevel = PermissionLevel.LEVEL_0,
    approval_rule: ApprovalRule = ApprovalRule.NONE,
    risk: ToolRisk = ToolRisk.READ_ONLY,
    side_effect: ToolSideEffect = ToolSideEffect.NONE,
    idempotency: ToolIdempotency = ToolIdempotency.SIDE_EFFECT_FREE,
    retry_policy: ToolRetryPolicy = ToolRetryPolicy.TRANSIENT_ONLY,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        version="1",
        description="test tool",
        input_schema={"type": "object"},
        permission_level=permission_level,
        approval_rule=approval_rule,
        risk=risk,
        side_effect=side_effect,
        sensitivity=SensitivityClass.PUBLIC,
        required_capabilities=("test.tool.invoke",),
        timeout_seconds=1,
        max_result_bytes=1_024,
        max_result_items=1,
        idempotency=idempotency,
        retry_policy=retry_policy,
        concurrency=ToolConcurrency.PARALLEL,
        postcondition="Test result returned.",
        recovery="No recovery needed for this test.",
    )


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
async def test_phase_one_policy_allows_only_audited_read_only_tools() -> None:
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
    assert policy.allowed_tool_names == frozenset(
        {"get_current_time", "get_system_status", "read_text_file"}
    )


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


@pytest.mark.asyncio
async def test_allowlist_cannot_bypass_risk_or_approval_policy() -> None:
    policy = DenyByDefaultPolicy({"danger"})
    for tool in (
        definition(
            "danger",
            permission_level=PermissionLevel.LEVEL_4,
            approval_rule=ApprovalRule.DISABLED,
            risk=ToolRisk.DESTRUCTIVE,
            side_effect=ToolSideEffect.ADMINISTRATIVE,
            idempotency=ToolIdempotency.NON_IDEMPOTENT,
            retry_policy=ToolRetryPolicy.RECONCILE_FIRST,
        ),
        definition(
            "danger",
            permission_level=PermissionLevel.LEVEL_3,
            approval_rule=ApprovalRule.EXACT_RECENT_AUTH,
            risk=ToolRisk.SENSITIVE,
        ),
    ):
        decision = await policy.authorize(
            conversation=Conversation(id="conversation"),
            call=ToolCall(id="call", name="danger"),
            tool=tool,
            arguments=EmptyArguments(),
        )
        assert decision.allowed is False
        assert "approval-capable" in (decision.reason or "")
