"""Metadata discovery never becomes an execution or approval path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import jarvis.cli as cli
from jarvis.computer.config import ComputerAccessPolicy
from jarvis.computer.registry import build_computer_registry
from jarvis.config import Settings
from jarvis.core import PermissionLevel, ToolDefinition
from jarvis.planning import TaskHandlerRegistry, ValueTaskHandler
from jarvis.tools import CurrentTimeTool, DiscoveryOwner, UnifiedToolRegistry


def test_discovery_preserves_owner_and_detaches_nested_schema(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    controlled.mkdir()
    computer = build_computer_registry(
        ComputerAccessPolicy(
            enabled=True,
            maximum_permission_level=PermissionLevel.LEVEL_1,
            controlled_root=controlled,
        )
    )
    clock = CurrentTimeTool()
    catalog = UnifiedToolRegistry(
        model_tools=(clock, *computer.model_tools),
        task_handlers=TaskHandlerRegistry((ValueTaskHandler(),)),
        computer=computer,
    )

    assert catalog.get("get_current_time").owner is DiscoveryOwner.CORE
    assert catalog.get("search_controlled_files").owner is DiscoveryOwner.COMPUTER_READ
    action = catalog.get("control_media")
    assert action is not None
    assert action.owner is DiscoveryOwner.COMPUTER_ACTION
    assert isinstance(action.definition, ToolDefinition)
    assert action.definition.permission_level is PermissionLevel.LEVEL_1
    assert catalog.get("task.value").owner is DiscoveryOwner.TASK_SCHEDULER
    assert catalog.get("unknown") is None
    assert catalog.get("CONTROL_MEDIA") is None

    action.definition.input_schema["type"] = "array"
    fresh = catalog.get("control_media")
    assert fresh is not None
    assert fresh.definition.input_schema["type"] == "object"
    assert computer.action("control_media") is not None


def test_discovery_rejects_missing_and_duplicate_registrations(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    controlled.mkdir()
    computer = build_computer_registry(
        ComputerAccessPolicy(
            enabled=True,
            maximum_permission_level=PermissionLevel.LEVEL_1,
            controlled_root=controlled,
        )
    )
    clock = CurrentTimeTool()
    tasks = TaskHandlerRegistry((ValueTaskHandler(),))
    with pytest.raises(ValueError, match="duplicate discovery name"):
        UnifiedToolRegistry(model_tools=(clock, clock), task_handlers=tasks)
    with pytest.raises(ValueError, match="does not match model tools"):
        UnifiedToolRegistry(model_tools=(clock,), task_handlers=tasks, computer=computer)


def test_tools_cli_json_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(data_dir=tmp_path, cloud_policy="local_only", _env_file=None)
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)
    result = CliRunner().invoke(cli.app, ["tools", "list", "--json"])

    assert result.exit_code == 0, result.output
    entries = json.loads(result.output)
    assert {entry["name"] for entry in entries} >= {
        "get_current_time",
        "task.value",
        "research.report.inspect",
    }
    assert all(entry["owner"] != "computer_action" for entry in entries)
    assert (tmp_path / "jarvis.db").exists()

    unknown = CliRunner().invoke(cli.app, ["tools", "list", "--name", "unknown"])
    assert unknown.exit_code == 2
