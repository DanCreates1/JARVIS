from __future__ import annotations

from jarvis.config import Settings
from jarvis.diagnostics import DiagnosticStatus
from jarvis.vision.diagnostics import run_vision_diagnostics
from jarvis.vision.fakes import FakeCaptureSettings


def test_vision_diagnostics_do_not_capture_and_report_dual_gates(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("jarvis.vision.diagnostics.find_spec", lambda _name: object())
    monkeypatch.setattr("jarvis.vision.diagnostics.verify_model", lambda *_args: True)
    settings = Settings(data_dir=tmp_path, vision_capture_enabled=False)

    report = run_vision_diagnostics(
        settings,
        settings_store=FakeCaptureSettings(enabled=False),  # type: ignore[arg-type]
    )

    assert report.ok
    details = {check.name: check.detail for check in report.checks}
    assert "disabled" in details["vision software kill switch"]
    assert "disabled" in details["vision host gate"]
    assert all(check.status is DiagnosticStatus.PASS for check in report.checks)


def test_vision_diagnostics_missing_dependencies_fail_without_opening(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("jarvis.vision.diagnostics.find_spec", lambda _name: None)

    report = run_vision_diagnostics(
        Settings(data_dir=tmp_path),
        settings_store=FakeCaptureSettings(),  # type: ignore[arg-type]
    )

    assert not report.ok
    failures = [check for check in report.checks if check.status is DiagnosticStatus.FAIL]
    assert {check.name for check in failures} == {
        "OpenCV camera adapter",
        "OpenCV Zoo MP hand-pose estimator",
        "OpenCV Zoo MP palm detector",
        "Pillow screen adapter",
    }


def test_vision_diagnostics_invalid_store_fails_closed(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("jarvis.vision.diagnostics.find_spec", lambda _name: object())
    monkeypatch.setattr("jarvis.vision.diagnostics.verify_model", lambda *_args: True)

    class BrokenStore:
        def load_control(self):  # type: ignore[no-untyped-def]
            from jarvis.vision.settings_store import VisionSettingsError

            raise VisionSettingsError("broken")

    report = run_vision_diagnostics(
        Settings(data_dir=tmp_path),
        settings_store=BrokenStore(),  # type: ignore[arg-type]
    )
    assert not report.ok
    assert any(check.name == "vision software kill switch" for check in report.checks)


def test_vision_diagnostics_handles_missing_parent_package(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def missing_parent(name: str) -> object:
        if name == "PIL.ImageGrab":
            raise ModuleNotFoundError("PIL")
        return object()

    monkeypatch.setattr("jarvis.vision.diagnostics.find_spec", missing_parent)
    monkeypatch.setattr("jarvis.vision.diagnostics.verify_model", lambda *_args: True)

    report = run_vision_diagnostics(
        Settings(data_dir=tmp_path),
        settings_store=FakeCaptureSettings(),  # type: ignore[arg-type]
    )

    assert not report.ok
    pillow = next(check for check in report.checks if check.name == "Pillow screen adapter")
    assert pillow.status is DiagnosticStatus.FAIL
