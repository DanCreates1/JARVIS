from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jarvis.cli import app
from jarvis.proactivity.worker_models import WorkerPlan


@pytest.fixture
def operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JARVIS_PROACTIVITY_ENABLED", "true")
    monkeypatch.setenv("JARVIS_PROACTIVITY_RUNNER_ENABLED", "true")
    monkeypatch.setenv("JARVIS_PROACTIVITY_ENABLED_FEATURES", '["task.checkin"]')
    return CliRunner(), tmp_path / "review.json"


def test_cli_exact_review_enable_replay_stop_and_status(operator):
    runner, path = operator
    result = runner.invoke(
        app,
        [
            "proactive",
            "background",
            "preview",
            str(path),
            "--feature",
            "task.checkin",
            "--max-ticks",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "No worker started" in result.output
    plan = WorkerPlan.model_validate_json(path.read_bytes())
    assert (
        runner.invoke(
            app,
            [
                "proactive",
                "background",
                "enable",
                str(path),
                "--expected-digest",
                plan.sha256,
                "--confirm",
                "ENABLE BACKGROUND wrong",
            ],
        ).exit_code
        == 1
    )
    args = [
        "proactive",
        "background",
        "enable",
        str(path),
        "--expected-digest",
        plan.sha256,
        "--confirm",
        f"ENABLE BACKGROUND {plan.sha256[:8]}",
    ]
    collision = plan.sha256[:-1] + ("0" if plan.sha256[-1] != "0" else "1")
    assert collision[:8] == plan.sha256[:8]
    wrong_digest = [collision if value == plan.sha256 else value for value in args]
    assert runner.invoke(app, wrong_digest).exit_code == 1
    assert runner.invoke(app, args).exit_code == 0
    assert runner.invoke(app, args).exit_code == 1
    status = runner.invoke(app, ["proactive", "background", "status"])
    assert json.loads(status.output)["enabled"] is True
    result = runner.invoke(app, ["proactive", "background", "run"])
    assert result.exit_code == 0, result.output
    assert "ticks=1" in result.output and "external_sends=0" in result.output
    assert runner.invoke(app, ["proactive", "background", "stop"]).exit_code == 0
    assert runner.invoke(app, args).exit_code == 1
    assert runner.invoke(app, ["proactive", "background", "run"]).exit_code == 1
    status = runner.invoke(app, ["proactive", "background", "status"])
    assert json.loads(status.output)["enabled"] is False


@pytest.mark.parametrize(
    "kind", ["disabled", "runner", "feature", "overwrite", "oversize", "private"]
)
def test_cli_denials_are_content_free(operator, monkeypatch, kind):
    runner, path = operator
    args = ["proactive", "background", "preview", str(path), "--feature", "task.checkin"]
    if kind == "disabled":
        monkeypatch.setenv("JARVIS_PROACTIVITY_ENABLED", "false")
    elif kind == "runner":
        monkeypatch.setenv("JARVIS_PROACTIVITY_RUNNER_ENABLED", "false")
    elif kind == "feature":
        args[-1] = "calendar.unapproved"
    elif kind == "overwrite":
        path.write_text("PRIVATE-CONTENT-CANARY")
    else:
        path.write_text("PRIVATE-CONTENT-CANARY" * (1_000 if kind == "oversize" else 1))
        args = [
            "proactive",
            "background",
            "enable",
            str(path),
            "--expected-digest",
            "0" * 64,
            "--confirm",
            "forged",
        ]
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert "failed closed" in result.output
    assert "PRIVATE-CONTENT-CANARY" not in result.output
