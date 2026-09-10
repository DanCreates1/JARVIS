from __future__ import annotations

from typer.testing import CliRunner

from jarvis.cli import app

runner = CliRunner()


def test_vision_enable_status_disable_never_start_capture(tmp_path) -> None:  # type: ignore[no-untyped-def]
    environment = {
        "JARVIS_DATA_DIR": str(tmp_path),
        "JARVIS_VISION_CAPTURE_ENABLED": "false",
    }

    enabled = runner.invoke(app, ["vision", "enable"], env=environment)
    status = runner.invoke(app, ["vision", "status"], env=environment)
    disabled = runner.invoke(app, ["vision", "disable"], env=environment)

    assert enabled.exit_code == 0
    assert "host gate remains disabled" in enabled.stdout
    assert status.exit_code == 0
    assert "inactive" in status.stdout
    assert disabled.exit_code == 0
    assert "kill switch enabled" in disabled.stdout


def test_vision_capture_fails_before_source_open_when_host_gate_off(tmp_path) -> None:  # type: ignore[no-untyped-def]
    environment = {
        "JARVIS_DATA_DIR": str(tmp_path),
        "JARVIS_VISION_CAPTURE_ENABLED": "false",
    }
    assert runner.invoke(app, ["vision", "enable"], env=environment).exit_code == 0

    result = runner.invoke(
        app,
        [
            "vision",
            "capture",
            "--source",
            "camera",
            "--width",
            "2",
            "--height",
            "2",
        ],
        env=environment,
    )

    assert result.exit_code == 1
    assert "host vision capture configuration is disabled" in result.stdout


def test_vision_capture_rejects_unbounded_or_unknown_envelope(tmp_path) -> None:  # type: ignore[no-untyped-def]
    environment = {"JARVIS_DATA_DIR": str(tmp_path)}

    unknown = runner.invoke(
        app,
        ["vision", "capture", "--source", "unknown"],
        env=environment,
    )
    oversized = runner.invoke(
        app,
        ["vision", "capture", "--source", "screen", "--width", "1921"],
        env=environment,
    )

    assert unknown.exit_code == 2
    assert oversized.exit_code == 2
    assert "Invalid capture envelope" in unknown.stdout
    assert "Invalid capture envelope" in oversized.stdout


def test_vision_setup_installs_models_only_on_explicit_command(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    installed: list[object] = []

    def install(path):  # type: ignore[no-untyped-def]
        installed.append(path)
        return path / "palm.onnx", path / "hand.onnx"

    monkeypatch.setattr("jarvis.gestures.model_store.install_vision_models", install)
    result = runner.invoke(
        app,
        ["vision", "setup"],
        env={"JARVIS_DATA_DIR": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert installed == [tmp_path / "models" / "vision"]
    assert "verified=2" in result.stdout


def test_vision_gestures_rejects_unbounded_envelope_before_model_or_camera(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(
        app,
        ["vision", "gestures", "--duration-ms", "30001"],
        env={"JARVIS_DATA_DIR": str(tmp_path)},
    )

    assert result.exit_code == 2
    assert "Invalid gesture envelope" in result.stdout
