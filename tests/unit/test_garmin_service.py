"""Core rejects raw or malformed output from the isolated Garmin bridge."""

from pathlib import Path
from sys import executable

import pytest

from jarvis.garmin.service import GarminSummaryService, GarminUnavailableError


@pytest.mark.asyncio
async def test_garmin_service_rejects_unexpected_private_fields(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.py"
    bridge.write_text(
        "import json\n"
        "print(json.dumps({'date': '2026-09-30', "
        "'refreshed_at': '2026-09-30T12:00:00Z', "
        "'activities': [], 'token': 'must-not-leak'}))\n",
        encoding="utf-8",
    )
    reader = GarminSummaryService(python_path=Path(executable), bridge_path=bridge)
    with pytest.raises(GarminUnavailableError, match="refresh_failed"):
        await reader.summary()
