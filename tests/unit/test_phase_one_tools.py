from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core import (
    ApprovalRule,
    PermissionLevel,
    SensitivityClass,
    ToolConcurrency,
    ToolIdempotency,
    ToolRetryPolicy,
    ToolRisk,
    ToolSideEffect,
    count_json_leaf_items,
)
from jarvis.tools import (
    CurrentTimeArguments,
    CurrentTimeTool,
    ReadTextFileArguments,
    ReadTextFileTool,
    SystemStatusArguments,
    SystemStatusTool,
    phase_one_tools,
)


@pytest.mark.asyncio
async def test_read_text_file_enforces_root_type_encoding_and_size(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    tool = ReadTextFileTool((allowed,), max_bytes=12)

    text_file = allowed / "note.txt"
    text_file.write_text("hello", encoding="utf-8")
    result = await tool.invoke(ReadTextFileArguments(path=str(text_file)))
    assert result.content == "hello"
    assert result.is_error is False

    empty = allowed / "empty.txt"
    empty.write_text("", encoding="utf-8")
    assert (await tool.invoke(ReadTextFileArguments(path=str(empty)))).content == "File is empty."

    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    denied = await tool.invoke(ReadTextFileArguments(path=str(outside)))
    assert denied.is_error and denied.data == {"code": "path_not_allowed"}

    missing = await tool.invoke(ReadTextFileArguments(path=str(allowed / "missing.txt")))
    assert missing.is_error and missing.data == {"code": "not_regular_file"}

    large = allowed / "large.txt"
    large.write_text("x" * 13, encoding="utf-8")
    assert (await tool.invoke(ReadTextFileArguments(path=str(large)))).data == {
        "code": "file_too_large"
    }

    binary = allowed / "binary.txt"
    binary.write_bytes(b"\xff\xfe")
    assert (await tool.invoke(ReadTextFileArguments(path=str(binary)))).data == {
        "code": "read_failed"
    }


@pytest.mark.asyncio
async def test_system_status_and_registry_are_bounded_read_only(tmp_path: Path) -> None:
    tool = SystemStatusTool(probe_path=tmp_path)
    result = await tool.invoke(SystemStatusArguments())
    assert result.is_error is False
    assert isinstance(result.data, dict)
    assert result.data["disk_total_bytes"] > 0
    assert "Python" in result.content
    assert count_json_leaf_items(result.data) <= tool.definition.max_result_items

    clock = CurrentTimeTool()
    clock_result = await clock.invoke(CurrentTimeArguments(timezone="UTC"))
    assert count_json_leaf_items(clock_result.data) <= clock.definition.max_result_items

    registry = phase_one_tools(allowed_file_roots=(tmp_path,))
    assert {tool.definition.name for tool in registry} == {
        "get_current_time",
        "get_system_status",
        "read_text_file",
    }
    for registered in registry:
        definition = registered.definition
        assert definition.version == "1"
        assert definition.permission_level is PermissionLevel.LEVEL_0
        assert definition.approval_rule is ApprovalRule.NONE
        assert definition.requires_approval is False
        assert definition.risk is ToolRisk.READ_ONLY
        assert definition.side_effect is ToolSideEffect.NONE
        assert definition.required_capabilities
        assert 0 < definition.timeout_seconds <= 5
        assert 0 < definition.max_result_bytes <= 100 * 1_024
        assert (
            definition.max_result_items
            == {
                "get_current_time": 3,
                "get_system_status": 8,
                "read_text_file": 1,
            }[definition.name]
        )
        assert definition.idempotency is ToolIdempotency.SIDE_EFFECT_FREE
        assert definition.retry_policy is ToolRetryPolicy.TRANSIENT_ONLY
        assert definition.concurrency is ToolConcurrency.PARALLEL
        assert definition.postcondition
        assert definition.recovery

    sensitivity = {tool.definition.name: tool.definition.sensitivity for tool in registry}
    assert sensitivity == {
        "get_current_time": SensitivityClass.PUBLIC,
        "get_system_status": SensitivityClass.PRIVATE,
        "read_text_file": SensitivityClass.PRIVATE,
    }


def test_read_text_file_requires_root_and_positive_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="root"):
        ReadTextFileTool(())
    with pytest.raises(ValueError, match="positive"):
        ReadTextFileTool((tmp_path,), max_bytes=0)
