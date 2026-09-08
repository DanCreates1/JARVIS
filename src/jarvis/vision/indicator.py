"""Foreground visible capture indicator adapters."""

from __future__ import annotations

import sys
from collections.abc import Callable

from .models import IndicatorState


class TerminalCaptureIndicator:
    """Keep a foreground terminal indicator active for the exact source lifetime."""

    def __init__(self, writer: Callable[[str], None] | None = None) -> None:
        self._writer = writer or (lambda value: print(value, file=sys.stderr, flush=True))
        self._session_id: str | None = None

    async def show(self, state: IndicatorState) -> None:
        if self._session_id is not None:
            raise RuntimeError("capture indicator is already active")
        self._writer(
            "[JARVIS CAPTURE ACTIVE] "
            f"source={state.source.value} purpose={state.purpose.value} "
            f"region={state.region.x},{state.region.y},"
            f"{state.region.width}x{state.region.height}"
        )
        self._session_id = state.session_id

    async def clear(self, session_id: str) -> None:
        if self._session_id != session_id:
            raise RuntimeError("capture indicator session mismatch")
        self._writer("[JARVIS CAPTURE OFF]")
        self._session_id = None
