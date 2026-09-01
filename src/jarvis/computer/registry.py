"""Fixed Phase 3 computer-action registry and non-mutating model adapters."""

from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType
from typing import Protocol

from pydantic import BaseModel

from jarvis.core import PermissionLevel, Tool, ToolDefinition, ToolResult
from jarvis.permissions import ActionHandler

from .actions import (
    ActionCanonicalizer,
    AppGroupLaunchHandler,
    ApplicationLaunchHandler,
    LocalPrinterStatusTool,
    MediaControlHandler,
    ReversibleMoveHandler,
    SearchControlledFilesTool,
)
from .config import ComputerAccessPolicy


class BrokeredComputerAction(ActionCanonicalizer, ActionHandler, Protocol):
    """One canonicalizer whose mutation methods are callable only by the broker."""


class BrokeredActionTool:
    """Expose schema to the model while making direct invocation inert and fail-closed."""

    def __init__(self, action: BrokeredComputerAction) -> None:
        self._action = action

    @property
    def action(self) -> BrokeredComputerAction:
        return self._action

    @property
    def definition(self) -> ToolDefinition:
        return self._action.definition.tool

    @property
    def input_model(self) -> type[BaseModel]:
        return self._action.input_model

    async def invoke(self, arguments: BaseModel) -> ToolResult:
        del arguments
        return ToolResult(
            content=(
                "Direct computer-action execution is prohibited. Use the trusted approval "
                "broker and one-use grant."
            ),
            is_error=True,
            data={"code": "broker_required"},
        )


class ComputerActionRegistry:
    """Immutable reviewed registry shared by proposal policy and local broker."""

    def __init__(
        self,
        actions: Iterable[BrokeredComputerAction],
        *,
        read_tools: Iterable[Tool] = (),
    ) -> None:
        action_map: dict[str, BrokeredComputerAction] = {}
        adapter_map: dict[str, BrokeredActionTool] = {}
        dispatch_keys: set[str] = set()
        for action in actions:
            definition = action.definition
            name = definition.action_id
            if name in action_map:
                raise ValueError(f"duplicate computer action name: {name}")
            if definition.dispatch_key in dispatch_keys:
                raise ValueError(f"duplicate computer action dispatch: {definition.dispatch_key}")
            action_map[name] = action
            adapter_map[name] = BrokeredActionTool(action)
            dispatch_keys.add(definition.dispatch_key)
        if not action_map:
            raise ValueError("computer action registry requires at least one brokered action")

        read_map: dict[str, Tool] = {}
        for tool in read_tools:
            read_definition = ToolDefinition.model_validate(tool.definition)
            if read_definition.name in action_map or read_definition.name in read_map:
                raise ValueError(f"duplicate computer tool name: {read_definition.name}")
            read_map[read_definition.name] = tool

        self._actions = MappingProxyType(action_map)
        self._adapters = MappingProxyType(adapter_map)
        self._read_tools = MappingProxyType(read_map)

    @property
    def actions(self) -> tuple[BrokeredComputerAction, ...]:
        return tuple(self._actions.values())

    @property
    def read_tools(self) -> tuple[Tool, ...]:
        return tuple(self._read_tools.values())

    @property
    def model_tools(self) -> tuple[Tool, ...]:
        return (*self.read_tools, *self._adapters.values())

    def action(self, name: str) -> BrokeredComputerAction | None:
        return self._actions.get(name)

    def tool(self, name: str) -> Tool | None:
        return self._read_tools.get(name) or self._adapters.get(name)

    @property
    def required_capabilities(self) -> tuple[str, ...]:
        values = {
            capability
            for tool in self.model_tools
            for capability in tool.definition.required_capabilities
        }
        return tuple(sorted(values))


def build_computer_registry(policy: ComputerAccessPolicy) -> ComputerActionRegistry:
    """Build the complete fixed Phase 3 registry from host-owned configuration."""
    if not policy.enabled:
        raise ValueError("computer access policy is disabled")
    if not policy.controlled_root.is_dir() or policy.controlled_root.is_symlink():
        raise ValueError("controlled root must exist as a regular non-link directory")
    if policy.maximum_permission_level < PermissionLevel.LEVEL_1:
        raise ValueError("enabled computer access requires at least permission Level 1")

    from .extra_actions import (
        OpenBrowserTargetHandler,
        SetClipboardTextHandler,
        SetMasterVolumeHandler,
    )
    from .printing import PrintControlledTextHandler

    actions: list[BrokeredComputerAction] = [
        MediaControlHandler(),
        SetMasterVolumeHandler(policy),
    ]
    if policy.applications:
        actions.append(ApplicationLaunchHandler(policy))
    if policy.app_groups:
        actions.append(AppGroupLaunchHandler(policy))
    if policy.maximum_permission_level >= PermissionLevel.LEVEL_2:
        actions.extend((SetClipboardTextHandler(policy), ReversibleMoveHandler(policy)))
        if policy.browser_targets:
            actions.append(OpenBrowserTargetHandler(policy))
        if policy.printers:
            actions.append(PrintControlledTextHandler(policy))

    read_tools: list[Tool] = [
        SearchControlledFilesTool(policy),
        LocalPrinterStatusTool(policy),
    ]
    return ComputerActionRegistry(actions, read_tools=read_tools)
