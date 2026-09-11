from __future__ import annotations

import asyncio
import hashlib
import platform
import shutil
from pathlib import Path

from typer.testing import CliRunner

from jarvis.cli import app
from jarvis.memory import SQLiteConversationStore, local_memory_host_id
from jarvis.remote import (
    TopologyProfile,
    analyze_database,
    build_remote_manifest,
    create_cutover_receipt,
    load_deployment_manifest,
    load_deployment_state,
)

runner = CliRunner()


def _database(path: Path) -> Path:
    async def initialize() -> None:
        store = SQLiteConversationStore(path)
        await store.initialize()
        await store.close()

    asyncio.run(initialize())
    return path


def test_deployment_help_exposes_bounded_operations() -> None:
    result = runner.invoke(app, ["remote", "deployment", "--help"])
    assert result.exit_code == 0
    for command in ("manifest", "activate", "verify", "stage", "promote", "rollback"):
        assert command in result.stdout


def test_release_cli_stages_promotes_and_rolls_back_exact_artifacts(tmp_path: Path) -> None:
    release_root = tmp_path / "releases"
    release_root.mkdir()
    first = tmp_path / "first.whl"
    second = tmp_path / "second.whl"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    first_sha = hashlib.sha256(b"first").hexdigest()
    second_sha = hashlib.sha256(b"second").hexdigest()
    state = tmp_path / "release-state.json"

    for artifact, digest in ((first, first_sha), (second, second_sha)):
        staged = runner.invoke(
            app,
            [
                "remote",
                "deployment",
                "stage",
                str(artifact),
                "--release-root",
                str(release_root),
                "--sha256",
                digest,
            ],
        )
        assert staged.exit_code == 0
        assert digest in staged.stdout

    initial = runner.invoke(
        app,
        [
            "remote",
            "deployment",
            "promote",
            first_sha,
            "--state",
            str(state),
            "--release-root",
            str(release_root),
        ],
    )
    assert initial.exit_code == 0
    promoted = runner.invoke(
        app,
        [
            "remote",
            "deployment",
            "promote",
            second_sha,
            "--state",
            str(state),
            "--release-root",
            str(release_root),
            "--expected-current-sha256",
            first_sha,
        ],
    )
    assert promoted.exit_code == 0
    rolled_back = runner.invoke(
        app,
        [
            "remote",
            "deployment",
            "rollback",
            second_sha,
            "--state",
            str(state),
            "--release-root",
            str(release_root),
        ],
    )
    assert rolled_back.exit_code == 0
    assert first_sha in rolled_back.stdout


def test_release_cli_refuses_duplicate_stage(tmp_path: Path) -> None:
    release_root = tmp_path / "releases"
    release_root.mkdir()
    artifact = tmp_path / "release.whl"
    artifact.write_bytes(b"release")
    digest = hashlib.sha256(b"release").hexdigest()
    arguments = [
        "remote",
        "deployment",
        "stage",
        str(artifact),
        "--release-root",
        str(release_root),
        "--sha256",
        digest,
    ]
    assert runner.invoke(app, arguments).exit_code == 0
    duplicate = runner.invoke(app, arguments)
    assert duplicate.exit_code == 2
    assert "destination_exists" in duplicate.stdout


def test_deployment_cli_manifest_activate_verify_round_trip(tmp_path: Path) -> None:
    topology = build_remote_manifest(
        profile=TopologyProfile.SPLIT,
        host_id=local_memory_host_id(),
        server_node_id="node:server",
        laptop_node_id="node:laptop",
        server_capabilities=("core.chat", "core.identity", "transport.events"),
        laptop_capabilities=("node.computer", "node.voice", "transport.events"),
        epoch=2,
    )
    topology_path = tmp_path / "topology.json"
    topology_path.write_text(topology.model_dump_json(indent=2), encoding="utf-8")
    source = _database(tmp_path / "source.db")
    target = tmp_path / "target.db"
    shutil.copyfile(source, target)
    receipt_path = tmp_path / "cutover.json"
    create_cutover_receipt(
        source,
        target,
        receipt_path,
        topology=topology,
        source_owner_node_id="node:laptop",
        accepted_state_sha256=analyze_database(source).content_sha256,
    )
    artifact = tmp_path / "jarvis-0.1.0-py3-none-any.whl"
    artifact.write_bytes(b"pinned-release")
    manifest_path = tmp_path / "deployment.json"
    manifest_result = runner.invoke(
        app,
        [
            "remote",
            "deployment",
            "manifest",
            str(manifest_path),
            "--topology",
            str(topology_path),
            "--release",
            str(artifact),
            "--role",
            "server-core",
            "--node-id",
            "node:server",
            "--database",
            str(target),
            "--ownership-receipt",
            str(receipt_path),
            "--python-version",
            platform.python_version(),
        ],
    )
    assert manifest_result.exit_code == 0
    manifest = load_deployment_manifest(manifest_path)
    assert manifest.digest in manifest_result.stdout

    state_path = tmp_path / "state.json"
    activation_result = runner.invoke(
        app,
        [
            "remote",
            "deployment",
            "activate",
            str(state_path),
            "--manifest",
            str(manifest_path),
            "--topology",
            str(topology_path),
            "--release",
            str(artifact),
            "--database",
            str(target),
            "--ownership-receipt",
            str(receipt_path),
        ],
    )
    assert activation_result.exit_code == 0
    state = load_deployment_state(state_path)
    assert state.digest in activation_result.stdout

    verification = runner.invoke(
        app,
        [
            "remote",
            "deployment",
            "verify",
            "--manifest",
            str(manifest_path),
            "--manifest-sha256",
            manifest.digest,
            "--state",
            str(state_path),
            "--state-sha256",
            state.digest,
            "--topology",
            str(topology_path),
            "--release",
            str(artifact),
            "--database",
            str(target),
            "--ownership-receipt",
            str(receipt_path),
        ],
    )
    assert verification.exit_code == 0
    assert '"role": "server-core"' in verification.stdout
