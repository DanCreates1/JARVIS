"""Transactional Phase 11C device binding and single-owner coordination."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiosqlite
from pydantic import TypeAdapter, ValidationError

from jarvis.memory.sqlite_store import SQLiteConversationStore
from jarvis.remote.models import DeviceState, RemoteScope

from .device_models import (
    CandidateOwnership,
    DeviceBindingState,
    OwnershipEvent,
    OwnershipEventType,
    OwnershipKind,
    ProactivityAdapterControl,
    ProactivityDeviceBinding,
    VisibleProactivityState,
)
from .models import FeatureName

_FEATURE_ADAPTER = TypeAdapter(FeatureName)


class ProactivityDeviceStoreError(RuntimeError):
    pass


class DeviceOwnershipNotFoundError(ProactivityDeviceStoreError):
    pass


class DeviceOwnershipConflictError(ProactivityDeviceStoreError):
    pass


class DeviceOwnershipDeniedError(ProactivityDeviceStoreError):
    pass


class DeviceOwnershipCorruptionError(ProactivityDeviceStoreError):
    pass


class SQLiteProactivityDeviceStore:
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
                    raise DeviceOwnershipCorruptionError("SQLite quick_check failed")
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

    async def __aenter__(self) -> SQLiteProactivityDeviceStore:
        await self.initialize()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def get_control(self, *, host_id: str) -> ProactivityAdapterControl:
        async with self._operation_lock:
            connection = await self._get_connection()
            row = await _fetchone(
                connection,
                "SELECT * FROM proactivity_adapter_controls WHERE host_id = ?",
                (host_id,),
            )
        if row is None:
            return ProactivityAdapterControl(
                host_id=host_id,
                enabled=False,
                version=1,
                kill_generation=1,
                updated_at=datetime.fromtimestamp(0, UTC),
            )
        return _control(row)

    async def set_control(
        self, *, host_id: str, enabled: bool, now: datetime | None = None
    ) -> ProactivityAdapterControl:
        timestamp = _aware(now or datetime.now(UTC))
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                row = await _fetchone(
                    connection,
                    "SELECT * FROM proactivity_adapter_controls WHERE host_id = ?",
                    (host_id,),
                )
                if row is None:
                    await connection.execute(
                        """
                        INSERT INTO proactivity_adapter_controls
                            (host_id, enabled, version, kill_generation, updated_at)
                        VALUES (?, ?, 1, 1, ?)
                        """,
                        (host_id, int(enabled), _encode(timestamp)),
                    )
                else:
                    was_enabled = bool(row["enabled"])
                    await connection.execute(
                        """
                        UPDATE proactivity_adapter_controls
                        SET enabled = ?, version = version + 1,
                            kill_generation = kill_generation + ?, updated_at = ?
                        WHERE host_id = ?
                        """,
                        (
                            int(enabled),
                            int(was_enabled and not enabled),
                            _encode(timestamp),
                            host_id,
                        ),
                    )
                if not enabled:
                    await self._reclaim_matching_locked(
                        connection,
                        host_id=host_id,
                        timestamp=timestamp,
                        event_type=OwnershipEventType.ADAPTER_DISABLED,
                        reason_code="trusted_local_adapter_kill",
                    )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return await self.get_control(host_id=host_id)

    async def bind_device(
        self,
        *,
        host_id: str,
        device_id: str,
        feature: str,
        allow_manage: bool,
        expires_at: datetime,
        now: datetime | None = None,
    ) -> ProactivityDeviceBinding:
        timestamp = _aware(now or datetime.now(UTC))
        expiry = _aware(expires_at)
        feature = _FEATURE_ADAPTER.validate_python(feature)
        if expiry < timestamp + timedelta(minutes=1) or expiry > timestamp + timedelta(days=30):
            raise ValueError("device binding lifetime must be 1 minute through 30 days")
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await self._require_device_locked(
                    connection,
                    host_id=host_id,
                    device_id=device_id,
                    require_manage=allow_manage,
                    timestamp=timestamp,
                )
                current = await _fetchone(
                    connection,
                    """
                    SELECT * FROM proactivity_device_bindings
                    WHERE host_id = ? AND device_id = ? AND feature = ?
                    """,
                    (host_id, device_id, feature),
                )
                if current is None:
                    await connection.execute(
                        """
                        INSERT INTO proactivity_device_bindings
                            (host_id, device_id, feature, allow_manage, state, version,
                             expires_at, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 'active', 1, ?, ?, ?)
                        """,
                        (
                            host_id,
                            device_id,
                            feature,
                            int(allow_manage),
                            _encode(expiry),
                            _encode(timestamp),
                            _encode(timestamp),
                        ),
                    )
                else:
                    await connection.execute(
                        """
                        UPDATE proactivity_device_bindings
                        SET allow_manage = ?, state = 'active', version = version + 1,
                            expires_at = ?, updated_at = ?
                        WHERE host_id = ? AND device_id = ? AND feature = ?
                        """,
                        (
                            int(allow_manage),
                            _encode(expiry),
                            _encode(timestamp),
                            host_id,
                            device_id,
                            feature,
                        ),
                    )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return await self.require_binding(host_id=host_id, device_id=device_id, feature=feature)

    async def revoke_binding(
        self,
        *,
        host_id: str,
        device_id: str,
        feature: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> ProactivityDeviceBinding:
        timestamp = _aware(now or datetime.now(UTC))
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                cursor = await connection.execute(
                    """
                    UPDATE proactivity_device_bindings
                    SET state = 'revoked', version = version + 1, updated_at = ?
                    WHERE host_id = ? AND device_id = ? AND feature = ?
                      AND version = ? AND state = 'active'
                    """,
                    (_encode(timestamp), host_id, device_id, feature, expected_version),
                )
                if cursor.rowcount != 1:
                    raise DeviceOwnershipConflictError("device binding changed or is inactive")
                await self._reclaim_matching_locked(
                    connection,
                    host_id=host_id,
                    timestamp=timestamp,
                    event_type=OwnershipEventType.BINDING_REVOKED,
                    reason_code="trusted_local_binding_revoked",
                    device_id=device_id,
                    feature=feature,
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return await self.require_binding(host_id=host_id, device_id=device_id, feature=feature)

    async def require_binding(
        self, *, host_id: str, device_id: str, feature: str
    ) -> ProactivityDeviceBinding:
        async with self._operation_lock:
            connection = await self._get_connection()
            row = await _fetchone(
                connection,
                """
                SELECT * FROM proactivity_device_bindings
                WHERE host_id = ? AND device_id = ? AND feature = ?
                """,
                (host_id, device_id, feature),
            )
        if row is None:
            raise DeviceOwnershipNotFoundError("device binding not found")
        return _binding(row)

    async def list_bindings(
        self, *, host_id: str, device_id: str | None = None, limit: int = 500
    ) -> Sequence[ProactivityDeviceBinding]:
        if not 1 <= limit <= 500:
            raise ValueError("binding limit must be between 1 and 500")
        sql = "SELECT * FROM proactivity_device_bindings WHERE host_id = ?"
        values: list[object] = [host_id]
        if device_id is not None:
            sql += " AND device_id = ?"
            values.append(device_id)
        sql += " ORDER BY device_id, feature LIMIT ?"
        values.append(limit)
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(sql, values) as cursor:
                rows = await cursor.fetchall()
        return tuple(_binding(row) for row in rows)

    async def list_visible(
        self,
        *,
        host_id: str,
        device_id: str,
        now: datetime | None = None,
        limit: int = 100,
        allowed_features: frozenset[str] | None = None,
    ) -> Sequence[VisibleProactivityState]:
        if not 1 <= limit <= 100:
            raise ValueError("visible state limit must be between 1 and 100")
        timestamp = _aware(now or datetime.now(UTC))
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await self._require_control_locked(connection, host_id=host_id)
                await self._require_device_locked(
                    connection,
                    host_id=host_id,
                    device_id=device_id,
                    require_manage=False,
                    timestamp=timestamp,
                )
                await self._expire_locked(connection, host_id=host_id, timestamp=timestamp)
                sql = """
                    SELECT o.*, c.feature, d.state AS dispatch_state,
                           n.state AS notification_state, n.available_at, n.expires_at
                    FROM proactivity_ownerships AS o
                    JOIN proactivity_candidates AS c ON c.id = o.candidate_id
                    JOIN proactivity_dispatches AS d ON d.candidate_id = o.candidate_id
                    JOIN proactivity_notifications AS n ON n.candidate_id = o.candidate_id
                    JOIN proactivity_device_bindings AS b
                      ON b.host_id = o.host_id AND b.device_id = ? AND b.feature = c.feature
                    WHERE o.host_id = ? AND b.state = 'active' AND b.expires_at > ?
                      AND n.state IN ('active', 'snoozed') AND n.expires_at > ?
                """
                values: list[object] = [
                    device_id,
                    host_id,
                    _encode(timestamp),
                    _encode(timestamp),
                ]
                if allowed_features is not None:
                    if not allowed_features:
                        await connection.commit()
                        return ()
                    ordered_features = sorted(allowed_features)
                    placeholders = ",".join("?" for _ in ordered_features)
                    sql += f" AND c.feature IN ({placeholders})"
                    values.extend(ordered_features)
                sql += " ORDER BY n.available_at DESC, o.candidate_id LIMIT ?"
                values.append(limit)
                async with connection.execute(sql, values) as cursor:
                    rows = await cursor.fetchall()
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return tuple(_visible(row, device_id=device_id) for row in rows)

    async def claim(
        self,
        *,
        host_id: str,
        device_id: str,
        candidate_id: str,
        expected_version: int,
        lease_seconds: int,
        now: datetime | None = None,
        allowed_features: frozenset[str] | None = None,
    ) -> CandidateOwnership:
        return await self._device_transition(
            host_id=host_id,
            device_id=device_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            lease_seconds=lease_seconds,
            event_type=OwnershipEventType.DEVICE_CLAIMED,
            reason_code="scoped_device_claim",
            mode="claim",
            now=now,
            allowed_features=allowed_features,
        )

    async def renew(
        self,
        *,
        host_id: str,
        device_id: str,
        candidate_id: str,
        expected_version: int,
        lease_seconds: int,
        now: datetime | None = None,
        allowed_features: frozenset[str] | None = None,
    ) -> CandidateOwnership:
        return await self._device_transition(
            host_id=host_id,
            device_id=device_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            lease_seconds=lease_seconds,
            event_type=OwnershipEventType.DEVICE_RENEWED,
            reason_code="scoped_device_lease_renewed",
            mode="renew",
            now=now,
            allowed_features=allowed_features,
        )

    async def release(
        self,
        *,
        host_id: str,
        device_id: str,
        candidate_id: str,
        expected_version: int,
        now: datetime | None = None,
        allowed_features: frozenset[str] | None = None,
    ) -> CandidateOwnership:
        return await self._device_transition(
            host_id=host_id,
            device_id=device_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            lease_seconds=None,
            event_type=OwnershipEventType.DEVICE_RELEASED,
            reason_code="scoped_device_release_to_local",
            mode="release",
            now=now,
            allowed_features=allowed_features,
        )

    async def handoff(
        self,
        *,
        host_id: str,
        device_id: str,
        target_device_id: str,
        candidate_id: str,
        expected_version: int,
        lease_seconds: int,
        now: datetime | None = None,
        allowed_features: frozenset[str] | None = None,
    ) -> CandidateOwnership:
        if target_device_id == device_id:
            raise DeviceOwnershipDeniedError("handoff target must differ from current owner")
        return await self._device_transition(
            host_id=host_id,
            device_id=device_id,
            target_device_id=target_device_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            lease_seconds=lease_seconds,
            event_type=OwnershipEventType.DEVICE_HANDOFF,
            reason_code="scoped_exact_device_handoff",
            mode="handoff",
            now=now,
            allowed_features=allowed_features,
        )

    async def local_handoff(
        self,
        *,
        host_id: str,
        target_device_id: str,
        candidate_id: str,
        expected_version: int,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> CandidateOwnership:
        return await self._device_transition(
            host_id=host_id,
            device_id=host_id,
            target_device_id=target_device_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            lease_seconds=lease_seconds,
            event_type=OwnershipEventType.DEVICE_HANDOFF,
            reason_code="trusted_local_exact_device_handoff",
            mode="local_handoff",
            now=now,
        )

    async def local_reclaim(
        self,
        *,
        host_id: str,
        candidate_id: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> CandidateOwnership:
        timestamp = _aware(now or datetime.now(UTC))
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                row = await self._ownership_row_locked(
                    connection, host_id=host_id, candidate_id=candidate_id
                )
                if row["version"] != expected_version:
                    raise DeviceOwnershipConflictError("candidate ownership changed")
                if row["owner_kind"] != OwnershipKind.DEVICE.value:
                    raise DeviceOwnershipDeniedError("candidate is already locally owned")
                updated = await self._set_local_locked(
                    connection,
                    row=row,
                    timestamp=timestamp,
                    event_type=OwnershipEventType.LOCAL_RECLAIMED,
                    reason_code="trusted_local_reclaim",
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return updated

    async def list_ownerships(
        self, *, host_id: str, now: datetime | None = None, limit: int = 500
    ) -> Sequence[CandidateOwnership]:
        if not 1 <= limit <= 500:
            raise ValueError("ownership limit must be between 1 and 500")
        timestamp = _aware(now or datetime.now(UTC))
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await self._expire_locked(connection, host_id=host_id, timestamp=timestamp)
                async with connection.execute(
                    """
                    SELECT * FROM proactivity_ownerships
                    WHERE host_id = ? ORDER BY updated_at DESC, candidate_id LIMIT ?
                    """,
                    (host_id, limit),
                ) as cursor:
                    rows = await cursor.fetchall()
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return tuple(_ownership(row) for row in rows)

    async def list_events(
        self, *, host_id: str, candidate_id: str, limit: int = 500
    ) -> Sequence[OwnershipEvent]:
        if not 1 <= limit <= 2_000:
            raise ValueError("ownership event limit must be between 1 and 2000")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT * FROM proactivity_ownership_events
                WHERE host_id = ? AND candidate_id = ? ORDER BY sequence LIMIT ?
                """,
                (host_id, candidate_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return tuple(_event(row) for row in rows)

    async def _device_transition(
        self,
        *,
        host_id: str,
        device_id: str,
        candidate_id: str,
        expected_version: int,
        lease_seconds: int | None,
        event_type: OwnershipEventType,
        reason_code: str,
        mode: str,
        target_device_id: str | None = None,
        allowed_features: frozenset[str] | None = None,
        now: datetime | None,
    ) -> CandidateOwnership:
        timestamp = _aware(now or datetime.now(UTC))
        if lease_seconds is not None and not 30 <= lease_seconds <= 300:
            raise ValueError("device ownership lease must be 30 through 300 seconds")
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await self._require_control_locked(connection, host_id=host_id)
                await self._expire_locked(connection, host_id=host_id, timestamp=timestamp)
                row = await self._ownership_row_locked(
                    connection, host_id=host_id, candidate_id=candidate_id
                )
                if row["version"] != expected_version:
                    raise DeviceOwnershipConflictError("candidate ownership changed")
                feature = str(row["feature"])
                if row["dispatch_state"] not in {"notified", "snoozed"} or row[
                    "notification_state"
                ] not in {"active", "snoozed"}:
                    raise DeviceOwnershipDeniedError("candidate notification is inactive")
                if allowed_features is not None and feature not in allowed_features:
                    raise DeviceOwnershipDeniedError("candidate feature is not configured")
                if mode == "local_handoff":
                    if row["owner_kind"] != OwnershipKind.LOCAL_HOST.value:
                        raise DeviceOwnershipDeniedError("candidate is not locally owned")
                else:
                    await self._require_binding_locked(
                        connection,
                        host_id=host_id,
                        device_id=device_id,
                        feature=feature,
                        require_manage=True,
                        timestamp=timestamp,
                    )
                if mode == "claim":
                    if row["owner_kind"] != OwnershipKind.LOCAL_HOST.value:
                        raise DeviceOwnershipConflictError("candidate already has a device owner")
                    target = device_id
                elif mode == "renew":
                    if row["owner_device_id"] != device_id:
                        raise DeviceOwnershipDeniedError("device does not own candidate")
                    if datetime.fromisoformat(row["lease_expires_at"]) <= timestamp:
                        raise DeviceOwnershipConflictError("device ownership lease expired")
                    target = device_id
                elif mode == "release":
                    if row["owner_device_id"] != device_id:
                        raise DeviceOwnershipDeniedError("device does not own candidate")
                    updated = await self._set_local_locked(
                        connection,
                        row=row,
                        timestamp=timestamp,
                        event_type=event_type,
                        reason_code=reason_code,
                    )
                    await connection.commit()
                    return updated
                else:
                    if target_device_id is None:
                        raise ValueError("handoff target is required")
                    if mode == "handoff" and row["owner_device_id"] != device_id:
                        raise DeviceOwnershipDeniedError("device does not own candidate")
                    target = target_device_id
                await self._require_binding_locked(
                    connection,
                    host_id=host_id,
                    device_id=target,
                    feature=feature,
                    require_manage=True,
                    timestamp=timestamp,
                )
                assert lease_seconds is not None
                lease_expiry = min(
                    timestamp + timedelta(seconds=lease_seconds),
                    datetime.fromisoformat(row["notification_expires_at"]),
                )
                if lease_expiry <= timestamp:
                    raise DeviceOwnershipDeniedError("candidate notification expired")
                cursor = await connection.execute(
                    """
                    UPDATE proactivity_ownerships
                    SET owner_kind = 'device', owner_id = ?, owner_device_id = ?,
                        lease_expires_at = ?, version = version + 1, updated_at = ?
                    WHERE host_id = ? AND candidate_id = ? AND version = ?
                    """,
                    (
                        target,
                        target,
                        _encode(lease_expiry),
                        _encode(timestamp),
                        host_id,
                        candidate_id,
                        expected_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise DeviceOwnershipConflictError("candidate ownership changed")
                updated_row = await self._ownership_row_locked(
                    connection, host_id=host_id, candidate_id=candidate_id
                )
                updated = _ownership(updated_row)
                await self._append_event_locked(
                    connection,
                    ownership=updated,
                    event_type=event_type,
                    reason_code=reason_code,
                    created_at=timestamp,
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return updated

    async def _ownership_row_locked(
        self, connection: aiosqlite.Connection, *, host_id: str, candidate_id: str
    ) -> aiosqlite.Row:
        row = await _fetchone(
            connection,
            """
            SELECT o.*, c.feature, d.state AS dispatch_state,
                   n.state AS notification_state, n.expires_at AS notification_expires_at
            FROM proactivity_ownerships AS o
            JOIN proactivity_candidates AS c ON c.id = o.candidate_id
            JOIN proactivity_dispatches AS d ON d.candidate_id = o.candidate_id
            JOIN proactivity_notifications AS n ON n.candidate_id = o.candidate_id
            WHERE o.host_id = ? AND o.candidate_id = ?
            """,
            (host_id, candidate_id),
        )
        if row is None:
            raise DeviceOwnershipNotFoundError("candidate ownership not found")
        return row

    async def _require_control_locked(
        self, connection: aiosqlite.Connection, *, host_id: str
    ) -> None:
        row = await _fetchone(
            connection,
            "SELECT enabled FROM proactivity_adapter_controls WHERE host_id = ?",
            (host_id,),
        )
        if row is None or not bool(row["enabled"]):
            raise DeviceOwnershipDeniedError("proactivity device adapter is locally disabled")

    async def _require_device_locked(
        self,
        connection: aiosqlite.Connection,
        *,
        host_id: str,
        device_id: str,
        require_manage: bool,
        timestamp: datetime,
    ) -> None:
        row = await _fetchone(
            connection,
            """
            SELECT state, scopes_json, credential_expires_at FROM remote_devices
            WHERE host_id = ? AND id = ?
            """,
            (host_id, device_id),
        )
        if (
            row is None
            or row["state"] != DeviceState.ACTIVE.value
            or datetime.fromisoformat(row["credential_expires_at"]) <= timestamp
        ):
            raise DeviceOwnershipDeniedError("device is unavailable")
        try:
            scopes = frozenset(RemoteScope(value) for value in json.loads(row["scopes_json"]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DeviceOwnershipCorruptionError("stored device scopes are invalid") from exc
        required = {RemoteScope.CLIENT_PROACTIVITY_READ}
        if require_manage:
            required.add(RemoteScope.CLIENT_PROACTIVITY_MANAGE)
        if not required.issubset(scopes):
            raise DeviceOwnershipDeniedError("device lacks proactivity scope")

    async def _require_binding_locked(
        self,
        connection: aiosqlite.Connection,
        *,
        host_id: str,
        device_id: str,
        feature: str,
        require_manage: bool,
        timestamp: datetime,
    ) -> None:
        await self._require_device_locked(
            connection,
            host_id=host_id,
            device_id=device_id,
            require_manage=require_manage,
            timestamp=timestamp,
        )
        row = await _fetchone(
            connection,
            """
            SELECT allow_manage, state, expires_at FROM proactivity_device_bindings
            WHERE host_id = ? AND device_id = ? AND feature = ?
            """,
            (host_id, device_id, feature),
        )
        if (
            row is None
            or row["state"] != DeviceBindingState.ACTIVE.value
            or datetime.fromisoformat(row["expires_at"]) <= timestamp
            or (require_manage and not bool(row["allow_manage"]))
        ):
            raise DeviceOwnershipDeniedError("device feature binding denied")

    async def _expire_locked(
        self, connection: aiosqlite.Connection, *, host_id: str, timestamp: datetime
    ) -> None:
        await connection.execute(
            """
            UPDATE proactivity_device_bindings
            SET state = 'expired', version = version + 1, updated_at = ?
            WHERE host_id = ? AND state = 'active' AND expires_at <= ?
            """,
            (_encode(timestamp), host_id, _encode(timestamp)),
        )
        await self._reclaim_matching_locked(
            connection,
            host_id=host_id,
            timestamp=timestamp,
            event_type=OwnershipEventType.LEASE_EXPIRED,
            reason_code="device_lease_expired_local_reclaim",
            expired_only=True,
        )

    async def _reclaim_matching_locked(
        self,
        connection: aiosqlite.Connection,
        *,
        host_id: str,
        timestamp: datetime,
        event_type: OwnershipEventType,
        reason_code: str,
        device_id: str | None = None,
        feature: str | None = None,
        expired_only: bool = False,
    ) -> None:
        sql = """
            SELECT o.*, c.feature, n.expires_at AS notification_expires_at
            FROM proactivity_ownerships AS o
            JOIN proactivity_candidates AS c ON c.id = o.candidate_id
            JOIN proactivity_notifications AS n ON n.candidate_id = o.candidate_id
            WHERE o.host_id = ? AND o.owner_kind = 'device'
        """
        values: list[object] = [host_id]
        if device_id is not None:
            sql += " AND o.owner_device_id = ?"
            values.append(device_id)
        if feature is not None:
            sql += " AND c.feature = ?"
            values.append(feature)
        if expired_only:
            sql += " AND o.lease_expires_at <= ?"
            values.append(_encode(timestamp))
        async with connection.execute(sql, values) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            await self._set_local_locked(
                connection,
                row=row,
                timestamp=timestamp,
                event_type=event_type,
                reason_code=reason_code,
            )

    async def _set_local_locked(
        self,
        connection: aiosqlite.Connection,
        *,
        row: aiosqlite.Row,
        timestamp: datetime,
        event_type: OwnershipEventType,
        reason_code: str,
    ) -> CandidateOwnership:
        cursor = await connection.execute(
            """
            UPDATE proactivity_ownerships
            SET owner_kind = 'local_host', owner_id = host_id, owner_device_id = NULL,
                lease_expires_at = NULL, version = version + 1, updated_at = ?
            WHERE candidate_id = ? AND version = ?
            """,
            (_encode(timestamp), row["candidate_id"], row["version"]),
        )
        if cursor.rowcount != 1:
            raise DeviceOwnershipConflictError("candidate ownership changed")
        updated_row = await self._ownership_row_locked(
            connection, host_id=row["host_id"], candidate_id=row["candidate_id"]
        )
        updated = _ownership(updated_row)
        await self._append_event_locked(
            connection,
            ownership=updated,
            event_type=event_type,
            reason_code=reason_code,
            created_at=timestamp,
        )
        return updated

    @staticmethod
    async def _append_event_locked(
        connection: aiosqlite.Connection,
        *,
        ownership: CandidateOwnership,
        event_type: OwnershipEventType,
        reason_code: str,
        created_at: datetime,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO proactivity_ownership_events
                (id, host_id, candidate_id, event_type, reason_code,
                 owner_kind, owner_device_id, version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"proactivity-owner-event:{uuid4()}",
                ownership.host_id,
                ownership.candidate_id,
                event_type.value,
                reason_code,
                ownership.owner_kind.value,
                ownership.owner_device_id,
                ownership.version,
                _encode(created_at),
            ),
        )

    async def _get_connection(self) -> aiosqlite.Connection:
        await self.initialize()
        if self._connection is None:
            raise ProactivityDeviceStoreError("device ownership store is not initialized")
        return self._connection


async def _fetchone(
    connection: aiosqlite.Connection, sql: str, parameters: Sequence[object]
) -> aiosqlite.Row | None:
    async with connection.execute(sql, parameters) as cursor:
        return await cursor.fetchone()


def _control(row: aiosqlite.Row) -> ProactivityAdapterControl:
    try:
        return ProactivityAdapterControl.model_validate(dict(row))
    except ValidationError as exc:
        raise DeviceOwnershipCorruptionError("stored adapter control is invalid") from exc


def _binding(row: aiosqlite.Row) -> ProactivityDeviceBinding:
    try:
        return ProactivityDeviceBinding.model_validate(dict(row))
    except ValidationError as exc:
        raise DeviceOwnershipCorruptionError("stored device binding is invalid") from exc


def _ownership(row: aiosqlite.Row) -> CandidateOwnership:
    try:
        return CandidateOwnership.model_validate(
            {field: row[field] for field in CandidateOwnership.model_fields}
        )
    except ValidationError as exc:
        raise DeviceOwnershipCorruptionError("stored candidate ownership is invalid") from exc


def _visible(row: aiosqlite.Row, *, device_id: str) -> VisibleProactivityState:
    try:
        return VisibleProactivityState(
            candidate_id=row["candidate_id"],
            feature=row["feature"],
            dispatch_state=row["dispatch_state"],
            notification_state=row["notification_state"],
            owner_kind=row["owner_kind"],
            owned_by_this_device=row["owner_device_id"] == device_id,
            ownership_version=row["version"],
            lease_expires_at=row["lease_expires_at"],
            available_at=row["available_at"],
            expires_at=row["expires_at"],
        )
    except ValidationError as exc:
        raise DeviceOwnershipCorruptionError("stored visible state is invalid") from exc


def _event(row: aiosqlite.Row) -> OwnershipEvent:
    try:
        return OwnershipEvent.model_validate(dict(row))
    except ValidationError as exc:
        raise DeviceOwnershipCorruptionError("stored ownership event is invalid") from exc


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("device ownership timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _encode(value: datetime) -> str:
    return _aware(value).isoformat(timespec="microseconds")
