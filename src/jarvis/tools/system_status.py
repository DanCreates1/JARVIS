"""Bounded read-only operating-system status tool."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict

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


class SystemStatusArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SystemStatusTool:
    def __init__(self, *, probe_path: Path) -> None:
        self._probe_path = probe_path.resolve()
        self._definition = ToolDefinition(
            name="get_system_status",
            version="1",
            description="Read bounded operating-system, Python, and storage capacity information.",
            input_schema=SystemStatusArguments.model_json_schema(),
            permission_level=PermissionLevel.LEVEL_0,
            approval_rule=ApprovalRule.NONE,
            risk=ToolRisk.READ_ONLY,
            side_effect=ToolSideEffect.NONE,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("system.status.read",),
            timeout_seconds=2,
            max_result_bytes=8_192,
            max_result_items=8,
            idempotency=ToolIdempotency.SIDE_EFFECT_FREE,
            retry_policy=ToolRetryPolicy.TRANSIENT_ONLY,
            concurrency=ToolConcurrency.PARALLEL,
            postcondition="Result contains bounded OS, Python, CPU, and storage metadata.",
            recovery=(
                "No side effect occurs; restore access to the configured probe path and retry."
            ),
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return SystemStatusArguments

    async def invoke(self, arguments: BaseModel) -> ToolResult:
        del arguments
        usage = shutil.disk_usage(self._probe_path)
        data = {
            "os": platform.system(),
            "os_release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "disk_total_bytes": usage.total,
            "disk_free_bytes": usage.free,
            "python_executable_name": Path(sys.executable).name,
        }
        return ToolResult(
            content=(
                f"{data['os']} {data['os_release']} on {data['machine']}; "
                f"Python {data['python']}; {data['cpu_count']} logical CPUs; "
                f"{usage.free / (1024**3):.1f} GiB disk free."
            ),
            data=data,
        )
