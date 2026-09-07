"""Execution ports for bounded task nodes."""

from __future__ import annotations

from typing import Protocol

from pydantic import Field, JsonValue, model_validator

from jarvis.core.models import CoreModel, Identifier

from .models import (
    HandlerName,
    TaskFailureClass,
    TaskNode,
    TaskNodeKind,
    TaskRetryMode,
    TaskUsage,
)


class TaskHandlerDefinition(CoreModel):
    name: HandlerName
    kind: TaskNodeKind
    retry_mode: TaskRetryMode
    max_timeout_seconds: float = Field(gt=0, le=30)
    max_output_bytes: int = Field(default=100 * 1_024, ge=1, le=100 * 1_024)
    requires_approval: bool = False
    supports_compensation: bool = False

    @model_validator(mode="after")
    def require_effect_approval(self) -> TaskHandlerDefinition:
        if self.kind is TaskNodeKind.EFFECT and not self.requires_approval:
            raise ValueError("effect handlers must require an exact approval grant")
        if self.kind is TaskNodeKind.READ_ONLY and self.requires_approval:
            raise ValueError("read-only handlers cannot require approval grants")
        return self


class TaskHandlerContext(CoreModel):
    task_id: Identifier
    host_id: Identifier
    node: TaskNode
    usage: TaskUsage
    dependency_outputs: dict[str, JsonValue | None]


class TaskHandlerResult(CoreModel):
    output: JsonValue | None = None


class TaskHandlerError(RuntimeError):
    def __init__(
        self,
        code: str,
        failure_class: TaskFailureClass,
        *,
        partial_effect: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.failure_class = failure_class
        self.partial_effect = partial_effect


class TaskHandler(Protocol):
    definition: TaskHandlerDefinition

    async def validate(self, context: TaskHandlerContext) -> None: ...

    async def execute(self, context: TaskHandlerContext) -> TaskHandlerResult: ...

    async def verify(self, context: TaskHandlerContext, result: TaskHandlerResult) -> bool: ...

    async def compensate(
        self, context: TaskHandlerContext, result: TaskHandlerResult | None
    ) -> bool: ...

    async def reconcile(self, context: TaskHandlerContext) -> TaskHandlerResult | None: ...
