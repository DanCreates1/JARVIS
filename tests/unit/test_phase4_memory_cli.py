from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from jarvis import cli
from jarvis.config import Settings
from jarvis.memory import (
    MemoryCategory,
    MemoryState,
    ProvenanceSource,
    SQLiteMemoryStore,
    untrusted_provenance,
)

HOST = "host-cli-test"


async def _items(settings: Settings):  # type: ignore[no-untyped-def]
    async with SQLiteMemoryStore(settings.database_path) as store:
        return await store.list(host_id=HOST, limit=100)


async def _candidate(settings: Settings, *, key: str, content: str):  # type: ignore[no-untyped-def]
    async with SQLiteMemoryStore(settings.database_path) as store:
        return await store.propose(
            host_id=HOST,
            category=MemoryCategory.PROFILE,
            key=key,
            content=content,
            confidence=0.9,
            provenance=untrusted_provenance(
                source_type=ProvenanceSource.MESSAGE,
                source_id=f"message-{key}",
                source_label="synthetic CLI candidate",
                conversation_id="conversation-cli",
                message_id=f"message-{key}",
                source_content=content,
            ),
        )


def test_memory_cli_complete_inspection_and_control_workflow(
    monkeypatch,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path / "data", _env_file=None)
    output = StringIO()
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)
    monkeypatch.setattr(cli, "local_memory_host_id", lambda: HOST)
    monkeypatch.setattr(
        cli,
        "console",
        Console(file=output, force_terminal=False, color_system=None, width=240),
    )
    runner = CliRunner()

    remembered = runner.invoke(
        cli.app,
        [
            "memory",
            "remember",
            "profile",
            "Prefers concise synthetic CLI reports",
            "--key",
            "preference.cli",
        ],
    )
    assert remembered.exit_code == 0
    first = next(item for item in asyncio.run(_items(settings)) if item.key == "preference.cli")

    assert runner.invoke(cli.app, ["memory", "list"]).exit_code == 0
    assert runner.invoke(cli.app, ["memory", "list", "--state", "deleted"]).exit_code == 0
    assert runner.invoke(cli.app, ["memory", "search", "concise CLI reports"]).exit_code == 0
    assert runner.invoke(cli.app, ["memory", "retention"]).exit_code == 0
    assert runner.invoke(cli.app, ["memory", "set-retention", "profile", "30"]).exit_code == 0
    assert runner.invoke(cli.app, ["memory", "expire"]).exit_code == 0
    first = next(item for item in asyncio.run(_items(settings)) if item.id == first.id)

    corrected = runner.invoke(
        cli.app,
        [
            "memory",
            "correct",
            first.id,
            "--expected-version",
            str(first.version),
            "--content",
            "Prefers detailed synthetic CLI reports",
        ],
    )
    assert corrected.exit_code == 0
    active = next(
        item
        for item in asyncio.run(_items(settings))
        if item.key == "preference.cli" and item.state is MemoryState.COMMITTED
    )

    conflict_create = runner.invoke(
        cli.app,
        [
            "memory",
            "remember",
            "profile",
            "Prefers tabular synthetic CLI reports",
            "--key",
            "preference.cli",
        ],
    )
    assert conflict_create.exit_code == 0
    assert runner.invoke(cli.app, ["memory", "conflicts"]).exit_code == 0
    conflict_item = next(
        item for item in asyncio.run(_items(settings)) if item.content.startswith("Prefers tabular")
    )
    conflict_id = conflict_item.conflict_ids[0]
    resolved = runner.invoke(
        cli.app,
        ["memory", "resolve-conflict", conflict_id, conflict_item.id],
    )
    assert resolved.exit_code == 0

    candidate = asyncio.run(
        _candidate(settings, key="profile.candidate", content="Synthetic promoted candidate")
    )
    promoted = runner.invoke(
        cli.app,
        [
            "memory",
            "promote",
            candidate.id,
            "--expected-version",
            str(candidate.version),
            "--expected-digest",
            candidate.content_sha256,
        ],
    )
    assert promoted.exit_code == 0
    replay = runner.invoke(
        cli.app,
        [
            "memory",
            "promote",
            candidate.id,
            "--expected-version",
            str(candidate.version),
            "--expected-digest",
            candidate.content_sha256,
        ],
    )
    assert replay.exit_code == 1

    rejected_candidate = asyncio.run(
        _candidate(settings, key="profile.reject", content="Synthetic rejected candidate")
    )
    rejected = runner.invoke(
        cli.app,
        [
            "memory",
            "reject",
            rejected_candidate.id,
            "--expected-version",
            str(rejected_candidate.version),
        ],
    )
    assert rejected.exit_code == 0

    export_path = tmp_path / "export.json"
    exported = runner.invoke(cli.app, ["memory", "export", str(export_path)])
    assert exported.exit_code == 0 and export_path.exists()
    assert runner.invoke(cli.app, ["memory", "export", str(export_path)]).exit_code == 1

    forgotten = runner.invoke(cli.app, ["memory", "forget", active.id])
    assert forgotten.exit_code == 0
    assert runner.invoke(cli.app, ["memory", "forget", active.id]).exit_code == 1
    assert (
        runner.invoke(
            cli.app,
            [
                "memory",
                "correct",
                "missing",
                "--expected-version",
                "1",
                "--content",
                "invalid",
            ],
        ).exit_code
        == 1
    )

    rendered = output.getvalue()
    assert "Committed" in rendered
    assert "sha256=" in rendered
    assert "Why retrieved" in rendered
    assert "Conflict resolved" in rendered
    assert "Deleted transitively" in rendered


def test_memory_cli_helper_failure_paths(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(data_dir=tmp_path / "failure-data", _env_file=None)
    output = StringIO()
    monkeypatch.setattr(cli, "local_memory_host_id", lambda: HOST)
    monkeypatch.setattr(
        cli,
        "console",
        Console(file=output, force_terminal=False, color_system=None),
    )

    assert (
        asyncio.run(
            cli._memory_promote(
                settings,
                candidate_id="missing",
                expected_version=1,
                expected_digest="0" * 64,
            )
        )
        == 1
    )
    assert (
        asyncio.run(cli._memory_reject(settings, candidate_id="missing", expected_version=1)) == 1
    )
    assert (
        asyncio.run(
            cli._memory_resolve_conflict(
                settings,
                conflict_id="missing",
                winner_memory_id="missing",
            )
        )
        == 1
    )
    assert (
        asyncio.run(
            cli._memory_set_retention(
                settings,
                category=MemoryCategory.WORKING,
                days=1,
            )
        )
        == 0
    )
    assert datetime.now(UTC).tzinfo is UTC
