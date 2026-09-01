"""Narrow allowlisted read-only file tool."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from jarvis.core import (
    ApprovalRule,
    PermissionLevel,
    SensitivityClass,
    ToolConcurrency,
    ToolDefinition,
    ToolIdempotency,
    ToolResult,
    ToolRetryPolicy,
    ToolRisk,
    ToolSideEffect,
)


class ReadTextFileArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=2_000)


class ReadTextFileTool:
    def __init__(self, allowed_roots: Iterable[Path], *, max_bytes: int = 100_000) -> None:
        self._roots = tuple(root.expanduser().resolve() for root in allowed_roots)
        if not self._roots:
            raise ValueError("read_text_file requires at least one allowed root")
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._max_bytes = max_bytes
        self._definition = ToolDefinition(
            name="read_text_file",
            version="1",
            description="Read one UTF-8 text file inside configured private allowlisted roots.",
            input_schema=ReadTextFileArguments.model_json_schema(),
            permission_level=PermissionLevel.LEVEL_0,
            approval_rule=ApprovalRule.NONE,
            risk=ToolRisk.READ_ONLY,
            side_effect=ToolSideEffect.NONE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("filesystem.read_text",),
            timeout_seconds=5,
            max_result_bytes=100 * 1_024,
            max_result_items=1,
            idempotency=ToolIdempotency.SIDE_EFFECT_FREE,
            retry_policy=ToolRetryPolicy.TRANSIENT_ONLY,
            concurrency=ToolConcurrency.PARALLEL,
            postcondition=(
                "Resolved target remains a regular file inside an allowlisted root and the "
                "returned content is bounded UTF-8 text."
            ),
            recovery="No side effect occurs; correct the path, encoding, or file size and retry.",
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return ReadTextFileArguments

    async def invoke(self, arguments: BaseModel) -> ToolResult:
        parsed = ReadTextFileArguments.model_validate(arguments)
        return await asyncio.to_thread(self._read, parsed.path)

    def _read(self, path: str) -> ToolResult:
        candidate = Path(path).expanduser().resolve(strict=False)
        if not any(candidate.is_relative_to(root) for root in self._roots):
            return ToolResult(
                content="File access denied: path is outside configured roots.",
                is_error=True,
                data={"code": "path_not_allowed"},
            )
        if not candidate.is_file():
            return ToolResult(
                content="File not found or is not a regular file.",
                is_error=True,
                data={"code": "not_regular_file"},
            )
        if candidate.stat().st_size > self._max_bytes:
            return ToolResult(
                content=f"File exceeds the {self._max_bytes}-byte read limit.",
                is_error=True,
                data={"code": "file_too_large"},
            )
        try:
            content = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ToolResult(
                content="File could not be read as UTF-8 text.",
                is_error=True,
                data={"code": "read_failed"},
            )
        return ToolResult(
            content=content or "File is empty.", data={"bytes": len(content.encode())}
        )
