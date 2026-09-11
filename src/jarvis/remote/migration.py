"""Phase 9B encrypted SQLite migration, shadow verification, and ownership receipts."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import struct
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, closing
from datetime import UTC, datetime
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import BinaryIO, Final, Self
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jarvis.remote.topology import OwnershipDomain, TopologyManifest, TopologyProfile

MIGRATION_BUNDLE_FORMAT: Final = "jarvis-migration-bundle-v1"
MIGRATION_RECEIPT_FORMAT: Final = "jarvis-migration-ownership-v1"
MIGRATION_CIPHER: Final = "AES-256-GCM+HKDF-SHA256"
MIGRATION_KEY_BYTES: Final = 32
MAX_MIGRATION_DATABASE_BYTES: Final = 8 * 1_024 * 1_024 * 1_024
MAX_BUNDLE_HEADER_BYTES: Final = 4_096
MAX_BUNDLE_MANIFEST_BYTES: Final = 1_048_576
MAX_RECEIPT_BYTES: Final = 65_536

_BUNDLE_MAGIC: Final = b"JARVIS9B\x00"
_GCM_NONCE_BYTES: Final = 12
_GCM_TAG_BYTES: Final = 16
_HKDF_SALT_BYTES: Final = 32
_CHUNK_BYTES: Final = 1_048_576
_DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"
_KEY_ID_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_IDENTIFIER_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$"
_MIGRATION_PATTERN: Final = re.compile(r"^(?P<version>[0-9]{3})_[a-z0-9_]+\.sql$")
_SHARED_DOMAINS: Final = tuple(
    domain
    for domain in OwnershipDomain
    if domain
    not in {
        OwnershipDomain.DEVICE_SETTINGS,
        OwnershipDomain.COMPUTER_EFFECTS,
        OwnershipDomain.MEDIA_CAPTURE,
    }
)


class MigrationErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    SOURCE_UNAVAILABLE = "source_unavailable"
    DESTINATION_EXISTS = "destination_exists"
    DESTINATION_UNAVAILABLE = "destination_unavailable"
    DATABASE_TOO_LARGE = "database_too_large"
    DATABASE_INVALID = "database_invalid"
    SCHEMA_MISMATCH = "schema_mismatch"
    FOREIGN_KEY_INVALID = "foreign_key_invalid"
    BUNDLE_INVALID = "bundle_invalid"
    AUTHENTICATION_FAILED = "authentication_failed"
    KEY_MISMATCH = "key_mismatch"
    TOPOLOGY_MISMATCH = "topology_mismatch"
    SHADOW_MISMATCH = "shadow_mismatch"
    SOURCE_DRIFT = "source_drift"
    LOCKED = "locked"
    RECEIPT_INVALID = "receipt_invalid"
    IO_FAILED = "io_failed"


class MigrationError(RuntimeError):
    """Stable, content-free migration failure."""

    def __init__(self, code: MigrationErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class SchemaMigration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    name: str = Field(pattern=r"^[0-9]{3}_[a-z0-9_]+\.sql$")


class DatabaseTableState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=255)
    row_count: int = Field(ge=0)
    sha256: str = Field(pattern=_DIGEST_PATTERN)


class DatabaseState(BaseModel):
    """Content-free logical state used to prove two SQLite files are equivalent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database_bytes: int = Field(gt=0, le=MAX_MIGRATION_DATABASE_BYTES)
    database_sha256: str = Field(pattern=_DIGEST_PATTERN)
    schema_sha256: str = Field(pattern=_DIGEST_PATTERN)
    content_sha256: str = Field(pattern=_DIGEST_PATTERN)
    migrations: tuple[SchemaMigration, ...]
    tables: tuple[DatabaseTableState, ...] = Field(max_length=512)

    @field_validator("migrations")
    @classmethod
    def unique_migrations(cls, value: tuple[SchemaMigration, ...]) -> tuple[SchemaMigration, ...]:
        if len({item.version for item in value}) != len(value):
            raise ValueError("migration versions must be unique")
        return tuple(sorted(value, key=lambda item: item.version))

    @field_validator("tables")
    @classmethod
    def unique_tables(cls, value: tuple[DatabaseTableState, ...]) -> tuple[DatabaseTableState, ...]:
        if len({item.name for item in value}) != len(value):
            raise ValueError("table names must be unique")
        return tuple(sorted(value, key=lambda item: item.name))


class MigrationBundleManifest(BaseModel):
    """Private metadata encrypted inside a migration bundle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: str = Field(default=MIGRATION_BUNDLE_FORMAT, pattern=r"^jarvis-migration-bundle-v1$")
    operation_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    created_at: datetime
    key_id: str = Field(pattern=_KEY_ID_PATTERN)
    topology_profile: TopologyProfile
    topology_epoch: int = Field(ge=1)
    topology_digest: str = Field(pattern=_DIGEST_PATTERN)
    source_owner_node_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    target_owner_node_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    snapshot: DatabaseState

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_owner_change(self) -> Self:
        if self.topology_profile is TopologyProfile.LOCAL_ONLY:
            raise ValueError("migration bundle requires a remote target topology")
        if self.source_owner_node_id == self.target_owner_node_id:
            raise ValueError("migration source and target owners must differ")
        return self


class MigrationBundleReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    bundle_path: str
    encrypted_bytes: int = Field(gt=0)
    encrypted_sha256: str = Field(pattern=_DIGEST_PATTERN)
    key_id: str = Field(pattern=_KEY_ID_PATTERN)
    topology_digest: str = Field(pattern=_DIGEST_PATTERN)
    accepted_state_sha256: str = Field(pattern=_DIGEST_PATTERN)
    contains_private_data: bool = True


class RestoreReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    destination_path: str
    database_bytes: int = Field(gt=0)
    database_sha256: str = Field(pattern=_DIGEST_PATTERN)
    accepted_state_sha256: str = Field(pattern=_DIGEST_PATTERN)
    topology_digest: str = Field(pattern=_DIGEST_PATTERN)
    integrity_check: str = Field(pattern=r"^ok$")
    foreign_key_check: str = Field(pattern=r"^ok$")


class ShadowComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    matched: bool
    accepted_state_sha256: str = Field(pattern=_DIGEST_PATTERN)
    source_database_sha256: str = Field(pattern=_DIGEST_PATTERN)
    target_database_sha256: str = Field(pattern=_DIGEST_PATTERN)
    table_count: int = Field(ge=0)


class OwnershipTransition(StrEnum):
    CUTOVER = "cutover"
    ROLLBACK = "rollback"


class OwnershipTransitionReceipt(BaseModel):
    """Content-free, chained proof of one accepted state owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: str = Field(
        default=MIGRATION_RECEIPT_FORMAT, pattern=r"^jarvis-migration-ownership-v1$"
    )
    operation_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    transition: OwnershipTransition
    sequence: int = Field(ge=1)
    created_at: datetime
    topology_profile: TopologyProfile
    topology_epoch: int = Field(ge=1)
    topology_digest: str = Field(pattern=_DIGEST_PATTERN)
    previous_receipt_sha256: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    from_owner_node_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    active_owner_node_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    accepted_state_sha256: str = Field(pattern=_DIGEST_PATTERN)
    source_database_sha256: str = Field(pattern=_DIGEST_PATTERN)
    target_database_sha256: str = Field(pattern=_DIGEST_PATTERN)

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_chain_shape(self) -> Self:
        if self.from_owner_node_id == self.active_owner_node_id:
            raise ValueError("ownership transition must change owner")
        if self.sequence == 1 and self.previous_receipt_sha256 is not None:
            raise ValueError("first ownership receipt cannot have a predecessor")
        if self.sequence > 1 and self.previous_receipt_sha256 is None:
            raise ValueError("later ownership receipt requires a predecessor")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical_json(self.model_dump(mode="json")) + b"\n").hexdigest()


class _BundleHeader(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: str = Field(default=MIGRATION_BUNDLE_FORMAT, pattern=r"^jarvis-migration-bundle-v1$")
    cipher: str = Field(default=MIGRATION_CIPHER, pattern=r"^AES-256-GCM\+HKDF-SHA256$")
    key_id: str = Field(pattern=_KEY_ID_PATTERN)
    salt: str
    nonce: str


def read_migration_key(path: Path) -> bytes:
    """Read exactly one raw/base64url 256-bit key from a separate private file."""
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 256:
            raise OSError("unsafe migration key path")
        raw = path.read_bytes()
    except OSError as exc:
        raise MigrationError(
            MigrationErrorCode.INVALID_INPUT, "migration key is unavailable"
        ) from exc
    if len(raw) == MIGRATION_KEY_BYTES:
        return raw
    try:
        encoded = raw.decode("ascii").strip()
        key = _decode_base64url(encoded)
    except (UnicodeDecodeError, ValueError) as exc:
        raise MigrationError(
            MigrationErrorCode.INVALID_INPUT,
            "migration key must contain exactly 32 raw bytes or one base64url value",
        ) from exc
    if len(key) != MIGRATION_KEY_BYTES:
        raise MigrationError(
            MigrationErrorCode.INVALID_INPUT,
            "migration key must contain exactly 32 raw bytes or one base64url value",
        )
    return key


def analyze_database(path: Path) -> DatabaseState:
    """Validate and fingerprint a current JARVIS SQLite database without changing it."""
    source = path.resolve()
    _require_source_file(source)
    try:
        with closing(_connect(source, read_only=True)) as connection:
            return _analyze_connection(connection, source)
    except MigrationError:
        raise
    except sqlite3.Error as exc:
        raise MigrationError(
            MigrationErrorCode.DATABASE_INVALID, "database validation failed"
        ) from exc


def create_encrypted_backup(
    source: Path,
    destination: Path,
    *,
    topology: TopologyManifest,
    source_owner_node_id: str,
    key: bytes,
    key_id: str,
    now: datetime | None = None,
) -> MigrationBundleReceipt:
    """Create one authenticated, encrypted, no-overwrite SQLite migration bundle."""
    source_path = source.resolve()
    target_path = destination.resolve()
    _validate_key(key)
    _validate_key_id(key_id)
    _validate_identifier(source_owner_node_id)
    target_owner = _shared_owner(topology, require_remote=True)
    if source_owner_node_id == target_owner:
        raise MigrationError(MigrationErrorCode.TOPOLOGY_MISMATCH, "migration owners are unchanged")
    _require_source_file(source_path)
    _require_new_destination(target_path)

    snapshot_path = _temporary_path(target_path.parent, suffix=".db")
    created_target = False
    try:
        with (
            closing(_connect(source_path, read_only=True)) as source_connection,
            closing(sqlite3.connect(snapshot_path, timeout=30)) as snapshot_connection,
        ):
            source_connection.backup(snapshot_connection, pages=256, sleep=0.01)
            snapshot_connection.commit()
            snapshot_connection.execute("PRAGMA journal_mode = DELETE")
            snapshot_connection.commit()
        _flush_path(snapshot_path)
        snapshot = analyze_database(snapshot_path)
        manifest = MigrationBundleManifest(
            operation_id=f"migration:{uuid4()}",
            created_at=(now or datetime.now(UTC)),
            key_id=key_id,
            topology_profile=topology.profile,
            topology_epoch=topology.epoch,
            topology_digest=topology.digest,
            source_owner_node_id=source_owner_node_id,
            target_owner_node_id=target_owner,
            snapshot=snapshot,
        )
        encrypted_bytes, encrypted_sha256 = _encrypt_snapshot(
            snapshot_path,
            target_path,
            manifest=manifest,
            key=key,
        )
        created_target = True
        return MigrationBundleReceipt(
            operation_id=manifest.operation_id,
            bundle_path=str(target_path),
            encrypted_bytes=encrypted_bytes,
            encrypted_sha256=encrypted_sha256,
            key_id=key_id,
            topology_digest=topology.digest,
            accepted_state_sha256=snapshot.content_sha256,
        )
    except MigrationError:
        if created_target or target_path.exists():
            target_path.unlink(missing_ok=True)
        raise
    except (OSError, sqlite3.Error) as exc:
        if created_target or target_path.exists():
            target_path.unlink(missing_ok=True)
        raise MigrationError(MigrationErrorCode.IO_FAILED, "encrypted backup failed") from exc
    finally:
        _remove_database_artifacts(snapshot_path)


def restore_encrypted_backup(
    bundle: Path,
    destination: Path,
    *,
    topology: TopologyManifest,
    key: bytes,
    expected_key_id: str,
) -> RestoreReceipt:
    """Authenticate, decrypt, and verify a migration bundle into a new SQLite path."""
    bundle_path = bundle.resolve()
    target_path = destination.resolve()
    _validate_key(key)
    _validate_key_id(expected_key_id)
    _require_source_file(bundle_path)
    _require_new_destination(target_path)

    plaintext_path = _temporary_path(target_path.parent, suffix=".payload")
    created_target = False
    try:
        header, plaintext_bytes = _decrypt_bundle(
            bundle_path,
            plaintext_path,
            key=key,
            expected_key_id=expected_key_id,
        )
        with plaintext_path.open("rb") as payload:
            raw_length = payload.read(8)
            if len(raw_length) != 8:
                raise MigrationError(
                    MigrationErrorCode.BUNDLE_INVALID, "migration bundle is invalid"
                )
            manifest_length = struct.unpack(">Q", raw_length)[0]
            if not 1 <= manifest_length <= MAX_BUNDLE_MANIFEST_BYTES:
                raise MigrationError(
                    MigrationErrorCode.BUNDLE_INVALID, "migration bundle is invalid"
                )
            manifest_bytes = payload.read(manifest_length)
            if len(manifest_bytes) != manifest_length:
                raise MigrationError(
                    MigrationErrorCode.BUNDLE_INVALID, "migration bundle is invalid"
                )
            try:
                manifest = MigrationBundleManifest.model_validate_json(manifest_bytes)
            except ValueError as exc:
                raise MigrationError(
                    MigrationErrorCode.BUNDLE_INVALID, "migration bundle manifest is invalid"
                ) from exc
            _validate_bundle_binding(manifest, header, topology, expected_key_id)
            database_bytes = plaintext_bytes - 8 - manifest_length
            if database_bytes != manifest.snapshot.database_bytes:
                raise MigrationError(
                    MigrationErrorCode.BUNDLE_INVALID, "migration bundle is truncated"
                )
            with _open_private_exclusive(target_path) as target:
                created_target = True
                _copy_exact(payload, target, database_bytes)
                target.flush()
                os.fsync(target.fileno())
        restored = analyze_database(target_path)
        if restored != manifest.snapshot:
            raise MigrationError(
                MigrationErrorCode.SHADOW_MISMATCH,
                "restored database does not match backup manifest",
            )
        _private_permissions(target_path)
        return RestoreReceipt(
            operation_id=manifest.operation_id,
            destination_path=str(target_path),
            database_bytes=restored.database_bytes,
            database_sha256=restored.database_sha256,
            accepted_state_sha256=restored.content_sha256,
            topology_digest=topology.digest,
            integrity_check="ok",
            foreign_key_check="ok",
        )
    except MigrationError:
        if created_target:
            target_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        if created_target:
            target_path.unlink(missing_ok=True)
        raise MigrationError(MigrationErrorCode.IO_FAILED, "migration restore failed") from exc
    finally:
        plaintext_path.unlink(missing_ok=True)


def compare_shadow(source: Path, target: Path) -> ShadowComparison:
    """Require exact logical equality between two independently laid-out SQLite databases."""
    source_state = analyze_database(source)
    target_state = analyze_database(target)
    _require_equivalent(source_state, target_state)
    return ShadowComparison(
        matched=True,
        accepted_state_sha256=source_state.content_sha256,
        source_database_sha256=source_state.database_sha256,
        target_database_sha256=target_state.database_sha256,
        table_count=len(source_state.tables),
    )


def create_cutover_receipt(
    source: Path,
    target: Path,
    destination: Path,
    *,
    topology: TopologyManifest,
    source_owner_node_id: str,
    accepted_state_sha256: str,
    now: datetime | None = None,
) -> OwnershipTransitionReceipt:
    """Prove an idle, unchanged source and target before selecting the remote owner."""
    _validate_identifier(source_owner_node_id)
    target_owner = _shared_owner(topology, require_remote=True)
    if source_owner_node_id == target_owner:
        raise MigrationError(MigrationErrorCode.TOPOLOGY_MISMATCH, "cutover owners are unchanged")
    return _create_transition_receipt(
        source,
        target,
        destination,
        topology=topology,
        transition=OwnershipTransition.CUTOVER,
        from_owner_node_id=source_owner_node_id,
        active_owner_node_id=target_owner,
        accepted_state_sha256=accepted_state_sha256,
        previous=None,
        now=now,
    )


def create_rollback_receipt(
    active: Path,
    restored_local: Path,
    destination: Path,
    *,
    topology: TopologyManifest,
    previous_receipt: Path,
    accepted_state_sha256: str,
    now: datetime | None = None,
) -> OwnershipTransitionReceipt:
    """Prove reverse synchronization and chain ownership back to one local owner."""
    if topology.profile is not TopologyProfile.LOCAL_ONLY:
        raise MigrationError(
            MigrationErrorCode.TOPOLOGY_MISMATCH, "rollback requires a local-only topology"
        )
    previous_path = previous_receipt.resolve()
    previous = load_transition_receipt(previous_path)
    if previous.transition is not OwnershipTransition.CUTOVER:
        raise MigrationError(MigrationErrorCode.RECEIPT_INVALID, "rollback predecessor is invalid")
    if topology.epoch <= previous.topology_epoch:
        raise MigrationError(
            MigrationErrorCode.TOPOLOGY_MISMATCH, "rollback topology epoch must advance"
        )
    local_owner = _shared_owner(topology, require_remote=False)
    if local_owner == previous.active_owner_node_id:
        raise MigrationError(MigrationErrorCode.TOPOLOGY_MISMATCH, "rollback owners are unchanged")
    return _create_transition_receipt(
        active,
        restored_local,
        destination,
        topology=topology,
        transition=OwnershipTransition.ROLLBACK,
        from_owner_node_id=previous.active_owner_node_id,
        active_owner_node_id=local_owner,
        accepted_state_sha256=accepted_state_sha256,
        previous=(previous_path, previous),
        now=now,
    )


def load_transition_receipt(path: Path) -> OwnershipTransitionReceipt:
    receipt_path = path.resolve()
    _require_source_file(receipt_path, max_bytes=MAX_RECEIPT_BYTES)
    try:
        return OwnershipTransitionReceipt.model_validate_json(receipt_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise MigrationError(
            MigrationErrorCode.RECEIPT_INVALID, "ownership receipt is invalid"
        ) from exc


def _create_transition_receipt(
    source: Path,
    target: Path,
    destination: Path,
    *,
    topology: TopologyManifest,
    transition: OwnershipTransition,
    from_owner_node_id: str,
    active_owner_node_id: str,
    accepted_state_sha256: str,
    previous: tuple[Path, OwnershipTransitionReceipt] | None,
    now: datetime | None,
) -> OwnershipTransitionReceipt:
    if re.fullmatch(_DIGEST_PATTERN, accepted_state_sha256) is None:
        raise MigrationError(MigrationErrorCode.INVALID_INPUT, "accepted state digest is invalid")
    source_path = source.resolve()
    target_path = target.resolve()
    receipt_path = destination.resolve()
    if source_path == target_path:
        raise MigrationError(MigrationErrorCode.INVALID_INPUT, "transition databases must differ")
    _require_source_file(source_path)
    _require_source_file(target_path)
    _require_new_destination(receipt_path)

    try:
        with ExitStack() as stack:
            connections: dict[Path, sqlite3.Connection] = {}
            for path in sorted((source_path, target_path), key=lambda item: str(item).casefold()):
                connection = stack.enter_context(closing(_connect(path, read_only=False)))
                connection.execute("BEGIN IMMEDIATE")
                connections[path] = connection
            source_state = _analyze_connection(connections[source_path], source_path)
            target_state = _analyze_connection(connections[target_path], target_path)
            if source_state.content_sha256 != accepted_state_sha256:
                raise MigrationError(
                    MigrationErrorCode.SOURCE_DRIFT, "database changed after accepted snapshot"
                )
            _require_equivalent(source_state, target_state)
            previous_digest = None
            sequence = 1
            if previous is not None:
                previous_path, previous_receipt = previous
                previous_digest = _sha256_file(previous_path)
                if previous_digest != previous_receipt.digest:
                    raise MigrationError(
                        MigrationErrorCode.RECEIPT_INVALID, "ownership receipt digest is invalid"
                    )
                if previous_receipt.accepted_state_sha256 != accepted_state_sha256:
                    raise MigrationError(
                        MigrationErrorCode.SOURCE_DRIFT, "rollback state differs from cutover state"
                    )
                sequence = previous_receipt.sequence + 1
            receipt = OwnershipTransitionReceipt(
                operation_id=f"migration:{uuid4()}",
                transition=transition,
                sequence=sequence,
                created_at=now or datetime.now(UTC),
                topology_profile=topology.profile,
                topology_epoch=topology.epoch,
                topology_digest=topology.digest,
                previous_receipt_sha256=previous_digest,
                from_owner_node_id=from_owner_node_id,
                active_owner_node_id=active_owner_node_id,
                accepted_state_sha256=accepted_state_sha256,
                source_database_sha256=source_state.database_sha256,
                target_database_sha256=target_state.database_sha256,
            )
            _write_private_json(receipt_path, receipt.model_dump(mode="json"))
            for connection in connections.values():
                connection.rollback()
            return receipt
    except MigrationError:
        receipt_path.unlink(missing_ok=True)
        raise
    except sqlite3.OperationalError as exc:
        receipt_path.unlink(missing_ok=True)
        code = (
            MigrationErrorCode.LOCKED
            if "locked" in str(exc).casefold()
            else MigrationErrorCode.IO_FAILED
        )
        raise MigrationError(
            code, "migration transition could not obtain exclusive writer locks"
        ) from exc
    except (OSError, sqlite3.Error) as exc:
        receipt_path.unlink(missing_ok=True)
        raise MigrationError(MigrationErrorCode.IO_FAILED, "migration transition failed") from exc


def _analyze_connection(connection: sqlite3.Connection, path: Path) -> DatabaseState:
    size = path.stat().st_size
    if not 0 < size <= MAX_MIGRATION_DATABASE_BYTES:
        code = (
            MigrationErrorCode.DATABASE_TOO_LARGE
            if size > MAX_MIGRATION_DATABASE_BYTES
            else MigrationErrorCode.DATABASE_INVALID
        )
        raise MigrationError(code, "database size is outside migration bounds")
    integrity = tuple(row[0] for row in connection.execute("PRAGMA integrity_check"))
    if integrity != ("ok",):
        raise MigrationError(MigrationErrorCode.DATABASE_INVALID, "database integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise MigrationError(
            MigrationErrorCode.FOREIGN_KEY_INVALID, "database foreign-key check failed"
        )

    schema_rows = tuple(
        connection.execute(
            """
            SELECT type, name, tbl_name, COALESCE(sql, '')
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name, tbl_name, sql
            """
        )
    )
    table_names = tuple(
        str(row[0])
        for row in connection.execute(
            """
            SELECT name FROM sqlite_schema
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    )
    if len(table_names) > 512:
        raise MigrationError(MigrationErrorCode.SCHEMA_MISMATCH, "database has too many tables")
    migrations = _read_migrations(connection)
    if migrations != _expected_migrations():
        raise MigrationError(
            MigrationErrorCode.SCHEMA_MISMATCH, "database migrations do not match this release"
        )
    tables = tuple(_fingerprint_table(connection, name) for name in table_names)
    schema_sha256 = hashlib.sha256(_canonical_json(schema_rows)).hexdigest()
    content_sha256 = hashlib.sha256(
        _canonical_json(
            {
                "schema_sha256": schema_sha256,
                "migrations": [item.model_dump(mode="json") for item in migrations],
                "tables": [item.model_dump(mode="json") for item in tables],
            }
        )
    ).hexdigest()
    return DatabaseState(
        database_bytes=size,
        database_sha256=_sha256_file(path),
        schema_sha256=schema_sha256,
        content_sha256=content_sha256,
        migrations=migrations,
        tables=tables,
    )


def _read_migrations(connection: sqlite3.Connection) -> tuple[SchemaMigration, ...]:
    try:
        rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
    except sqlite3.Error as exc:
        raise MigrationError(
            MigrationErrorCode.SCHEMA_MISMATCH, "schema migration ledger is unavailable"
        ) from exc
    return tuple(SchemaMigration(version=int(row[0]), name=str(row[1])) for row in rows)


def _expected_migrations() -> tuple[SchemaMigration, ...]:
    expected: list[SchemaMigration] = []
    for resource in files("jarvis.memory.migrations").iterdir():
        match = _MIGRATION_PATTERN.fullmatch(resource.name)
        if match is not None:
            expected.append(
                SchemaMigration(version=int(match.group("version")), name=resource.name)
            )
    return tuple(sorted(expected, key=lambda item: item.version))


def _fingerprint_table(connection: sqlite3.Connection, name: str) -> DatabaseTableState:
    quoted = _quote_identifier(name)
    columns = tuple(
        (str(row[1]), int(row[5])) for row in connection.execute(f"PRAGMA table_info({quoted})")
    )
    if not columns:
        raise MigrationError(MigrationErrorCode.SCHEMA_MISMATCH, "table has no visible columns")
    order_names = [item[0] for item in sorted(columns, key=lambda item: (item[1] == 0, item[1]))]
    order = ", ".join(_quote_identifier(column) for column in order_names)
    digest = hashlib.sha256()
    count = 0
    for row in connection.execute(f"SELECT * FROM {quoted} ORDER BY {order}"):
        encoded = _canonical_json([_sqlite_value(value) for value in row])
        digest.update(struct.pack(">Q", len(encoded)))
        digest.update(encoded)
        count += 1
    return DatabaseTableState(name=name, row_count=count, sha256=digest.hexdigest())


def _sqlite_value(value: object) -> dict[str, object]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bytes):
        return {"type": "blob", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "real", "value": value.hex()}
    if isinstance(value, str):
        return {"type": "text", "value": value}
    raise MigrationError(MigrationErrorCode.DATABASE_INVALID, "database contains unsupported data")


def _encrypt_snapshot(
    snapshot: Path,
    destination: Path,
    *,
    manifest: MigrationBundleManifest,
    key: bytes,
) -> tuple[int, str]:
    salt = os.urandom(_HKDF_SALT_BYTES)
    nonce = os.urandom(_GCM_NONCE_BYTES)
    header = _BundleHeader(
        key_id=manifest.key_id,
        salt=_encode_base64url(salt),
        nonce=_encode_base64url(nonce),
    )
    header_bytes = _canonical_json(header.model_dump(mode="json"))
    if len(header_bytes) > MAX_BUNDLE_HEADER_BYTES:
        raise MigrationError(
            MigrationErrorCode.BUNDLE_INVALID, "migration bundle header is invalid"
        )
    prefix = _BUNDLE_MAGIC + struct.pack(">I", len(header_bytes)) + header_bytes
    derived_key = _derive_key(key, salt=salt, key_id=manifest.key_id)
    encryptor = Cipher(algorithms.AES(derived_key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(prefix)
    manifest_bytes = _canonical_json(manifest.model_dump(mode="json"))
    if len(manifest_bytes) > MAX_BUNDLE_MANIFEST_BYTES:
        raise MigrationError(
            MigrationErrorCode.BUNDLE_INVALID, "migration bundle manifest is too large"
        )
    with _open_private_exclusive(destination) as output, snapshot.open("rb") as source:
        output.write(prefix)
        output.write(encryptor.update(struct.pack(">Q", len(manifest_bytes))))
        output.write(encryptor.update(manifest_bytes))
        for chunk in iter(lambda: source.read(_CHUNK_BYTES), b""):
            output.write(encryptor.update(chunk))
        output.write(encryptor.finalize())
        output.write(encryptor.tag)
        output.flush()
        os.fsync(output.fileno())
    return destination.stat().st_size, _sha256_file(destination)


def _decrypt_bundle(
    bundle: Path,
    destination: Path,
    *,
    key: bytes,
    expected_key_id: str,
) -> tuple[_BundleHeader, int]:
    size = bundle.stat().st_size
    if (
        size <= len(_BUNDLE_MAGIC) + 4 + _GCM_TAG_BYTES
        or size > MAX_MIGRATION_DATABASE_BYTES + 2_000_000
    ):
        raise MigrationError(MigrationErrorCode.BUNDLE_INVALID, "migration bundle size is invalid")
    with bundle.open("rb") as source:
        magic = source.read(len(_BUNDLE_MAGIC))
        raw_header_length = source.read(4)
        if magic != _BUNDLE_MAGIC or len(raw_header_length) != 4:
            raise MigrationError(
                MigrationErrorCode.BUNDLE_INVALID, "migration bundle header is invalid"
            )
        header_length = struct.unpack(">I", raw_header_length)[0]
        if not 1 <= header_length <= MAX_BUNDLE_HEADER_BYTES:
            raise MigrationError(
                MigrationErrorCode.BUNDLE_INVALID, "migration bundle header is invalid"
            )
        header_bytes = source.read(header_length)
        try:
            header = _BundleHeader.model_validate_json(header_bytes)
            salt = _decode_base64url(header.salt)
            nonce = _decode_base64url(header.nonce)
        except (ValueError, UnicodeDecodeError) as exc:
            raise MigrationError(
                MigrationErrorCode.BUNDLE_INVALID, "migration bundle header is invalid"
            ) from exc
        if len(salt) != _HKDF_SALT_BYTES or len(nonce) != _GCM_NONCE_BYTES:
            raise MigrationError(
                MigrationErrorCode.BUNDLE_INVALID, "migration bundle header is invalid"
            )
        if header.key_id != expected_key_id:
            raise MigrationError(MigrationErrorCode.KEY_MISMATCH, "migration key ID does not match")
        prefix = magic + raw_header_length + header_bytes
        ciphertext_length = size - len(prefix) - _GCM_TAG_BYTES
        source.seek(size - _GCM_TAG_BYTES)
        tag = source.read(_GCM_TAG_BYTES)
        source.seek(len(prefix))
        decryptor = Cipher(
            algorithms.AES(_derive_key(key, salt=salt, key_id=header.key_id)),
            modes.GCM(nonce, tag),
        ).decryptor()
        decryptor.authenticate_additional_data(prefix)
        remaining = ciphertext_length
        try:
            with _open_private_exclusive(destination) as output:
                while remaining:
                    chunk = source.read(min(_CHUNK_BYTES, remaining))
                    if not chunk:
                        raise MigrationError(
                            MigrationErrorCode.BUNDLE_INVALID, "migration bundle is truncated"
                        )
                    remaining -= len(chunk)
                    output.write(decryptor.update(chunk))
                output.write(decryptor.finalize())
                output.flush()
                os.fsync(output.fileno())
        except InvalidTag as exc:
            destination.unlink(missing_ok=True)
            raise MigrationError(
                MigrationErrorCode.AUTHENTICATION_FAILED, "migration bundle authentication failed"
            ) from exc
    return header, destination.stat().st_size


def _validate_bundle_binding(
    manifest: MigrationBundleManifest,
    header: _BundleHeader,
    topology: TopologyManifest,
    expected_key_id: str,
) -> None:
    target_owner = _shared_owner(topology, require_remote=True)
    if manifest.key_id != header.key_id or manifest.key_id != expected_key_id:
        raise MigrationError(MigrationErrorCode.KEY_MISMATCH, "migration key ID does not match")
    if (
        manifest.topology_profile is not topology.profile
        or manifest.topology_epoch != topology.epoch
        or manifest.topology_digest != topology.digest
        or manifest.target_owner_node_id != target_owner
    ):
        raise MigrationError(
            MigrationErrorCode.TOPOLOGY_MISMATCH, "migration topology does not match"
        )


def _shared_owner(topology: TopologyManifest, *, require_remote: bool) -> str:
    if require_remote and topology.profile is TopologyProfile.LOCAL_ONLY:
        raise MigrationError(
            MigrationErrorCode.TOPOLOGY_MISMATCH, "migration requires a remote target topology"
        )
    owners = {topology.owner_for(domain) for domain in _SHARED_DOMAINS}
    if len(owners) != 1:
        raise MigrationError(
            MigrationErrorCode.TOPOLOGY_MISMATCH, "shared state must have exactly one owner"
        )
    return next(iter(owners))


def _require_equivalent(source: DatabaseState, target: DatabaseState) -> None:
    if (
        source.schema_sha256 != target.schema_sha256
        or source.content_sha256 != target.content_sha256
        or source.migrations != target.migrations
        or source.tables != target.tables
    ):
        raise MigrationError(MigrationErrorCode.SHADOW_MISMATCH, "shadow databases differ")


def _connect(path: Path, *, read_only: bool) -> sqlite3.Connection:
    mode = "ro" if read_only else "rw"
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode={mode}",
        uri=True,
        timeout=0.25,
        isolation_level=None,
    )
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 250")
    if read_only:
        connection.execute("PRAGMA query_only = ON")
    return connection


def _require_source_file(path: Path, *, max_bytes: int = MAX_MIGRATION_DATABASE_BYTES) -> None:
    try:
        is_file = path.is_file()
        is_link = path.is_symlink()
        size = path.stat().st_size if is_file else 0
    except OSError as exc:
        raise MigrationError(
            MigrationErrorCode.SOURCE_UNAVAILABLE, "source is unavailable"
        ) from exc
    if not is_file or is_link:
        raise MigrationError(MigrationErrorCode.SOURCE_UNAVAILABLE, "source is unavailable")
    if not 0 < size <= max_bytes:
        raise MigrationError(MigrationErrorCode.DATABASE_TOO_LARGE, "source size is outside bounds")


def _require_new_destination(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise MigrationError(MigrationErrorCode.DESTINATION_EXISTS, "destination already exists")
    if not path.parent.is_dir():
        raise MigrationError(
            MigrationErrorCode.DESTINATION_UNAVAILABLE, "destination directory is unavailable"
        )


def _temporary_path(parent: Path, *, suffix: str) -> Path:
    try:
        handle, raw_path = tempfile.mkstemp(prefix=".jarvis-phase9b-", suffix=suffix, dir=parent)
        os.close(handle)
        path = Path(raw_path)
        path.unlink()
        return path
    except OSError as exc:
        raise MigrationError(
            MigrationErrorCode.DESTINATION_UNAVAILABLE, "temporary destination is unavailable"
        ) from exc


def _derive_key(master: bytes, *, salt: bytes, key_id: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=MIGRATION_KEY_BYTES,
        salt=salt,
        info=f"jarvis-phase9b:{key_id}".encode("ascii"),
    ).derive(master)


def _validate_key(key: bytes) -> None:
    if not isinstance(key, bytes) or len(key) != MIGRATION_KEY_BYTES:
        raise MigrationError(MigrationErrorCode.INVALID_INPUT, "migration key must be 32 bytes")


def _validate_key_id(key_id: str) -> None:
    if re.fullmatch(_KEY_ID_PATTERN, key_id) is None:
        raise MigrationError(MigrationErrorCode.INVALID_INPUT, "migration key ID is invalid")


def _validate_identifier(value: str) -> None:
    if re.fullmatch(_IDENTIFIER_PATTERN, value) is None:
        raise MigrationError(MigrationErrorCode.INVALID_INPUT, "migration owner ID is invalid")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_private_json(path: Path, value: object) -> None:
    payload = _canonical_json(value) + b"\n"
    with _open_private_exclusive(path) as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def _open_private_exclusive(path: Path) -> BinaryIO:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise MigrationError(
            MigrationErrorCode.DESTINATION_EXISTS, "destination already exists"
        ) from exc
    try:
        return os.fdopen(descriptor, "wb")
    except Exception as exc:
        os.close(descriptor)
        path.unlink(missing_ok=True)
        raise MigrationError(
            MigrationErrorCode.IO_FAILED, "private destination could not be opened"
        ) from exc


def _copy_exact(source: object, target: object, size: int) -> None:
    remaining = size
    while remaining:
        chunk = source.read(min(_CHUNK_BYTES, remaining))  # type: ignore[attr-defined]
        if not chunk:
            raise MigrationError(MigrationErrorCode.BUNDLE_INVALID, "migration bundle is truncated")
        target.write(chunk)  # type: ignore[attr-defined]
        remaining -= len(chunk)
    if source.read(1):  # type: ignore[attr-defined]
        raise MigrationError(
            MigrationErrorCode.BUNDLE_INVALID, "migration bundle has trailing data"
        )


def _flush_path(path: Path) -> None:
    with path.open("r+b") as source:
        os.fsync(source.fileno())


def _remove_database_artifacts(path: Path) -> None:
    path.unlink(missing_ok=True)
    path.with_name(path.name + "-wal").unlink(missing_ok=True)
    path.with_name(path.name + "-shm").unlink(missing_ok=True)


def _private_permissions(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError as exc:
        raise MigrationError(
            MigrationErrorCode.IO_FAILED, "private file permissions failed"
        ) from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64url(value: str) -> bytes:
    if not value or re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value) is None:
        raise ValueError("invalid base64url")
    unpadded = value.rstrip("=")
    return base64.b64decode(
        unpadded + "=" * (-len(unpadded) % 4),
        altchars=b"-_",
        validate=True,
    )


def iter_shared_domains() -> Iterator[OwnershipDomain]:
    """Expose the exact Phase 9B shared-state classification for diagnostics/docs tests."""
    return iter(_SHARED_DOMAINS)
