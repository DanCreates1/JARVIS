"""Side-effect-free current-time tool."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

Now = Callable[[tzinfo | None], datetime]


class CurrentTimeArguments(BaseModel):
    """Validated arguments accepted by ``get_current_time``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timezone: str = Field(
        default="local",
        min_length=1,
        max_length=100,
        description="'local', 'UTC', or an IANA timezone such as 'America/Toronto'.",
    )

    @field_validator("timezone")
    @classmethod
    def normalize_timezone(cls, value: str) -> str:
        return value.strip()


def _now(zone: tzinfo | None) -> datetime:
    if zone is None:
        return datetime.now().astimezone()
    return datetime.now(zone)


class CurrentTimeTool:
    """Read the system clock without mutating local or external state."""

    def __init__(self, now: Now = _now) -> None:
        self._now = now
        self._definition = ToolDefinition(
            name="get_current_time",
            version="1",
            description=(
                "Return the current date and time for the local system, UTC, or a named "
                "IANA timezone. This tool is read-only."
            ),
            input_schema=CurrentTimeArguments.model_json_schema(),
            permission_level=PermissionLevel.LEVEL_0,
            approval_rule=ApprovalRule.NONE,
            risk=ToolRisk.READ_ONLY,
            side_effect=ToolSideEffect.NONE,
            sensitivity=SensitivityClass.PUBLIC,
            required_capabilities=("clock.read",),
            timeout_seconds=1,
            max_result_bytes=4_096,
            max_result_items=3,
            idempotency=ToolIdempotency.SIDE_EFFECT_FREE,
            retry_policy=ToolRetryPolicy.TRANSIENT_ONLY,
            concurrency=ToolConcurrency.PARALLEL,
            postcondition="Result contains a timezone-aware ISO-8601 timestamp.",
            recovery="No side effect occurs; correct the timezone and retry.",
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return CurrentTimeArguments

    async def invoke(self, arguments: BaseModel) -> ToolResult:
        validated = CurrentTimeArguments.model_validate(arguments)
        requested_zone = validated.timezone
        try:
            if requested_zone.casefold() == "local":
                zone: tzinfo | None = None
                zone_label = "local"
            elif requested_zone.casefold() == "utc":
                zone = UTC
                zone_label = "UTC"
            else:
                zone = ZoneInfo(requested_zone)
                zone_label = requested_zone
        except (ZoneInfoNotFoundError, ValueError):
            return ToolResult(
                content=f"Unknown timezone: {requested_zone}",
                is_error=True,
                data={"code": "unknown_timezone", "timezone": requested_zone},
            )

        current = self._now(zone)
        if current.tzinfo is None:
            current = current.replace(tzinfo=zone or UTC)
        offset = current.utcoffset()
        offset_seconds = int(offset.total_seconds()) if offset is not None else 0
        iso_value = current.isoformat(timespec="seconds")
        return ToolResult(
            content=f"The current time in {zone_label} is {iso_value}.",
            data={
                "iso8601": iso_value,
                "timezone": zone_label,
                "utc_offset_seconds": offset_seconds,
            },
        )
