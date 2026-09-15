from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

import jarvis.cli as cli


def test_proactivity_cli_preview_activate_disable_export_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=160))
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    now = datetime.now(UTC)
    scheduled = now + timedelta(days=1)
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(
        json.dumps(
            {
                "title": "Tomorrow briefing",
                "feature": "daily.briefing",
                "schedule": {
                    "kind": "once",
                    "timezone": "UTC",
                    "local_date": scheduled.date().isoformat(),
                    "local_time": scheduled.time().replace(tzinfo=None).isoformat(),
                },
                "provenance": {
                    "source_type": "host",
                    "source_id": "cli:test",
                    "untrusted": True,
                },
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(days=2)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    created = runner.invoke(cli.app, ["proactive", "create", str(proposal_path)])
    assert created.exit_code == 0
    text = output.getvalue()
    rule_id = re.search(r"Rule: (proactivity:[0-9a-f-]+)", text)
    digest = re.search(r"Proposal SHA-256: ([0-9a-f]{64})", text)
    phrase = re.search(r"Activation phrase: (ACTIVATE [0-9a-f]{8})", text)
    assert rule_id and digest and phrase

    output.seek(0)
    output.truncate(0)
    denied = runner.invoke(
        cli.app,
        [
            "proactive",
            "activate",
            rule_id.group(1),
            "--expected-version",
            "1",
            "--expected-digest",
            digest.group(1),
            "--confirm",
            "ACTIVATE wrong",
        ],
    )
    assert denied.exit_code == 2
    assert "confirmation does not match" in output.getvalue()

    output.seek(0)
    output.truncate(0)
    activated = runner.invoke(
        cli.app,
        [
            "proactive",
            "activate",
            rule_id.group(1),
            "--expected-version",
            "1",
            "--expected-digest",
            digest.group(1),
            "--confirm",
            phrase.group(1),
        ],
    )
    assert activated.exit_code == 0
    assert "No runner, task, or notification started" in output.getvalue()

    listed = runner.invoke(cli.app, ["proactive", "list"])
    assert listed.exit_code == 0

    disabled = runner.invoke(
        cli.app,
        ["proactive", "disable", rule_id.group(1), "--expected-version", "2"],
    )
    assert disabled.exit_code == 0

    export_path = tmp_path / "proactivity-export.json"
    exported = runner.invoke(cli.app, ["proactive", "export", str(export_path)])
    assert exported.exit_code == 0
    assert export_path.exists()

    deleted = runner.invoke(
        cli.app,
        [
            "proactive",
            "delete",
            rule_id.group(1),
            "--confirm-rule-id",
            rule_id.group(1),
        ],
    )
    assert deleted.exit_code == 0


def test_proactivity_status_is_default_off_and_has_no_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=160))
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))

    result = CliRunner().invoke(cli.app, ["proactive", "status"])

    assert result.exit_code == 0
    assert "Suggestion-only proactivity: disabled" in output.getvalue()
    assert "No background runner" in output.getvalue()
    assert "Foreground runner: disabled" in output.getvalue()


def test_proactivity_adapter_cli_confirmation_kill_and_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=160))
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    runner = CliRunner()

    denied = runner.invoke(
        cli.app,
        ["proactive", "adapter-enable", "--confirm", "ENABLE WRONG"],
    )
    assert denied.exit_code == 2
    enabled = runner.invoke(
        cli.app,
        [
            "proactive",
            "adapter-enable",
            "--confirm",
            "ENABLE PWA PROACTIVITY",
        ],
    )
    assert enabled.exit_code == 0
    assert "exact device scopes" in output.getvalue()
    status = runner.invoke(cli.app, ["proactive", "ownership"])
    assert status.exit_code == 0
    assert "persistent state: enabled" in output.getvalue()
    disabled = runner.invoke(cli.app, ["proactive", "adapter-disable"])
    assert disabled.exit_code == 0
    assert "ownership reclaimed locally" in output.getvalue()


def test_proactivity_cli_foreground_tick_and_local_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=160))
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JARVIS_PROACTIVITY_ENABLED", "true")
    monkeypatch.setenv("JARVIS_PROACTIVITY_RUNNER_ENABLED", "true")
    monkeypatch.setenv("JARVIS_PROACTIVITY_ENABLED_FEATURES", '["daily.briefing"]')
    now = datetime.now(UTC)
    schedule = (now - timedelta(minutes=1)).time().replace(tzinfo=None, microsecond=0)
    proposal_path = tmp_path / "runner-proposal.json"
    proposal_path.write_text(
        json.dumps(
            {
                "title": "Local reminder",
                "feature": "daily.briefing",
                "schedule": {
                    "kind": "daily",
                    "timezone": "UTC",
                    "local_time": schedule.isoformat(),
                },
                "provenance": {
                    "source_type": "host",
                    "source_id": "cli:runner",
                    "untrusted": True,
                },
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(days=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    assert runner.invoke(cli.app, ["proactive", "create", str(proposal_path)]).exit_code == 0
    text = output.getvalue()
    rule_id = re.search(r"Rule: (proactivity:[0-9a-f-]+)", text)
    digest = re.search(r"Proposal SHA-256: ([0-9a-f]{64})", text)
    phrase = re.search(r"Activation phrase: (ACTIVATE [0-9a-f]{8})", text)
    assert rule_id and digest and phrase
    activated = runner.invoke(
        cli.app,
        [
            "proactive",
            "activate",
            rule_id.group(1),
            "--expected-version",
            "1",
            "--expected-digest",
            digest.group(1),
            "--confirm",
            phrase.group(1),
        ],
    )
    assert activated.exit_code == 0
    tick = runner.invoke(cli.app, ["proactive", "tick"])
    assert tick.exit_code == 0
    assert "notifications=1" in output.getvalue()
    inbox = runner.invoke(cli.app, ["proactive", "inbox", "--active-only"])
    assert inbox.exit_code == 0
    rendered = output.getvalue()
    assert "daily.briefing" in rendered
    candidate = re.search(r"suggestion:[0-9a-f-]+", rendered)
    assert candidate

    events = runner.invoke(cli.app, ["proactive", "runner-events", candidate.group(0)])
    assert events.exit_code == 0
    assert "notification_ready" in output.getvalue()
    snoozed = runner.invoke(
        cli.app,
        [
            "proactive",
            "snooze",
            candidate.group(0),
            "--expected-version",
            "2",
            "--minutes",
            "1",
        ],
    )
    assert snoozed.exit_code == 0
    dismissed = runner.invoke(
        cli.app,
        [
            "proactive",
            "dismiss",
            candidate.group(0),
            "--expected-version",
            "3",
        ],
    )
    assert dismissed.exit_code == 0

    incomplete_event = runner.invoke(cli.app, ["proactive", "tick", "--event-name", "task.changed"])
    assert incomplete_event.exit_code == 2
    denied_cancel = runner.invoke(
        cli.app,
        [
            "proactive",
            "cancel",
            candidate.group(0),
            "--expected-version",
            "4",
        ],
    )
    assert denied_cancel.exit_code == 1
