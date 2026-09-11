import asyncio
import json
import os
import sqlite3
from pathlib import Path

import pytest

import jarvis.remote.migration as migration
from jarvis.memory import SQLiteConversationStore
from jarvis.remote import (
    MigrationError,
    MigrationErrorCode,
    TopologyProfile,
    analyze_database,
    build_local_only_manifest,
    build_remote_manifest,
    create_cutover_receipt,
    create_encrypted_backup,
    create_rollback_receipt,
    restore_encrypted_backup,
)

KEY = b"K" * 32
PRIVATE_MARKER = "PHASE9B-PRIVATE-CONTENT-MUST-BE-ENCRYPTED"


def _database(path: Path) -> Path:
    async def initialize() -> None:
        store = SQLiteConversationStore(path)
        await store.initialize()
        await store.close()

    asyncio.run(initialize())
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO conversations (id, metadata_json, created_at, updated_at)
            VALUES ('private', ?, '2026-09-11T00:00:00Z', '2026-09-11T00:00:00Z')
            """,
            (json.dumps({"private": PRIVATE_MARKER}),),
        )
        connection.commit()
    return path


def _remote(epoch: int = 10):  # type: ignore[no-untyped-def]
    return build_remote_manifest(
        profile=TopologyProfile.SERVER_PRIMARY,
        host_id="host:security",
        server_node_id="node:server",
        laptop_node_id="node:laptop",
        server_capabilities=("core.chat", "core.identity"),
        laptop_capabilities=("node.voice",),
        epoch=epoch,
    )


def test_bundle_hides_private_state_and_rejects_ciphertext_manifest_or_tag_tamper(
    tmp_path: Path,
) -> None:
    source = _database(tmp_path / "source.db")
    bundle = tmp_path / "backup.j9b"
    topology = _remote()
    create_encrypted_backup(
        source,
        bundle,
        topology=topology,
        source_owner_node_id="node:laptop",
        key=KEY,
        key_id="security-key",
    )
    encrypted = bundle.read_bytes()

    assert PRIVATE_MARKER.encode() not in encrypted
    assert KEY not in encrypted
    for index in (len(encrypted) // 2, len(encrypted) - 1):
        tampered = tmp_path / f"tampered-{index}.j9b"
        payload = bytearray(encrypted)
        payload[index] ^= 0x80
        tampered.write_bytes(payload)
        target = tmp_path / f"target-{index}.db"
        with pytest.raises(MigrationError) as error:
            restore_encrypted_backup(
                tampered,
                target,
                topology=topology,
                key=KEY,
                expected_key_id="security-key",
            )
        assert error.value.code is MigrationErrorCode.AUTHENTICATION_FAILED
        assert not target.exists()


def test_interrupted_backup_leaves_no_partial_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _database(tmp_path / "source.db")
    destination = tmp_path / "interrupted.j9b"

    def fail(*_args: object, **_kwargs: object) -> tuple[int, str]:
        destination.write_bytes(b"partial")
        raise OSError("simulated disk failure")

    monkeypatch.setattr(migration, "_encrypt_snapshot", fail)
    with pytest.raises(MigrationError) as error:
        create_encrypted_backup(
            source,
            destination,
            topology=_remote(),
            source_owner_node_id="node:laptop",
            key=KEY,
            key_id="security-key",
        )

    assert error.value.code is MigrationErrorCode.IO_FAILED
    assert not destination.exists()
    assert not tuple(tmp_path.glob(".jarvis-phase9b-*"))


def test_tampered_or_stale_receipt_cannot_authorize_rollback(tmp_path: Path) -> None:
    source = _database(tmp_path / "source.db")
    bundle = tmp_path / "backup.j9b"
    target = tmp_path / "target.db"
    topology = _remote()
    backup = create_encrypted_backup(
        source,
        bundle,
        topology=topology,
        source_owner_node_id="node:laptop",
        key=KEY,
        key_id="security-key",
    )
    restore_encrypted_backup(
        bundle,
        target,
        topology=topology,
        key=KEY,
        expected_key_id="security-key",
    )
    cutover_path = tmp_path / "cutover.json"
    create_cutover_receipt(
        source,
        target,
        cutover_path,
        topology=topology,
        source_owner_node_id="node:laptop",
        accepted_state_sha256=backup.accepted_state_sha256,
    )
    payload = json.loads(cutover_path.read_text(encoding="utf-8"))
    payload["active_owner_node_id"] = "node:attacker"
    cutover_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MigrationError) as tampered:
        create_rollback_receipt(
            target,
            source,
            tmp_path / "rollback.json",
            topology=build_local_only_manifest(
                host_id="host:security",
                node_id="node:laptop",
                capabilities=("core.chat",),
                epoch=11,
            ),
            previous_receipt=cutover_path,
            accepted_state_sha256=backup.accepted_state_sha256,
        )
    assert tampered.value.code is MigrationErrorCode.RECEIPT_INVALID


def test_database_mutation_after_shadow_proof_never_creates_cutover_receipt(tmp_path: Path) -> None:
    source = _database(tmp_path / "source.db")
    target = tmp_path / "target.db"
    with sqlite3.connect(source) as source_connection, sqlite3.connect(target) as target_connection:
        source_connection.backup(target_connection)
    accepted = analyze_database(source).content_sha256
    with sqlite3.connect(source) as connection:
        connection.execute(
            """
            INSERT INTO conversations (id, metadata_json, created_at, updated_at)
            VALUES ('stale-writer', '{}', '2026-09-11T00:00:00Z', '2026-09-11T00:00:00Z')
            """
        )
        connection.commit()

    receipt = tmp_path / "must-not-exist.json"
    with pytest.raises(MigrationError) as error:
        create_cutover_receipt(
            source,
            target,
            receipt,
            topology=_remote(),
            source_owner_node_id="node:laptop",
            accepted_state_sha256=accepted,
        )
    assert error.value.code is MigrationErrorCode.SOURCE_DRIFT
    assert not receipt.exists()


def test_key_file_symlink_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = tmp_path / "real.key"
    key.write_bytes(os.urandom(32))
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == key or original(path))

    with pytest.raises(MigrationError) as error:
        migration.read_migration_key(key)
    assert error.value.code is MigrationErrorCode.INVALID_INPUT
