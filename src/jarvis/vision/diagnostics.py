"""Non-capturing Phase 7A dependency and privacy diagnostics."""

from __future__ import annotations

import os
from importlib.util import find_spec

from jarvis.config import Settings
from jarvis.diagnostics import DiagnosticCheck, DiagnosticReport, DiagnosticStatus

from .settings_store import VisionSettingsError, VisionSettingsFile


def run_vision_diagnostics(
    settings: Settings,
    *,
    settings_store: VisionSettingsFile | None = None,
) -> DiagnosticReport:
    """Validate configuration and imports without opening camera or reading screen pixels."""
    store = settings_store or VisionSettingsFile(settings.vision_settings_path)
    checks: list[DiagnosticCheck] = [
        DiagnosticCheck(
            name="vision capture topology",
            status=(DiagnosticStatus.PASS if os.name == "nt" else DiagnosticStatus.FAIL),
            detail=(
                "Native capture runs in a killable local Windows subprocess."
                if os.name == "nt"
                else "The Phase 7A native adapter requires Windows."
            ),
            remediation=None if os.name == "nt" else "Run vision capture on Windows 10 or 11.",
        ),
        DiagnosticCheck(
            name="vision privacy policy",
            status=DiagnosticStatus.PASS,
            detail=(
                "Only explicit foreground, RGB24, bounded, local, ephemeral capture is modeled; "
                "cloud disclosure, biometrics, retention, recognition, and actions are absent."
            ),
        ),
    ]
    for module_name, display_name in (("cv2", "OpenCV camera"), ("PIL.ImageGrab", "Pillow screen")):
        available = _module_available(module_name)
        checks.append(
            DiagnosticCheck(
                name=f"{display_name} adapter",
                status=DiagnosticStatus.PASS if available else DiagnosticStatus.FAIL,
                detail=(
                    f"{display_name} dependency is importable."
                    if available
                    else f"{display_name} dependency is not installed."
                ),
                remediation=(
                    None
                    if available
                    else "Install with `uv sync --locked --extra vision`; this does not capture."
                ),
            )
        )
    try:
        control = store.load_control()
    except VisionSettingsError:
        checks.append(
            DiagnosticCheck(
                name="vision software kill switch",
                status=DiagnosticStatus.FAIL,
                detail="Vision control settings are unreadable; capture will fail closed.",
                remediation=f"Move aside or repair: {settings.vision_settings_path}",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name="vision software kill switch",
                status=DiagnosticStatus.PASS,
                detail=(
                    "User control is enabled; no capture starts without an explicit command."
                    if control.enabled
                    else "User control is disabled; camera/screen capture is blocked."
                ),
            )
        )
    checks.append(
        DiagnosticCheck(
            name="vision host gate",
            status=DiagnosticStatus.PASS,
            detail=(
                "Host capture gate is enabled; persistent control and explicit command "
                "remain required."
                if settings.vision_capture_enabled
                else "Host capture gate is disabled; no native source can open."
            ),
        )
    )
    return DiagnosticReport(checks=tuple(checks))


def _module_available(module_name: str) -> bool:
    try:
        return find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False
