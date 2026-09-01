from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import ValidationError

from jarvis.core import (
    ApprovalRule,
    PermissionLevel,
    SensitivityClass,
    ToolConcurrency,
    ToolDefinition,
    ToolIdempotency,
    ToolRetryPolicy,
    ToolRisk,
    ToolSideEffect,
)


def definition_values(**updates: object) -> dict[str, Any]:
    values: dict[str, Any] = {
        "name": "test_tool",
        "version": "1",
        "description": "A fully declared test tool.",
        "input_schema": {"type": "object", "additionalProperties": False},
        "permission_level": PermissionLevel.LEVEL_0,
        "approval_rule": ApprovalRule.NONE,
        "risk": ToolRisk.READ_ONLY,
        "side_effect": ToolSideEffect.NONE,
        "sensitivity": SensitivityClass.PUBLIC,
        "required_capabilities": ("test.tool.invoke",),
        "timeout_seconds": 1,
        "max_result_bytes": 4_096,
        "max_result_items": 1,
        "idempotency": ToolIdempotency.SIDE_EFFECT_FREE,
        "retry_policy": ToolRetryPolicy.TRANSIENT_ONLY,
        "concurrency": ToolConcurrency.PARALLEL,
        "postcondition": "The declared result is returned.",
        "recovery": "No side effect occurs; correct the request and retry.",
    }
    values.update(updates)
    return values


@pytest.mark.parametrize(
    ("level", "risk", "side_effect", "approval", "idempotency", "retry"),
    [
        (
            PermissionLevel.LEVEL_0,
            ToolRisk.READ_ONLY,
            ToolSideEffect.NONE,
            ApprovalRule.NONE,
            ToolIdempotency.SIDE_EFFECT_FREE,
            ToolRetryPolicy.TRANSIENT_ONLY,
        ),
        (
            PermissionLevel.LEVEL_1,
            ToolRisk.REVERSIBLE,
            ToolSideEffect.REVERSIBLE,
            ApprovalRule.EXPLICIT_ENABLEMENT,
            ToolIdempotency.IDEMPOTENT,
            ToolRetryPolicy.TRANSIENT_ONLY,
        ),
        (
            PermissionLevel.LEVEL_2,
            ToolRisk.REVERSIBLE,
            ToolSideEffect.EXTERNAL,
            ApprovalRule.POLICY_OR_EXPLICIT,
            ToolIdempotency.IDEMPOTENCY_KEY,
            ToolRetryPolicy.TRANSIENT_ONLY,
        ),
        (
            PermissionLevel.LEVEL_3,
            ToolRisk.SENSITIVE,
            ToolSideEffect.NONE,
            ApprovalRule.EXACT_RECENT_AUTH,
            ToolIdempotency.SIDE_EFFECT_FREE,
            ToolRetryPolicy.NEVER,
        ),
        (
            PermissionLevel.LEVEL_4,
            ToolRisk.DESTRUCTIVE,
            ToolSideEffect.ADMINISTRATIVE,
            ApprovalRule.DISABLED,
            ToolIdempotency.NON_IDEMPOTENT,
            ToolRetryPolicy.RECONCILE_FIRST,
        ),
    ],
)
def test_permission_levels_accept_only_explicit_coherent_metadata(
    level: PermissionLevel,
    risk: ToolRisk,
    side_effect: ToolSideEffect,
    approval: ApprovalRule,
    idempotency: ToolIdempotency,
    retry: ToolRetryPolicy,
) -> None:
    definition = ToolDefinition.model_validate(
        definition_values(
            permission_level=level,
            risk=risk,
            side_effect=side_effect,
            approval_rule=approval,
            idempotency=idempotency,
            retry_policy=retry,
        )
    )

    assert int(definition.permission_level) == int(level)
    assert definition.requires_approval is (approval is not ApprovalRule.NONE)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {"permission_level": PermissionLevel.LEVEL_0, "risk": ToolRisk.REVERSIBLE},
            "risk",
        ),
        (
            {
                "permission_level": PermissionLevel.LEVEL_1,
                "risk": ToolRisk.REVERSIBLE,
                "approval_rule": ApprovalRule.EXPLICIT_ENABLEMENT,
                "side_effect": ToolSideEffect.NONE,
            },
            "side effect",
        ),
        (
            {
                "permission_level": PermissionLevel.LEVEL_2,
                "risk": ToolRisk.REVERSIBLE,
                "side_effect": ToolSideEffect.REVERSIBLE,
                "approval_rule": ApprovalRule.NONE,
                "idempotency": ToolIdempotency.IDEMPOTENT,
            },
            "approval rule",
        ),
        (
            {
                "permission_level": PermissionLevel.LEVEL_3,
                "risk": ToolRisk.SENSITIVE,
                "approval_rule": ApprovalRule.EXACT_RECENT_AUTH,
                "side_effect": ToolSideEffect.NONE,
                "idempotency": ToolIdempotency.IDEMPOTENT,
            },
            "side-effect-free idempotency",
        ),
        (
            {
                "permission_level": PermissionLevel.LEVEL_3,
                "risk": ToolRisk.DESTRUCTIVE,
                "approval_rule": ApprovalRule.EXACT_RECENT_AUTH,
                "side_effect": ToolSideEffect.IRREVERSIBLE,
                "idempotency": ToolIdempotency.NON_IDEMPOTENT,
                "retry_policy": ToolRetryPolicy.TRANSIENT_ONLY,
            },
            "non-idempotent",
        ),
        (
            {
                "permission_level": PermissionLevel.LEVEL_4,
                "risk": ToolRisk.DESTRUCTIVE,
                "approval_rule": ApprovalRule.STEP_UP,
                "side_effect": ToolSideEffect.ADMINISTRATIVE,
                "idempotency": ToolIdempotency.IDEMPOTENT,
                "retry_policy": ToolRetryPolicy.TRANSIENT_ONLY,
            },
            "administrative",
        ),
    ],
)
def test_tool_definition_rejects_incoherent_security_metadata(
    updates: Mapping[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        ToolDefinition.model_validate(definition_values(**updates))


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"version": "0"}, "version"),
        ({"version": "v1"}, "version"),
        ({"input_schema": {"type": "string"}}, "object"),
        ({"required_capabilities": ()}, "at least 1"),
        (
            {"required_capabilities": ("test.tool.invoke", "test.tool.invoke")},
            "distinct",
        ),
        ({"required_capabilities": ("Test Tool",)}, "string_pattern_mismatch"),
        ({"timeout_seconds": 0}, "greater than 0"),
        ({"timeout_seconds": 31}, "less than or equal to 30"),
        ({"max_result_bytes": 0}, "greater than or equal to 1"),
        ({"max_result_bytes": 102_401}, "less than or equal to 102400"),
        ({"max_result_items": 0}, "greater than or equal to 1"),
        ({"max_result_items": 1_001}, "less than or equal to 1000"),
        ({"postcondition": ""}, "at least 1"),
        ({"recovery": ""}, "at least 1"),
    ],
)
def test_tool_definition_rejects_unbounded_or_ambiguous_metadata(
    updates: Mapping[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        ToolDefinition.model_validate(definition_values(**updates))


def test_legacy_minimal_definition_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        ToolDefinition(
            name="legacy_tool",
            description="Missing operational and security metadata.",
            input_schema={"type": "object"},
        )
