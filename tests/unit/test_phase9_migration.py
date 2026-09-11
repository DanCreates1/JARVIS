import asyncio
import base64
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jarvis.memory import SQLiteConversationStore
from jarvis.remote import (
    MigrationError,
    MigrationErrorCode,
    OwnershipTransition,
    TopologyProfile,
    analyze_database,
    build_local_only_manifest,
    build_remote_manifest,
    compare_shadow,
    create_cutover_receipt,
    create_encrypted_backup,
    create_rollback_receipt,
    iter_shared_domains,
    load_transition_receipt,
    read_migration_key,
    restore_encrypted_backup,
)

HOST_ID = "host:migration-test"
LAPTOP_ID = "node:laptop"
SERVER_ID = "node:server"
KEY_ID = "phase9b-test-key"
KEY = bytes(range(32))
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def _remote_topology(epoch: int = 7):  # type: ignore[no-untyped-def]
    return build_remote_manifest(
        profile=TopologyProfile.SPLIT,
        host_id=HOST_ID,
        server_node_id=SERVER_ID,
        laptop_node_id=LAPTOP_ID,
        server_capabilities=(
            "core.chat",
            "core.identity",
            "core.memory",
            "core.permissions",
            "core.research",
            "core.tasks",
            "transport.events",
        ),
        laptop_capabilities=("node.computer", "node.vision", "node.voice"),
        laptop_offline_capabilities=("node.voice",),
        epoch=epoch,
    )


def _local_topology(epoch: int = 8):  # type: ignore[no-untyped-def]
    return build_local_only_manifest(
        host_id=HOST_ID,
        node_id=LAPTOP_ID,
        capabilities=("core.chat", "node.voice"),
        epoch=epoch,
    )


def _database(path: Path, *, rows: int = 3) -> Path:
    async def initialize() -> None:
        store = SQLiteConversationStore(path)
        await store.initialize()
        await store.close()

    asyncio.run(initialize())
    with sqlite3.connect(path) as connection:
        for index in range(rows):
            connection.execute(
                """
                INSERT INTO conversations (id, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    f"conversation-{index}",
                    json.dumps({"index": index}),
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
            )
        connection.commit()
    return path


def _backup_and_restore(tmp_path: Path):  # type: ignore[no-untyped-def]
    source = _database(tmp_path / "source.db")
    bundle = tmp_path / "migration.j9b"
    target = tmp_path / "target.db"
    topology = _remote_topology()
    backup = create_encrypted_backup(
        source,
        bundle,
        topology=topology,
        source_owner_node_id=LAPTOP_ID,
        key=KEY,
        key_id=KEY_ID,
        now=NOW,
    )
    restore = restore_encrypted_backup(
        bundle,
        target,
        topology=topology,
        key=KEY,
        expected_key_id=KEY_ID,
    )
    return source, bundle, target, topology, backup, restore


def test_database_state_covers_all_packaged_migrations_and_shared_domains(tmp_path: Path) -> None:
    state = analyze_database(_database(tmp_path / "source.db"))

    assert [item.version for item in state.migrations] == list(range(1, 11))
    assert state.tables
    assert len(state.content_sha256) == 64
    assert {domain.value for domain in iter_shared_domains()} == {
        "identity",
        "sessions-replay",
        "conversations",
        "memory",
        "research",
        "tasks",
        "permission-authority",
        "audit",
    }


def test_encrypted_backup_restore_and_layout_independent_shadow(tmp_path: Path) -> None:
    source, bundle, target, topology, backup, restore = _backup_and_restore(tmp_path)

    assert backup.encrypted_bytes == bundle.stat().st_size
    assert backup.accepted_state_sha256 == restore.accepted_state_sha256
    assert backup.topology_digest == topology.digest
    assert KEY not in bundle.read_bytes()
    original_target_digest = restore.database_sha256

    with sqlite3.connect(target) as connection:
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    comparison = compare_shadow(source, target)

    assert comparison.matched is True
    assert comparison.accepted_state_sha256 == backup.accepted_state_sha256
    assert comparison.target_database_sha256 != original_target_digest


@pytest.mark.parametrize("damage", ["wrong-key", "ciphertext", "truncated"])
def test_restore_rejects_unauthenticated_or_incomplete_bundle(tmp_path: Path, damage: str) -> None:
    source = _database(tmp_path / "source.db")
    bundle = tmp_path / "migration.j9b"
    topology = _remote_topology()
    create_encrypted_backup(
        source,
        bundle,
        topology=topology,
        source_owner_node_id=LAPTOP_ID,
        key=KEY,
        key_id=KEY_ID,
    )
    key = KEY
    if damage == "wrong-key":
        key = os.urandom(32)
    else:
        payload = bytearray(bundle.read_bytes())
        if damage == "ciphertext":
            payload[len(payload) // 2] ^= 0x01
        else:
            del payload[-8:]
        bundle.write_bytes(payload)

    target = tmp_path / "rejected.db"
    with pytest.raises(MigrationError) as error:
        restore_encrypted_backup(
            bundle,
            target,
            topology=topology,
            key=key,
            expected_key_id=KEY_ID,
        )

    assert error.value.code in {
        MigrationErrorCode.AUTHENTICATION_FAILED,
        MigrationErrorCode.BUNDLE_INVALID,
    }
    assert not target.exists()


def test_restore_rejects_key_id_topology_and_existing_destination(tmp_path: Path) -> None:
    source = _database(tmp_path / "source.db")
    bundle = tmp_path / "migration.j9b"
    topology = _remote_topology()
    create_encrypted_backup(
        source,
        bundle,
        topology=topology,
        source_owner_node_id=LAPTOP_ID,
        key=KEY,
        key_id=KEY_ID,
    )

    for key_id, selected_topology, code in (
        ("wrong-key-id", topology, MigrationErrorCode.KEY_MISMATCH),
        (KEY_ID, _remote_topology(epoch=9), MigrationErrorCode.TOPOLOGY_MISMATCH),
    ):
        target = tmp_path / f"{key_id}-{selected_topology.epoch}.db"
        with pytest.raises(MigrationError) as error:
            restore_encrypted_backup(
                bundle,
                target,
                topology=selected_topology,
                key=KEY,
                expected_key_id=key_id,
            )
        assert error.value.code is code
        assert not target.exists()

    existing = tmp_path / "existing.db"
    existing.write_bytes(b"preserve")
    with pytest.raises(MigrationError) as error:
        restore_encrypted_backup(
            bundle,
            existing,
            topology=topology,
            key=KEY,
            expected_key_id=KEY_ID,
        )
    assert error.value.code is MigrationErrorCode.DESTINATION_EXISTS
    assert existing.read_bytes() == b"preserve"

    with pytest.raises(MigrationError) as duplicate_backup:
        create_encrypted_backup(
            source,
            bundle,
            topology=topology,
            source_owner_node_id=LAPTOP_ID,
            key=KEY,
            key_id=KEY_ID,
        )
    assert duplicate_backup.value.code is MigrationErrorCode.DESTINATION_EXISTS


def test_cutover_and_rollback_chain_one_owner_without_mutating_databases(tmp_path: Path) -> None:
    source, _bundle, target, topology, backup, _restore = _backup_and_restore(tmp_path)
    source_before = source.read_bytes()
    target_before = target.read_bytes()
    cutover_path = tmp_path / "cutover.json"

    cutover = create_cutover_receipt(
        source,
        target,
        cutover_path,
        topology=topology,
        source_owner_node_id=LAPTOP_ID,
        accepted_state_sha256=backup.accepted_state_sha256,
        now=NOW,
    )
    rollback_path = tmp_path / "rollback.json"
    rollback = create_rollback_receipt(
        target,
        source,
        rollback_path,
        topology=_local_topology(),
        previous_receipt=cutover_path,
        accepted_state_sha256=backup.accepted_state_sha256,
        now=NOW,
    )

    assert cutover.transition is OwnershipTransition.CUTOVER
    assert cutover.active_owner_node_id == SERVER_ID
    assert cutover.sequence == 1
    assert rollback.transition is OwnershipTransition.ROLLBACK
    assert rollback.active_owner_node_id == LAPTOP_ID
    assert rollback.sequence == 2
    assert rollback.previous_receipt_sha256 == cutover.digest
    assert load_transition_receipt(rollback_path) == rollback
    assert source.read_bytes() == source_before
    assert target.read_bytes() == target_before


def test_cutover_rejects_source_drift_shadow_mismatch_and_writer_lock(tmp_path: Path) -> None:
    source, _bundle, target, topology, backup, _restore = _backup_and_restore(tmp_path)
    with sqlite3.connect(source) as connection:
        connection.execute(
            """
            INSERT INTO conversations (id, metadata_json, created_at, updated_at)
            VALUES ('drift', '{}', ?, ?)
            """,
            (NOW.isoformat(), NOW.isoformat()),
        )
        connection.commit()

    with pytest.raises(MigrationError) as drift:
        create_cutover_receipt(
            source,
            target,
            tmp_path / "drift.json",
            topology=topology,
            source_owner_node_id=LAPTOP_ID,
            accepted_state_sha256=backup.accepted_state_sha256,
        )
    assert drift.value.code is MigrationErrorCode.SOURCE_DRIFT

    current_state = analyze_database(source)
    with pytest.raises(MigrationError) as mismatch:
        create_cutover_receipt(
            source,
            target,
            tmp_path / "mismatch.json",
            topology=topology,
            source_owner_node_id=LAPTOP_ID,
            accepted_state_sha256=current_state.content_sha256,
        )
    assert mismatch.value.code is MigrationErrorCode.SHADOW_MISMATCH

    with sqlite3.connect(source, isolation_level=None) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(MigrationError) as locked:
            create_cutover_receipt(
                source,
                target,
                tmp_path / "locked.json",
                topology=topology,
                source_owner_node_id=LAPTOP_ID,
                accepted_state_sha256=current_state.content_sha256,
            )
    assert locked.value.code is MigrationErrorCode.LOCKED


def test_schema_and_foreign_key_corruption_fail_closed(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.db"
    with sqlite3.connect(unknown) as connection:
        connection.execute("CREATE TABLE unexpected (id INTEGER PRIMARY KEY)")
    with pytest.raises(MigrationError) as schema:
        analyze_database(unknown)
    assert schema.value.code is MigrationErrorCode.SCHEMA_MISMATCH

    invalid = _database(tmp_path / "invalid.db")
    with sqlite3.connect(invalid) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            INSERT INTO messages
                (id, conversation_id, sequence, role, payload_json, created_at)
            VALUES ('bad-message', 'missing', 1, 'user', '{}', ?)
            """,
            (NOW.isoformat(),),
        )
        connection.commit()
    with pytest.raises(MigrationError) as foreign_key:
        analyze_database(invalid)
    assert foreign_key.value.code is MigrationErrorCode.FOREIGN_KEY_INVALID


def test_migration_key_file_accepts_raw_or_base64url_only(tmp_path: Path) -> None:
    raw = tmp_path / "raw.key"
    raw.write_bytes(KEY)
    encoded = tmp_path / "encoded.key"
    encoded.write_text(base64.urlsafe_b64encode(KEY).decode("ascii").rstrip("="), encoding="ascii")
    invalid = tmp_path / "invalid.key"
    invalid.write_text("short", encoding="ascii")

    assert read_migration_key(raw) == KEY
    assert read_migration_key(encoded) == KEY
    with pytest.raises(MigrationError) as error:
        read_migration_key(invalid)
    assert error.value.code is MigrationErrorCode.INVALID_INPUT


def test_public_migration_boundaries_reject_invalid_inputs(tmp_path: Path) -> None:
    source = _database(tmp_path / "source.db")
    topology = _remote_topology()

    cases = (
        (
            {"key": b"short", "key_id": KEY_ID, "source_owner_node_id": LAPTOP_ID},
            MigrationErrorCode.INVALID_INPUT,
        ),
        (
            {"key": KEY, "key_id": "bad key", "source_owner_node_id": LAPTOP_ID},
            MigrationErrorCode.INVALID_INPUT,
        ),
        (
            {"key": KEY, "key_id": KEY_ID, "source_owner_node_id": "bad owner"},
            MigrationErrorCode.INVALID_INPUT,
        ),
        (
            {"key": KEY, "key_id": KEY_ID, "source_owner_node_id": SERVER_ID},
            MigrationErrorCode.TOPOLOGY_MISMATCH,
        ),
    )
    for index, (arguments, expected_code) in enumerate(cases):
        with pytest.raises(MigrationError) as error:
            create_encrypted_backup(
                source,
                tmp_path / f"invalid-{index}.j9b",
                topology=topology,
                **arguments,
            )
        assert error.value.code is expected_code

    with pytest.raises(MigrationError) as local_only:
        create_encrypted_backup(
            source,
            tmp_path / "local-only.j9b",
            topology=_local_topology(),
            source_owner_node_id=LAPTOP_ID,
            key=KEY,
            key_id=KEY_ID,
        )
    assert local_only.value.code is MigrationErrorCode.TOPOLOGY_MISMATCH

    with pytest.raises(MigrationError) as missing_source:
        analyze_database(tmp_path / "missing.db")
    assert missing_source.value.code is MigrationErrorCode.SOURCE_UNAVAILABLE

    invalid_receipt = tmp_path / "invalid-receipt.json"
    invalid_receipt.write_text("{}", encoding="utf-8")
    with pytest.raises(MigrationError) as receipt:
        load_transition_receipt(invalid_receipt)
    assert receipt.value.code is MigrationErrorCode.RECEIPT_INVALID

    with pytest.raises(MigrationError) as digest:
        create_cutover_receipt(
            source,
            source,
            tmp_path / "invalid-digest.json",
            topology=topology,
            source_owner_node_id=LAPTOP_ID,
            accepted_state_sha256="invalid",
        )
    assert digest.value.code is MigrationErrorCode.INVALID_INPUT
