"""SQLite persistence for Phase 8A device identities and sessions."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite

from jarvis.memory.sqlite_store import SQLiteConversationStore
from jarvis.remote.models import (
    DeviceRecord,
    DeviceState,
    DeviceType,
    EnrollmentTicket,
    RemoteAuditEvent,
    RemoteAuditOutcome,
    RemoteScope,
    RemoteSessionKind,
)

_MAX_DENIAL_AUDIT_EVENTS = 1_000


@dataclass(frozen=True, slots=True)
class StoredEnrollment:
    id: str
    challenge_sha256: str
    host_id: str
    display_name: str
    device_type: DeviceType
    approved_scopes: tuple[RemoteScope, ...]
    risk_ceiling: int
    expires_at: datetime
    consumed_at: datetime | None


@dataclass(frozen=True, slots=True)
class StoredDevice:
    record: DeviceRecord
    public_key: str


@dataclass(frozen=True, slots=True)
class StoredSession:
    id: str
    token_sha256: str
    device_id: str
    key_version: int
    audience: str
    scopes: tuple[RemoteScope, ...]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    session_kind: RemoteSessionKind
    csrf_token_sha256: str | None


class SQLiteRemoteIdentityStore:
    """Serialized durable store; all lifecycle mutations are atomic."""

    def __init__(self, database_path: str | Path, *, busy_timeout_ms: int = 5_000) -> None:
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        self._database_path = Path(database_path)
        self._busy_timeout_ms = busy_timeout_ms
        self._connection: aiosqlite.Connection | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lifecycle_lock:
            if self._connection is not None:
                return
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = await aiosqlite.connect(self._database_path)
            connection.row_factory = aiosqlite.Row
            try:
                await connection.execute("PRAGMA foreign_keys = ON")
                await connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms:d}")
                await connection.execute("PRAGMA journal_mode = WAL")
                await connection.execute("PRAGMA synchronous = NORMAL")
                await SQLiteConversationStore._apply_migrations(connection)
            except BaseException:
                await connection.close()
                raise
            self._connection = connection

    async def close(self) -> None:
        async with self._operation_lock, self._lifecycle_lock:
            connection = self._connection
            self._connection = None
            if connection is not None:
                await connection.close()

    async def create_enrollment(
        self,
        ticket: EnrollmentTicket,
        *,
        challenge_sha256: str,
        created_at: datetime,
    ) -> None:
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                await connection.execute(
                    """
                    INSERT INTO remote_enrollments (
                        id, challenge_sha256, host_id, display_name, device_type, scopes_json,
                        risk_ceiling, expires_at, created_at, consumed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        ticket.id,
                        challenge_sha256,
                        ticket.host_id,
                        ticket.display_name,
                        ticket.device_type.value,
                        _dump_scopes(ticket.approved_scopes),
                        ticket.risk_ceiling,
                        _timestamp(ticket.expires_at),
                        _timestamp(created_at),
                    ),
                )
                await self._insert_audit(
                    connection,
                    event_type="enrollment.created",
                    outcome=RemoteAuditOutcome.SUCCEEDED,
                    reason_code="local_host_authorized",
                    enrollment_id=ticket.id,
                    created_at=created_at,
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise

    async def get_enrollment(self, enrollment_id: str) -> StoredEnrollment | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                "SELECT * FROM remote_enrollments WHERE id = ?", (enrollment_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return None if row is None else _stored_enrollment(row)

    async def complete_enrollment(
        self,
        *,
        enrollment: StoredEnrollment,
        device_id: str,
        public_key: str,
        key_fingerprint: str,
        protocol_version: str,
        credential_expires_at: datetime,
        completed_at: datetime,
    ) -> DeviceRecord | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = await connection.execute(
                    """
                    UPDATE remote_enrollments SET consumed_at = ?
                    WHERE id = ? AND consumed_at IS NULL AND expires_at > ?
                    """,
                    (
                        _timestamp(completed_at),
                        enrollment.id,
                        _timestamp(completed_at),
                    ),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    return None
                record = DeviceRecord(
                    id=device_id,
                    host_id=enrollment.host_id,
                    display_name=enrollment.display_name,
                    device_type=enrollment.device_type,
                    key_fingerprint=key_fingerprint,
                    key_version=1,
                    approved_scopes=enrollment.approved_scopes,
                    risk_ceiling=enrollment.risk_ceiling,
                    protocol_version=protocol_version,
                    state=DeviceState.ACTIVE,
                    enrolled_at=completed_at,
                    credential_expires_at=credential_expires_at,
                )
                await connection.execute(
                    """
                    INSERT INTO remote_devices (
                        id, host_id, display_name, device_type, public_key, key_fingerprint,
                        key_version, scopes_json, risk_ceiling, protocol_version, state,
                        enrolled_at, credential_expires_at, last_seen_at, revoked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                    """,
                    (
                        record.id,
                        record.host_id,
                        record.display_name,
                        record.device_type.value,
                        public_key,
                        record.key_fingerprint,
                        record.key_version,
                        _dump_scopes(record.approved_scopes),
                        record.risk_ceiling,
                        record.protocol_version,
                        record.state.value,
                        _timestamp(record.enrolled_at),
                        _timestamp(record.credential_expires_at),
                    ),
                )
                await self._insert_audit(
                    connection,
                    event_type="enrollment.completed",
                    outcome=RemoteAuditOutcome.SUCCEEDED,
                    reason_code="proof_verified",
                    device_id=record.id,
                    enrollment_id=enrollment.id,
                    created_at=completed_at,
                )
                await connection.commit()
                return record
            except aiosqlite.IntegrityError:
                await connection.rollback()
                return None
            except BaseException:
                await connection.rollback()
                raise

    async def get_device(self, device_id: str) -> StoredDevice | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                "SELECT * FROM remote_devices WHERE id = ?", (device_id,)
            ) as cursor:
                row = await cursor.fetchone()
        return None if row is None else _stored_device(row)

    async def list_devices(self, *, host_id: str) -> tuple[DeviceRecord, ...]:
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT * FROM remote_devices WHERE host_id = ?
                ORDER BY enrolled_at DESC, id DESC
                """,
                (host_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return tuple(_stored_device(row).record for row in rows)

    async def create_session(
        self,
        *,
        session_id: str,
        token_sha256: str,
        device: DeviceRecord,
        audience: str,
        scopes: tuple[RemoteScope, ...],
        created_at: datetime,
        expires_at: datetime,
        session_kind: RemoteSessionKind = RemoteSessionKind.SIGNED_API,
        csrf_token_sha256: str | None = None,
    ) -> None:
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    """
                    SELECT state, key_version, credential_expires_at
                    FROM remote_devices WHERE id = ?
                    """,
                    (device.id,),
                ) as cursor:
                    current = await cursor.fetchone()
                if (
                    current is None
                    or current["state"] != DeviceState.ACTIVE.value
                    or int(current["key_version"]) != device.key_version
                    or datetime.fromisoformat(current["credential_expires_at"]) <= created_at
                ):
                    raise RuntimeError("device changed before session creation")
                await connection.execute(
                    """
                    INSERT INTO remote_sessions (
                        id, token_sha256, device_id, key_version, audience, scopes_json,
                        created_at, expires_at, last_seen_at, revoked_at, revoke_reason,
                        session_kind, csrf_token_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        session_id,
                        token_sha256,
                        device.id,
                        device.key_version,
                        audience,
                        _dump_scopes(scopes),
                        _timestamp(created_at),
                        _timestamp(expires_at),
                        session_kind.value,
                        csrf_token_sha256,
                    ),
                )
                await self._insert_audit(
                    connection,
                    event_type="session.created",
                    outcome=RemoteAuditOutcome.SUCCEEDED,
                    reason_code=(
                        "browser_device_signature_verified"
                        if session_kind is RemoteSessionKind.BROWSER
                        else "device_signature_verified"
                    ),
                    device_id=device.id,
                    session_id=session_id,
                    created_at=created_at,
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise

    async def get_session_by_token_sha256(self, token_sha256: str) -> StoredSession | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                "SELECT * FROM remote_sessions WHERE token_sha256 = ?", (token_sha256,)
            ) as cursor:
                row = await cursor.fetchone()
        return None if row is None else _stored_session(row)

    async def touch_session(self, *, session_id: str, device_id: str, seen_at: datetime) -> bool:
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = await connection.execute(
                    """
                    UPDATE remote_sessions SET last_seen_at = ?
                    WHERE id = ? AND device_id = ? AND revoked_at IS NULL AND expires_at > ?
                    """,
                    (_timestamp(seen_at), session_id, device_id, _timestamp(seen_at)),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    return False
                await connection.execute(
                    "UPDATE remote_devices SET last_seen_at = ? WHERE id = ?",
                    (_timestamp(seen_at), device_id),
                )
                await connection.commit()
                return True
            except BaseException:
                await connection.rollback()
                raise

    async def consume_nonce(
        self,
        *,
        device_id: str,
        session_id: str | None,
        nonce: str,
        seen_at: datetime,
        expires_at: datetime,
    ) -> bool:
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                await connection.execute(
                    "DELETE FROM remote_nonces WHERE expires_at <= ?", (_timestamp(seen_at),)
                )
                try:
                    await connection.execute(
                        """
                        INSERT INTO remote_nonces (device_id, nonce, seen_at, expires_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            device_id,
                            nonce,
                            _timestamp(seen_at),
                            _timestamp(expires_at),
                        ),
                    )
                except aiosqlite.IntegrityError:
                    await self._insert_audit(
                        connection,
                        event_type="request.denied",
                        outcome=RemoteAuditOutcome.DENIED,
                        reason_code="replayed_nonce",
                        device_id=device_id,
                        session_id=session_id,
                        created_at=seen_at,
                    )
                    await self._prune_denials(connection, device_id=device_id)
                    await connection.commit()
                    return False
                await connection.execute(
                    "UPDATE remote_devices SET last_seen_at = ? WHERE id = ?",
                    (_timestamp(seen_at), device_id),
                )
                if session_id is not None:
                    await connection.execute(
                        "UPDATE remote_sessions SET last_seen_at = ? WHERE id = ?",
                        (_timestamp(seen_at), session_id),
                    )
                await connection.commit()
                return True
            except BaseException:
                await connection.rollback()
                raise

    async def rotate_device_key(
        self,
        *,
        device_id: str,
        expected_key_version: int,
        new_public_key: str,
        new_fingerprint: str,
        rotated_at: datetime,
        credential_expires_at: datetime,
    ) -> DeviceRecord | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = await connection.execute(
                    """
                    UPDATE remote_devices
                    SET public_key = ?, key_fingerprint = ?, key_version = key_version + 1,
                        credential_expires_at = ?, last_seen_at = ?
                    WHERE id = ? AND key_version = ? AND state = 'active'
                    """,
                    (
                        new_public_key,
                        new_fingerprint,
                        _timestamp(credential_expires_at),
                        _timestamp(rotated_at),
                        device_id,
                        expected_key_version,
                    ),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    return None
                await connection.execute(
                    """
                    UPDATE remote_sessions SET revoked_at = ?, revoke_reason = 'key_rotated'
                    WHERE device_id = ? AND revoked_at IS NULL
                    """,
                    (_timestamp(rotated_at), device_id),
                )
                await self._insert_audit(
                    connection,
                    event_type="device.key_rotated",
                    outcome=RemoteAuditOutcome.SUCCEEDED,
                    reason_code="old_and_new_proof_verified",
                    device_id=device_id,
                    created_at=rotated_at,
                )
                await connection.commit()
                async with connection.execute(
                    "SELECT * FROM remote_devices WHERE id = ?", (device_id,)
                ) as result_cursor:
                    row = await result_cursor.fetchone()
                return None if row is None else _stored_device(row).record
            except aiosqlite.IntegrityError:
                await connection.rollback()
                return None
            except BaseException:
                await connection.rollback()
                raise

    async def revoke_device(self, *, device_id: str, host_id: str, revoked_at: datetime) -> bool:
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = await connection.execute(
                    """
                    UPDATE remote_devices SET state = 'revoked', revoked_at = ?
                    WHERE id = ? AND host_id = ? AND state != 'revoked'
                    """,
                    (_timestamp(revoked_at), device_id, host_id),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    return False
                await connection.execute(
                    """
                    UPDATE remote_sessions SET revoked_at = ?, revoke_reason = 'device_revoked'
                    WHERE device_id = ? AND revoked_at IS NULL
                    """,
                    (_timestamp(revoked_at), device_id),
                )
                await self._insert_audit(
                    connection,
                    event_type="device.revoked",
                    outcome=RemoteAuditOutcome.SUCCEEDED,
                    reason_code="local_host_revoked",
                    device_id=device_id,
                    created_at=revoked_at,
                )
                await connection.commit()
                return True
            except BaseException:
                await connection.rollback()
                raise

    async def revoke_session(
        self, *, session_id: str, device_id: str, revoked_at: datetime
    ) -> bool:
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = await connection.execute(
                    """
                    UPDATE remote_sessions SET revoked_at = ?, revoke_reason = 'device_logout'
                    WHERE id = ? AND device_id = ? AND revoked_at IS NULL
                    """,
                    (_timestamp(revoked_at), session_id, device_id),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    return False
                await self._insert_audit(
                    connection,
                    event_type="session.revoked",
                    outcome=RemoteAuditOutcome.SUCCEEDED,
                    reason_code="device_logout",
                    device_id=device_id,
                    session_id=session_id,
                    created_at=revoked_at,
                )
                await connection.commit()
                return True
            except BaseException:
                await connection.rollback()
                raise

    async def append_denial(
        self,
        *,
        reason_code: str,
        created_at: datetime,
        device_id: str | None = None,
        session_id: str | None = None,
        enrollment_id: str | None = None,
    ) -> None:
        async with self._operation_lock:
            connection = await self._get_connection()
            await self._insert_audit(
                connection,
                event_type="request.denied",
                outcome=RemoteAuditOutcome.DENIED,
                reason_code=reason_code,
                device_id=device_id,
                session_id=session_id,
                enrollment_id=enrollment_id,
                created_at=created_at,
            )
            await self._prune_denials(
                connection,
                device_id=device_id,
                enrollment_id=enrollment_id,
            )
            await connection.commit()

    async def list_audit_events(
        self,
        *,
        device_id: str,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[RemoteAuditEvent, ...]:
        if after_sequence < 0 or not 1 <= limit <= 500:
            raise ValueError("invalid audit cursor or limit")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT * FROM remote_audit_events
                WHERE device_id = ? AND sequence > ?
                ORDER BY sequence LIMIT ?
                """,
                (device_id, after_sequence, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return tuple(_audit_event(row) for row in rows)

    async def _get_connection(self) -> aiosqlite.Connection:
        await self.initialize()
        connection = self._connection
        if connection is None:
            raise RuntimeError("remote identity store is not initialized")
        return connection

    @staticmethod
    async def _insert_audit(
        connection: aiosqlite.Connection,
        *,
        event_type: str,
        outcome: RemoteAuditOutcome,
        reason_code: str,
        created_at: datetime,
        device_id: str | None = None,
        session_id: str | None = None,
        enrollment_id: str | None = None,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO remote_audit_events (
                id, event_type, outcome, reason_code, device_id, session_id,
                enrollment_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                event_type,
                outcome.value,
                reason_code,
                device_id,
                session_id,
                enrollment_id,
                _timestamp(created_at),
            ),
        )

    @staticmethod
    async def _prune_denials(
        connection: aiosqlite.Connection,
        *,
        device_id: str | None = None,
        enrollment_id: str | None = None,
    ) -> None:
        if device_id is not None:
            await connection.execute(
                """
                DELETE FROM remote_audit_events
                WHERE event_type = 'request.denied' AND device_id = ?
                  AND sequence NOT IN (
                    SELECT sequence FROM remote_audit_events
                    WHERE event_type = 'request.denied' AND device_id = ?
                    ORDER BY sequence DESC LIMIT ?
                  )
                """,
                (device_id, device_id, _MAX_DENIAL_AUDIT_EVENTS),
            )
        elif enrollment_id is not None:
            await connection.execute(
                """
                DELETE FROM remote_audit_events
                WHERE event_type = 'request.denied' AND enrollment_id = ?
                  AND sequence NOT IN (
                    SELECT sequence FROM remote_audit_events
                    WHERE event_type = 'request.denied' AND enrollment_id = ?
                    ORDER BY sequence DESC LIMIT ?
                  )
                """,
                (enrollment_id, enrollment_id, _MAX_DENIAL_AUDIT_EVENTS),
            )


def _stored_enrollment(row: aiosqlite.Row) -> StoredEnrollment:
    return StoredEnrollment(
        id=str(row["id"]),
        challenge_sha256=str(row["challenge_sha256"]),
        host_id=str(row["host_id"]),
        display_name=str(row["display_name"]),
        device_type=DeviceType(row["device_type"]),
        approved_scopes=_load_scopes(row["scopes_json"]),
        risk_ceiling=int(row["risk_ceiling"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        consumed_at=(
            None if row["consumed_at"] is None else datetime.fromisoformat(row["consumed_at"])
        ),
    )


def _stored_device(row: aiosqlite.Row) -> StoredDevice:
    return StoredDevice(
        record=DeviceRecord(
            id=str(row["id"]),
            host_id=str(row["host_id"]),
            display_name=str(row["display_name"]),
            device_type=DeviceType(row["device_type"]),
            key_fingerprint=str(row["key_fingerprint"]),
            key_version=int(row["key_version"]),
            approved_scopes=_load_scopes(row["scopes_json"]),
            risk_ceiling=int(row["risk_ceiling"]),
            protocol_version=str(row["protocol_version"]),
            state=DeviceState(row["state"]),
            enrolled_at=datetime.fromisoformat(row["enrolled_at"]),
            credential_expires_at=datetime.fromisoformat(row["credential_expires_at"]),
            last_seen_at=(
                None if row["last_seen_at"] is None else datetime.fromisoformat(row["last_seen_at"])
            ),
            revoked_at=(
                None if row["revoked_at"] is None else datetime.fromisoformat(row["revoked_at"])
            ),
        ),
        public_key=str(row["public_key"]),
    )


def _stored_session(row: aiosqlite.Row) -> StoredSession:
    return StoredSession(
        id=str(row["id"]),
        token_sha256=str(row["token_sha256"]),
        device_id=str(row["device_id"]),
        key_version=int(row["key_version"]),
        audience=str(row["audience"]),
        scopes=_load_scopes(row["scopes_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        revoked_at=(
            None if row["revoked_at"] is None else datetime.fromisoformat(row["revoked_at"])
        ),
        session_kind=RemoteSessionKind(row["session_kind"]),
        csrf_token_sha256=(
            None if row["csrf_token_sha256"] is None else str(row["csrf_token_sha256"])
        ),
    )


def _audit_event(row: aiosqlite.Row) -> RemoteAuditEvent:
    return RemoteAuditEvent(
        sequence=int(row["sequence"]),
        id=str(row["id"]),
        event_type=str(row["event_type"]),
        outcome=RemoteAuditOutcome(row["outcome"]),
        reason_code=str(row["reason_code"]),
        device_id=row["device_id"],
        session_id=row["session_id"],
        enrollment_id=row["enrollment_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _dump_scopes(scopes: tuple[RemoteScope, ...]) -> str:
    return json.dumps(sorted(scope.value for scope in scopes), separators=(",", ":"))


def _load_scopes(value: str) -> tuple[RemoteScope, ...]:
    loaded = json.loads(value)
    if not isinstance(loaded, list) or not all(isinstance(item, str) for item in loaded):
        raise RuntimeError("invalid remote scope record")
    scopes = tuple(RemoteScope(item) for item in loaded)
    if len(scopes) != len(set(scopes)):
        raise RuntimeError("duplicate remote scope record")
    return scopes


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")
