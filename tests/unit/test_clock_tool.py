from datetime import UTC, datetime, tzinfo

import pytest
from pydantic import ValidationError

from jarvis.core import ToolResult
from jarvis.tools.clock import CurrentTimeArguments, CurrentTimeTool


def fixed_now(zone: tzinfo | None) -> datetime:
    return datetime(2026, 8, 18, 17, 30, 45, tzinfo=zone or UTC)


@pytest.mark.asyncio
async def test_current_time_tool_returns_machine_readable_result() -> None:
    tool = CurrentTimeTool(now=fixed_now)

    result = await tool.invoke(CurrentTimeArguments(timezone="UTC"))

    assert result == ToolResult(
        content="The current time in UTC is 2026-08-18T17:30:45+00:00.",
        data={
            "iso8601": "2026-08-18T17:30:45+00:00",
            "timezone": "UTC",
            "utc_offset_seconds": 0,
        },
    )


@pytest.mark.asyncio
async def test_current_time_tool_reports_unknown_timezone() -> None:
    result = await CurrentTimeTool(now=fixed_now).invoke(
        CurrentTimeArguments(timezone="Invalid/Nowhere")
    )

    assert result.is_error is True
    assert result.data == {
        "code": "unknown_timezone",
        "timezone": "Invalid/Nowhere",
    }


@pytest.mark.asyncio
async def test_current_time_tool_handles_local_and_naive_clocks() -> None:
    local = await CurrentTimeTool().invoke(CurrentTimeArguments(timezone=" local "))
    assert local.is_error is False
    assert local.data["timezone"] == "local"
    assert datetime.fromisoformat(str(local.data["iso8601"])).tzinfo is not None

    def naive_now(_zone: tzinfo | None) -> datetime:
        return datetime(2026, 8, 18, 17, 30, 45, tzinfo=UTC).replace(tzinfo=None)

    utc = await CurrentTimeTool(now=naive_now).invoke(CurrentTimeArguments(timezone="UTC"))
    assert utc.data["iso8601"] == "2026-08-18T17:30:45+00:00"
    assert utc.data["utc_offset_seconds"] == 0


def test_current_time_arguments_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CurrentTimeArguments.model_validate({"timezone": "UTC", "command": "whoami"})
