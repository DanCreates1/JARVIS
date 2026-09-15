"""Transactional single-owner Phase 11B runner state and local inbox."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiosqlite
from pydantic import ValidationError

from jarvis.memory.sqlite_store import SQLiteConversationStore
from jarvis.planning import TaskRecord, TaskStatus

from .runner_models import (
    CandidateDispatch,
    DispatchState,
    LocalNotification,
    NotificationState,
    RunnerEvent,
    RunnerEventType,
)


class ProactivityRunnerStoreError(RuntimeError):
    pass


class RunnerNotFoundError(ProactivityRunnerStoreError):
    pass


class RunnerConflictError(ProactivityRunnerStoreError):
    pass


class RunnerStateError(ProactivityRunnerStoreError):
    pass


class RunnerCorruptionError(ProactivityRunnerStoreError):
    pass


class SQLiteProactivityRunnerStore:
    def __init__(self, database_path: str | Path, *, busy_timeout_ms: int = 5_000) -> None:
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
                async with connection.execute("PRAGMA quick_check") as cursor:
                    row = await cursor.fetchone()
                if row is None or row[0] != "ok":
                    raise RunnerCorruptionError("SQLite quick_check failed")
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

    async def __aenter__(self) -> SQLiteProactivityRunnerStore:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    async def claim_next(
        self,
        *,
        host_id: str,
        runner_id: str,
        lease_seconds: int,
        notification_ttl_seconds: int,
        now: datetime | None = None,
    ) -> tuple[CandidateDispatch | None, bool]:
        if not runner_id.strip() or len(runner_id) > 200:
            raise ValueError("runner ID must be nonblank and at most 200 characters")
        if not 1 <= lease_seconds <= 60:
            raise ValueError("runner lease must be 1 through 60 seconds")
        if not 60 <= notification_ttl_seconds <= 86_400:
            raise ValueError("notification TTL must be 60 through 86400 seconds")
        timestamp = _aware(now or datetime.now(UTC))
        encoded_now = _encode(timestamp)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await self._close_stale_locked(connection, host_id=host_id, timestamp=timestamp)
                row = await _fetchone(
                    connection,
                    """
                    SELECT c.id AS candidate_id, c.host_id, c.rule_id, c.created_at,
                           c.expires_at AS candidate_expires_at,
                           r.expires_at AS rule_expires_at,
                           d.state, d.version, d.attempts, d.expires_at AS dispatch_expires_at
                    FROM proactivity_candidates AS c
                    JOIN proactivity_rules AS r
                      ON r.id = c.rule_id AND r.host_id = c.host_id
                    LEFT JOIN proactivity_dispatches AS d ON d.candidate_id = c.id
                    WHERE c.host_id = ? AND r.status = 'active' AND r.expires_at > ? AND (
                        (d.candidate_id IS NULL AND c.expires_at > ?) OR
                        (d.state = 'claimed' AND d.lease_expires_at <= ?
                         AND d.attempts < 10 AND d.expires_at > ?) OR
                        (d.state = 'snoozed' AND d.snoozed_until <= ? AND d.attempts < 10
                         AND d.expires_at > ?)
                    )
                    ORDER BY c.created_at, c.id
                    LIMIT 1
                    """,
                    (
                        host_id,
                        encoded_now,
                        encoded_now,
                        encoded_now,
                        encoded_now,
                        encoded_now,
                        encoded_now,
                    ),
                )
                if row is None:
                    await connection.commit()
                    return None, False
                lease_id = f"proactivity-lease:{uuid4()}"
                lease_expires = timestamp + timedelta(seconds=lease_seconds)
                recovered = row["state"] == DispatchState.CLAIMED.value
                if row["state"] is None:
                    expires_at = min(
                        datetime.fromisoformat(row["candidate_expires_at"]),
                        datetime.fromisoformat(row["rule_expires_at"]),
                        timestamp + timedelta(seconds=notification_ttl_seconds),
                    )
                    await connection.execute(
                        """
                        INSERT INTO proactivity_dispatches
                            (candidate_id, host_id, rule_id, state, version, attempts,
                             lease_id, lease_expires_at, expires_at, created_at, updated_at)
                        VALUES (?, ?, ?, 'claimed', 1, 1, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["candidate_id"],
                            row["host_id"],
                            row["rule_id"],
                            lease_id,
                            _encode(lease_expires),
                            _encode(expires_at),
                            encoded_now,
                            encoded_now,
                        ),
                    )
                    event_type = RunnerEventType.CANDIDATE_CLAIMED
                    reason = "foreground_single_owner_claim"
                else:
                    cursor = await connection.execute(
                        """
                        UPDATE proactivity_dispatches
                        SET state = 'claimed', version = version + 1, attempts = attempts + 1,
                            lease_id = ?, lease_expires_at = ?, snoozed_until = NULL,
                            failure_code = NULL, updated_at = ?
                        WHERE candidate_id = ? AND host_id = ? AND version = ?
                        """,
                        (
                            lease_id,
                            _encode(lease_expires),
                            encoded_now,
                            row["candidate_id"],
                            host_id,
                            row["version"],
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise RunnerConflictError("candidate dispatch changed")
                    event_type = (
                        RunnerEventType.LEASE_RECOVERED
                        if recovered
                        else RunnerEventType.CANDIDATE_CLAIMED
                    )
                    reason = (
                        "expired_lease_recovered"
                        if recovered
                        else "snooze_elapsed_foreground_claim"
                    )
                await self._append_event(
                    connection,
                    host_id=host_id,
                    rule_id=row["rule_id"],
                    candidate_id=row["candidate_id"],
                    event_type=event_type,
                    reason_code=reason,
                    created_at=timestamp,
                )
                await connection.commit()
                dispatch = await self._load_dispatch(row["candidate_id"], host_id=host_id)
            except BaseException:
                await connection.rollback()
                raise
        return dispatch, recovered

    async def complete_local_notification(
        self,
        *,
        host_id: str,
        candidate_id: str,
        lease_id: str,
        now: datetime | None = None,
    ) -> CandidateDispatch:
        timestamp = _aware(now or datetime.now(UTC))
        encoded_now = _encode(timestamp)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                row = await _fetchone(
                    connection,
                    """
                    SELECT d.*, c.feature
                    FROM proactivity_dispatches AS d
                    JOIN proactivity_candidates AS c ON c.id = d.candidate_id
                    WHERE d.host_id = ? AND d.candidate_id = ?
                    """,
                    (host_id, candidate_id),
                )
                if row is None:
                    raise RunnerNotFoundError("candidate dispatch not found")
                if row["state"] != DispatchState.CLAIMED.value or row["lease_id"] != lease_id:
                    raise RunnerConflictError("candidate lease is not owned")
                if datetime.fromisoformat(row["lease_expires_at"]) <= timestamp:
                    raise RunnerStateError("candidate lease expired")
                if datetime.fromisoformat(row["expires_at"]) <= timestamp:
                    await self._expire_locked(connection, row, timestamp=timestamp)
                    await connection.commit()
                    raise RunnerStateError("candidate notification expired")
                notification_id = row["notification_id"] or f"proactivity-notice:{uuid4()}"
                resurfaced = row["notification_id"] is not None
                await connection.execute(
                    """
                    INSERT INTO proactivity_notifications
                        (id, host_id, rule_id, candidate_id, feature, state,
                         available_at, expires_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                    ON CONFLICT(candidate_id) DO UPDATE SET
                        state = 'active', available_at = excluded.available_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        notification_id,
                        host_id,
                        row["rule_id"],
                        candidate_id,
                        row["feature"],
                        encoded_now,
                        row["expires_at"],
                        encoded_now,
                        encoded_now,
                    ),
                )
                ownership_cursor = await connection.execute(
                    """
                    INSERT OR IGNORE INTO proactivity_ownerships
                        (candidate_id, host_id, rule_id, owner_kind, owner_id,
                         owner_device_id, version, lease_expires_at, created_at, updated_at)
                    VALUES (?, ?, ?, 'local_host', ?, NULL, 1, NULL, ?, ?)
                    """,
                    (
                        candidate_id,
                        host_id,
                        row["rule_id"],
                        host_id,
                        encoded_now,
                        encoded_now,
                    ),
                )
                if ownership_cursor.rowcount == 1:
                    await connection.execute(
                        """
                        INSERT INTO proactivity_ownership_events
                            (id, host_id, candidate_id, event_type, reason_code,
                             owner_kind, owner_device_id, version, created_at)
                        VALUES (?, ?, ?, 'local_owner_created',
                                'generic_local_notification_owner',
                                'local_host', NULL, 1, ?)
                        """,
                        (
                            f"proactivity-owner-event:{uuid4()}",
                            host_id,
                            candidate_id,
                            encoded_now,
                        ),
                    )
                cursor = await connection.execute(
                    """
                    UPDATE proactivity_dispatches
                    SET state = 'notified', version = version + 1, lease_id = NULL,
                        lease_expires_at = NULL, notification_id = ?, updated_at = ?
                    WHERE host_id = ? AND candidate_id = ? AND lease_id = ?
                    """,
                    (notification_id, encoded_now, host_id, candidate_id, lease_id),
                )
                if cursor.rowcount != 1:
                    raise RunnerConflictError("candidate lease changed")
                await self._append_event(
                    connection,
                    host_id=host_id,
                    rule_id=row["rule_id"],
                    candidate_id=candidate_id,
                    event_type=(
                        RunnerEventType.NOTIFICATION_RESURFACED
                        if resurfaced
                        else RunnerEventType.NOTIFICATION_READY
                    ),
                    reason_code="generic_local_inbox_only",
                    created_at=timestamp,
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return await self.require_dispatch(host_id=host_id, candidate_id=candidate_id)

    async def snooze(
        self,
        *,
        host_id: str,
        candidate_id: str,
        expected_version: int,
        until: datetime,
        max_snooze_seconds: int,
        now: datetime | None = None,
    ) -> CandidateDispatch:
        timestamp = _aware(now or datetime.now(UTC))
        wake = _aware(until)
        if not 60 <= max_snooze_seconds <= 86_400:
            raise ValueError("maximum snooze must be 60 through 86400 seconds")
        if wake < timestamp + timedelta(seconds=60):
            raise RunnerStateError("snooze must be at least 60 seconds")
        if wake > timestamp + timedelta(seconds=max_snooze_seconds):
            raise RunnerStateError("snooze exceeds host ceiling")
        return await self._transition(
            host_id=host_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            allowed={DispatchState.CLAIMED, DispatchState.NOTIFIED},
            state=DispatchState.SNOOZED,
            notification_state=NotificationState.SNOOZED,
            event_type=RunnerEventType.SNOOZED,
            reason_code="trusted_local_snooze",
            now=timestamp,
            snoozed_until=wake,
        )

    async def dismiss(
        self, *, host_id: str, candidate_id: str, expected_version: int, now: datetime | None = None
    ) -> CandidateDispatch:
        return await self._transition(
            host_id=host_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            allowed={DispatchState.NOTIFIED, DispatchState.SNOOZED},
            state=DispatchState.DISMISSED,
            notification_state=NotificationState.DISMISSED,
            event_type=RunnerEventType.DISMISSED,
            reason_code="trusted_local_dismiss",
            now=_aware(now or datetime.now(UTC)),
        )

    async def cancel(
        self, *, host_id: str, candidate_id: str, expected_version: int, now: datetime | None = None
    ) -> CandidateDispatch:
        return await self._transition(
            host_id=host_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            allowed={DispatchState.CLAIMED, DispatchState.NOTIFIED, DispatchState.SNOOZED},
            state=DispatchState.CANCELLED,
            notification_state=NotificationState.CANCELLED,
            event_type=RunnerEventType.CANCELLED,
            reason_code="trusted_local_cancel",
            now=_aware(now or datetime.now(UTC)),
        )

    async def create_handoff(
        self,
        *,
        host_id: str,
        candidate_id: str,
        expected_version: int,
        task: TaskRecord,
        now: datetime | None = None,
    ) -> CandidateDispatch:
        timestamp = _aware(now or datetime.now(UTC))
        if task.graph.host_id != host_id:
            raise RunnerNotFoundError("task not found")
        if task.status not in {TaskStatus.PROPOSED, TaskStatus.READY}:
            raise RunnerStateError("task is not available for proactive handoff")
        if task.graph.deadline_at <= timestamp:
            raise RunnerStateError("task deadline expired")
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                current_task = await _fetchone(
                    connection,
                    """
                    SELECT record_json, version, status, plan_sha256
                    FROM planning_tasks WHERE host_id = ? AND id = ?
                    """,
                    (host_id, task.graph.id),
                )
                if current_task is None:
                    raise RunnerNotFoundError("task not found")
                if (
                    current_task["version"] != task.version
                    or current_task["plan_sha256"] != task.graph.plan_sha256
                    or current_task["status"] not in {"proposed", "ready"}
                ):
                    raise RunnerConflictError("task changed before handoff")
                row = await _fetchone(
                    connection,
                    "SELECT * FROM proactivity_dispatches WHERE host_id = ? AND candidate_id = ?",
                    (host_id, candidate_id),
                )
                if row is None:
                    raise RunnerNotFoundError("candidate dispatch not found")
                if row["version"] != expected_version:
                    raise RunnerConflictError("candidate dispatch changed")
                if row["state"] not in {"notified", "snoozed"}:
                    raise RunnerStateError("candidate cannot be handed off in its current state")
                if datetime.fromisoformat(row["expires_at"]) <= timestamp:
                    raise RunnerStateError("candidate notification expired")
                cursor = await connection.execute(
                    """
                    UPDATE proactivity_dispatches
                    SET state = 'handed_off', version = version + 1, task_id = ?,
                        task_version = ?, task_plan_sha256 = ?, snoozed_until = NULL,
                        updated_at = ?
                    WHERE host_id = ? AND candidate_id = ? AND version = ?
                    """,
                    (
                        task.graph.id,
                        task.version,
                        task.graph.plan_sha256,
                        _encode(timestamp),
                        host_id,
                        candidate_id,
                        expected_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RunnerConflictError("candidate dispatch changed")
                await connection.execute(
                    """
                    UPDATE proactivity_notifications
                    SET state = 'handed_off', updated_at = ?
                    WHERE host_id = ? AND candidate_id = ?
                    """,
                    (_encode(timestamp), host_id, candidate_id),
                )
                await self._append_event(
                    connection,
                    host_id=host_id,
                    rule_id=row["rule_id"],
                    candidate_id=candidate_id,
                    event_type=RunnerEventType.HANDOFF_CREATED,
                    reason_code="foreground_task_handoff_no_execution",
                    created_at=timestamp,
                )
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                await connection.rollback()
                raise RunnerConflictError("task or candidate already has a handoff") from exc
            except BaseException:
                await connection.rollback()
                raise
        return await self.require_dispatch(host_id=host_id, candidate_id=candidate_id)

    async def require_dispatch(self, *, host_id: str, candidate_id: str) -> CandidateDispatch:
        async with self._operation_lock:
            dispatch = await self._load_dispatch(candidate_id, host_id=host_id)
        if dispatch is None:
            raise RunnerNotFoundError("candidate dispatch not found")
        return dispatch

    async def list_notifications(
        self, *, host_id: str, active_only: bool = False, limit: int = 100
    ) -> Sequence[LocalNotification]:
        if not 1 <= limit <= 500:
            raise ValueError("notification limit must be between 1 and 500")
        sql = """
            SELECT n.*, d.version AS dispatch_version
            FROM proactivity_notifications AS n
            JOIN proactivity_dispatches AS d ON d.candidate_id = n.candidate_id
            WHERE n.host_id = ?
        """
        parameters: list[object] = [host_id]
        if active_only:
            sql += " AND n.state = 'active'"
        sql += " ORDER BY n.available_at DESC, n.id DESC LIMIT ?"
        parameters.append(limit)
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(sql, parameters) as cursor:
                rows = await cursor.fetchall()
        return tuple(_notification(row) for row in rows)

    async def list_events(
        self, *, host_id: str, candidate_id: str, limit: int = 500
    ) -> Sequence[RunnerEvent]:
        if not 1 <= limit <= 2_000:
            raise ValueError("runner event limit must be between 1 and 2000")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT * FROM proactivity_runner_events
                WHERE host_id = ? AND candidate_id = ? ORDER BY sequence LIMIT ?
                """,
                (host_id, candidate_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return tuple(RunnerEvent.model_validate(dict(row)) for row in rows)

    async def _transition(
        self,
        *,
        host_id: str,
        candidate_id: str,
        expected_version: int,
        allowed: set[DispatchState],
        state: DispatchState,
        notification_state: NotificationState,
        event_type: RunnerEventType,
        reason_code: str,
        now: datetime,
        snoozed_until: datetime | None = None,
    ) -> CandidateDispatch:
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                row = await _fetchone(
                    connection,
                    "SELECT * FROM proactivity_dispatches WHERE host_id = ? AND candidate_id = ?",
                    (host_id, candidate_id),
                )
                if row is None:
                    raise RunnerNotFoundError("candidate dispatch not found")
                if row["version"] != expected_version:
                    raise RunnerConflictError("candidate dispatch changed")
                if DispatchState(row["state"]) not in allowed:
                    raise RunnerStateError("candidate cannot transition from its current state")
                if snoozed_until is not None and snoozed_until >= datetime.fromisoformat(
                    row["expires_at"]
                ):
                    raise RunnerStateError("snooze must end before notification expiry")
                cursor = await connection.execute(
                    """
                    UPDATE proactivity_dispatches
                    SET state = ?, version = version + 1, lease_id = NULL,
                        lease_expires_at = NULL, snoozed_until = ?, updated_at = ?
                    WHERE host_id = ? AND candidate_id = ? AND version = ?
                    """,
                    (
                        state.value,
                        None if snoozed_until is None else _encode(snoozed_until),
                        _encode(now),
                        host_id,
                        candidate_id,
                        expected_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RunnerConflictError("candidate dispatch changed")
                await connection.execute(
                    """
                    UPDATE proactivity_notifications
                    SET state = ?, updated_at = ?
                    WHERE host_id = ? AND candidate_id = ?
                    """,
                    (notification_state.value, _encode(now), host_id, candidate_id),
                )
                await self._append_event(
                    connection,
                    host_id=host_id,
                    rule_id=row["rule_id"],
                    candidate_id=candidate_id,
                    event_type=event_type,
                    reason_code=reason_code,
                    created_at=now,
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return await self.require_dispatch(host_id=host_id, candidate_id=candidate_id)

    async def _expire_locked(
        self, connection: aiosqlite.Connection, row: aiosqlite.Row, *, timestamp: datetime
    ) -> None:
        await connection.execute(
            """
            UPDATE proactivity_dispatches
            SET state = 'expired', version = version + 1, lease_id = NULL,
                lease_expires_at = NULL, updated_at = ? WHERE candidate_id = ?
            """,
            (_encode(timestamp), row["candidate_id"]),
        )
        await connection.execute(
            """
            UPDATE proactivity_notifications SET state = 'expired', updated_at = ?
            WHERE candidate_id = ?
            """,
            (_encode(timestamp), row["candidate_id"]),
        )
        await self._append_event(
            connection,
            host_id=row["host_id"],
            rule_id=row["rule_id"],
            candidate_id=row["candidate_id"],
            event_type=RunnerEventType.EXPIRED,
            reason_code="notification_lifetime_elapsed",
            created_at=timestamp,
        )

    async def _close_stale_locked(
        self,
        connection: aiosqlite.Connection,
        *,
        host_id: str,
        timestamp: datetime,
        limit: int = 100,
    ) -> None:
        """Bound cleanup work so every foreground tick has a finite recovery pass."""
        encoded_now = _encode(timestamp)
        async with connection.execute(
            """
            SELECT * FROM proactivity_dispatches
            WHERE host_id = ? AND (
                (state IN ('claimed', 'notified', 'snoozed') AND expires_at <= ?) OR
                (state = 'claimed' AND attempts >= 10 AND lease_expires_at <= ?) OR
                (state = 'snoozed' AND attempts >= 10 AND snoozed_until <= ?)
            )
            ORDER BY updated_at, candidate_id
            LIMIT ?
            """,
            (host_id, encoded_now, encoded_now, encoded_now, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            exhausted = (
                row["state"] in {DispatchState.CLAIMED.value, DispatchState.SNOOZED.value}
                and row["attempts"] >= 10
                and datetime.fromisoformat(row["lease_expires_at"] or row["snoozed_until"])
                <= timestamp
                and datetime.fromisoformat(row["expires_at"]) > timestamp
            )
            if exhausted:
                await connection.execute(
                    """
                    UPDATE proactivity_dispatches
                    SET state = 'failed', version = version + 1, lease_id = NULL,
                        lease_expires_at = NULL, failure_code = 'lease_attempts_exhausted',
                        updated_at = ? WHERE candidate_id = ?
                    """,
                    (encoded_now, row["candidate_id"]),
                )
                await connection.execute(
                    """
                    UPDATE proactivity_notifications SET state = 'cancelled', updated_at = ?
                    WHERE candidate_id = ?
                    """,
                    (encoded_now, row["candidate_id"]),
                )
                await self._append_event(
                    connection,
                    host_id=row["host_id"],
                    rule_id=row["rule_id"],
                    candidate_id=row["candidate_id"],
                    event_type=RunnerEventType.DELIVERY_FAILED,
                    reason_code="lease_attempts_exhausted",
                    created_at=timestamp,
                )
            else:
                await self._expire_locked(connection, row, timestamp=timestamp)

    async def _load_dispatch(self, candidate_id: str, *, host_id: str) -> CandidateDispatch | None:
        connection = await self._get_connection()
        row = await _fetchone(
            connection,
            "SELECT * FROM proactivity_dispatches WHERE host_id = ? AND candidate_id = ?",
            (host_id, candidate_id),
        )
        return None if row is None else _dispatch(row)

    async def _get_connection(self) -> aiosqlite.Connection:
        await self.initialize()
        if self._connection is None:
            raise ProactivityRunnerStoreError("runner store is not initialized")
        return self._connection

    @staticmethod
    async def _append_event(
        connection: aiosqlite.Connection,
        *,
        host_id: str,
        rule_id: str,
        candidate_id: str,
        event_type: RunnerEventType,
        reason_code: str,
        created_at: datetime,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO proactivity_runner_events
                (id, host_id, rule_id, candidate_id, event_type, reason_code, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"proactivity-runner-event:{uuid4()}",
                host_id,
                rule_id,
                candidate_id,
                event_type.value,
                reason_code,
                _encode(created_at),
            ),
        )


async def _fetchone(
    connection: aiosqlite.Connection, sql: str, parameters: Sequence[object]
) -> aiosqlite.Row | None:
    async with connection.execute(sql, parameters) as cursor:
        return await cursor.fetchone()


def _dispatch(row: aiosqlite.Row) -> CandidateDispatch:
    try:
        return CandidateDispatch.model_validate(dict(row))
    except ValidationError as exc:
        raise RunnerCorruptionError("stored candidate dispatch is invalid") from exc


def _notification(row: aiosqlite.Row) -> LocalNotification:
    try:
        return LocalNotification.model_validate(dict(row))
    except ValidationError as exc:
        raise RunnerCorruptionError("stored local notification is invalid") from exc


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("runner store timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _encode(value: datetime) -> str:
    return _aware(value).isoformat(timespec="microseconds")
