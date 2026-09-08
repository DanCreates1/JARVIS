"""Composition helpers for the explicit foreground Phase 7A capture slice."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.config import Settings

from .adapters import IsolatedWindowsFrameSource
from .contracts import CaptureIndicator
from .indicator import TerminalCaptureIndicator
from .session import CaptureController
from .settings_store import VisionSettingsFile


@dataclass(slots=True)
class VisionCaptureComponents:
    settings_store: VisionSettingsFile
    source: IsolatedWindowsFrameSource
    controller: CaptureController

    async def close(self) -> None:
        self.controller.kill()
        await self.source.close()


def build_vision_capture(
    settings: Settings,
    *,
    indicator: CaptureIndicator | None = None,
) -> VisionCaptureComponents:
    settings_store = VisionSettingsFile(settings.vision_settings_path)
    source = IsolatedWindowsFrameSource()
    controller = CaptureController(
        source=source,
        indicator=indicator or TerminalCaptureIndicator(),
        settings_store=settings_store,
        host_enabled=settings.vision_capture_enabled,
    )
    return VisionCaptureComponents(
        settings_store=settings_store,
        source=source,
        controller=controller,
    )
