import asyncio
import json
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from jarvis import cli
from jarvis.config import Settings
from jarvis.memory import SQLiteConversationStore

KEY = bytes(range(32))


def _database(path: Path) -> Path:
    async def initialize() -> None:
        store = SQLiteConversationStore(path)
        await store.initialize()
        await store.close()

    asyncio.run(initialize())
    return path


def _capture(monkeypatch: pytest.MonkeyPatch) -> StringIO:
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=60))
    return output


def test_migration_cli_backup_restore_shadow_and_fail_closed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = _capture(monkeypatch)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings = Settings(data_dir=data_dir, _env_file=None)
    _database(settings.database_path)
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)
    manifest = tmp_path / "split.json"
    key_file = tmp_path / "migration.key"
    key_file.write_bytes(KEY)
    bundle = tmp_path / "migration.j9b"
    target = tmp_path / "restored.db"
    runner = CliRunner()

    planned = runner.invoke(
        cli.app,
        [
            "remote",
            "migration",
            "manifest",
            str(manifest),
            "--server-node-id",
            "node:server",
            "--laptop-node-id",
            "node:laptop",
        ],
    )
    assert planned.exit_code == 0
    assert '"activates_runtime": false' in output.getvalue()
    output.seek(0)
    output.truncate(0)

    backup = runner.invoke(
        cli.app,
        [
            "remote",
            "migration",
            "backup",
            str(bundle),
            "--manifest",
            str(manifest),
            "--key-file",
            str(key_file),
            "--key-id",
            "cli-key",
            "--source-owner-node-id",
            "node:laptop",
        ],
    )
    backup_output = json.loads(output.getvalue())
    output.seek(0)
    output.truncate(0)
    restore = runner.invoke(
        cli.app,
        [
            "remote",
            "migration",
            "restore",
            str(bundle),
            str(target),
            "--manifest",
            str(manifest),
            "--key-file",
            str(key_file),
            "--key-id",
            "cli-key",
        ],
    )
    output.seek(0)
    output.truncate(0)
    shadow = runner.invoke(
        cli.app,
        ["remote", "migration", "shadow", str(settings.database_path), str(target)],
    )

    assert backup.exit_code == 0
    assert restore.exit_code == 0
    assert shadow.exit_code == 0
    assert backup_output["contains_private_data"] is True
    assert '"matched": true' in output.getvalue()

    output.seek(0)
    output.truncate(0)
    duplicate = runner.invoke(
        cli.app,
        [
            "remote",
            "migration",
            "restore",
            str(bundle),
            str(target),
            "--manifest",
            str(manifest),
            "--key-file",
            str(key_file),
            "--key-id",
            "cli-key",
        ],
    )
    assert duplicate.exit_code == 2
    assert "destination_exists" in output.getvalue()

    output.seek(0)
    output.truncate(0)
    local_manifest = runner.invoke(
        cli.app,
        [
            "remote",
            "migration",
            "manifest",
            str(tmp_path / "local.json"),
            "--profile",
            "local-only",
            "--epoch",
            "3",
            "--laptop-node-id",
            "node:laptop",
        ],
    )
    assert local_manifest.exit_code == 0
    assert '"profile": "local-only"' in output.getvalue()
