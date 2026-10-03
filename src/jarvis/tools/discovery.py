"""Read-only discovery across fixed model tools and task handlers."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from jarvis.computer.registry import ComputerActionRegistry
from jarvis.core import Tool, ToolDefinition
from jarvis.core.models import CoreModel
from jarvis.planning import TaskHandlerRegistry
from jarvis.planning.contracts import TaskHandlerDefinition


class DiscoveryOwner(StrEnum):
    CORE = "core"
    COMPUTER_READ = "computer_read"
    COMPUTER_ACTION = "computer_action"
    TASK_SCHEDULER = "task_scheduler"


class DiscoveryEntry(CoreModel):
    name: str
    owner: DiscoveryOwner
    definition: ToolDefinition | TaskHandlerDefinition


class UnifiedToolRegistry:
    """Snapshot metadata only; never exposes handlers or grants execution authority."""

    def __init__(
        self,
        *,
        model_tools: Iterable[Tool],
        task_handlers: TaskHandlerRegistry,
        computer: ComputerActionRegistry | None = None,
    ) -> None:
        entries: dict[str, DiscoveryEntry] = {}
        seen_computer: set[str] = set()
        for tool in model_tools:
            definition = ToolDefinition.model_validate(tool.definition).model_copy(deep=True)
            name = definition.name
            if name in entries:
                raise ValueError(f"duplicate discovery name: {name}")
            owner = DiscoveryOwner.CORE
            if computer is not None and computer.tool(name) is not None:
                if computer.tool(name) is not tool:
                    raise ValueError(f"computer discovery tool mismatch: {name}")
                owner = (
                    DiscoveryOwner.COMPUTER_ACTION
                    if computer.action(name) is not None
                    else DiscoveryOwner.COMPUTER_READ
                )
                seen_computer.add(name)
            entries[name] = DiscoveryEntry(name=name, owner=owner, definition=definition)

        if computer is not None:
            expected = {tool.definition.name for tool in computer.model_tools}
            if seen_computer != expected:
                raise ValueError("computer discovery registry does not match model tools")

        for task_definition in task_handlers.definitions:
            if task_definition.name in entries:
                raise ValueError(f"duplicate discovery name: {task_definition.name}")
            entries[task_definition.name] = DiscoveryEntry(
                name=task_definition.name,
                owner=DiscoveryOwner.TASK_SCHEDULER,
                definition=task_definition,
            )
        self._entries = tuple(sorted(entries.values(), key=lambda entry: entry.name))
        self._by_name = {entry.name: entry for entry in self._entries}

    @property
    def entries(self) -> tuple[DiscoveryEntry, ...]:
        return tuple(entry.model_copy(deep=True) for entry in self._entries)

    def get(self, name: str) -> DiscoveryEntry | None:
        entry = self._by_name.get(name)
        return entry.model_copy(deep=True) if entry is not None else None
