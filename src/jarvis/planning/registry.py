"""Immutable task-handler registry and safe local handlers."""

from __future__ import annotations

from collections.abc import Iterable

from .contracts import (
    TaskHandler,
    TaskHandlerContext,
    TaskHandlerDefinition,
    TaskHandlerResult,
)
from .models import TaskNodeKind, TaskRetryMode


class TaskHandlerRegistry:
    def __init__(self, handlers: Iterable[TaskHandler]) -> None:
        mapping: dict[str, TaskHandler] = {}
        for handler in handlers:
            name = handler.definition.name
            if name in mapping:
                raise ValueError(f"duplicate task handler: {name}")
            mapping[name] = handler
        if not mapping:
            raise ValueError("at least one task handler is required")
        self._handlers = mapping

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def get(self, name: str) -> TaskHandler:
        try:
            return self._handlers[name]
        except KeyError:
            raise KeyError(f"unknown task handler: {name}") from None


class ValueTaskHandler:
    """Return one bounded JSON value; useful for deterministic local graph composition."""

    definition = TaskHandlerDefinition(
        name="task.value",
        kind=TaskNodeKind.READ_ONLY,
        retry_mode=TaskRetryMode.NEVER,
        max_timeout_seconds=5,
    )

    async def validate(self, context: TaskHandlerContext) -> None:
        if set(context.node.arguments) != {"value"}:
            raise ValueError("task.value requires exactly one 'value' argument")

    async def execute(self, context: TaskHandlerContext) -> TaskHandlerResult:
        return TaskHandlerResult(output=context.node.arguments["value"])

    async def verify(self, context: TaskHandlerContext, result: TaskHandlerResult) -> bool:
        return result.output == context.node.arguments["value"]

    async def compensate(
        self, context: TaskHandlerContext, result: TaskHandlerResult | None
    ) -> bool:
        return True

    async def reconcile(self, context: TaskHandlerContext) -> TaskHandlerResult | None:
        return None
