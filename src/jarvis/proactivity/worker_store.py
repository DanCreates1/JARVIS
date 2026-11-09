"""Reuse canonical runner store lifecycle for fenced, single-owner worker control."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from .runner_store import SQLiteProactivityRunnerStore
from .worker_models import WorkerDeniedError, WorkerPermit, WorkerPlan, check_worker_permit, utc_now


class SQLiteProactivityWorkerStore(SQLiteProactivityRunnerStore):
    """Same SQLite/migration/transaction policy as the existing inbox runner."""

    async def status(self, *, host_id: str) -> dict[str, object]:
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """SELECT generation, enabled, expires_at, lease_expires_at, ticks_reserved
                   FROM proactivity_worker_controls WHERE host_id = ?""",
                (host_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return {"generation": 0, "enabled": False, "running": False, "ticks_reserved": 0}
        now = utc_now().isoformat(timespec="microseconds")
        enabled = bool(row[1]) and row[2] > now
        return {
            "generation": row[0],
            "enabled": enabled,
            "running": enabled and row[3] is not None and row[3] > now,
            "expires_at": row[2],
            "ticks_reserved": row[4],
        }

    async def enable(self, plan: WorkerPlan) -> None:
        now = utc_now()
        if (
            not plan.created_at
            <= now
            < min(plan.expires_at, plan.created_at + timedelta(minutes=5))
        ):
            raise WorkerDeniedError("worker review is stale")
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                now = utc_now()
                if (
                    not plan.created_at
                    <= now
                    < min(plan.expires_at, plan.created_at + timedelta(minutes=5))
                ):
                    raise WorkerDeniedError("worker review is stale")
                async with connection.execute(
                    "SELECT generation FROM proactivity_worker_controls WHERE host_id = ?",
                    (plan.host_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if (0 if row is None else row[0]) != plan.expected_generation:
                    raise WorkerDeniedError("worker review generation changed")
                await connection.execute(
                    """INSERT INTO proactivity_worker_controls
                           (host_id, generation, enabled, plan_json, expires_at, updated_at)
                       VALUES (?, ?, 1, ?, ?, ?)
                       ON CONFLICT(host_id) DO UPDATE SET
                           generation = excluded.generation, enabled = 1,
                           plan_json = excluded.plan_json, expires_at = excluded.expires_at,
                           updated_at = excluded.updated_at, owner_token = NULL,
                           lease_expires_at = NULL, ticks_reserved = 0""",
                    (
                        plan.host_id,
                        plan.expected_generation + 1,
                        plan.model_dump_json(),
                        _encode(plan.expires_at),
                        _encode(now),
                    ),
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise

    async def claim(self, *, host_id: str) -> tuple[WorkerPlan, WorkerPermit]:
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    "SELECT * FROM proactivity_worker_controls WHERE host_id = ?", (host_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                now = utc_now()
                if row is None or not row["enabled"] or row["expires_at"] <= _encode(now):
                    raise WorkerDeniedError("background evaluation is disabled or expired")
                if row["lease_expires_at"] is not None and row["lease_expires_at"] > _encode(now):
                    raise WorkerDeniedError("another background worker owns the lease")
                plan = WorkerPlan.model_validate_json(row["plan_json"])
                if (
                    plan.host_id != host_id
                    or now < plan.created_at
                    or row["ticks_reserved"] >= plan.max_ticks
                ):
                    raise WorkerDeniedError("worker scope or polling budget denied")
                permit = WorkerPermit(host_id, row["generation"], uuid4().hex, plan.features)
                await connection.execute(
                    """UPDATE proactivity_worker_controls SET owner_token = ?,
                           lease_expires_at = ?, updated_at = ? WHERE host_id = ?""",
                    (
                        permit.owner_token,
                        _encode(min(plan.expires_at, now + timedelta(seconds=90))),
                        _encode(now),
                        host_id,
                    ),
                )
                await connection.commit()
                return plan, permit
            except BaseException:
                await connection.rollback()
                raise

    async def reserve_tick(self, permit: WorkerPermit, plan: WorkerPlan) -> None:
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await check_worker_permit(connection, permit, host_id=permit.host_id)
                now = utc_now()
                cursor = await connection.execute(
                    """UPDATE proactivity_worker_controls SET ticks_reserved = ticks_reserved + 1,
                           lease_expires_at = ?, updated_at = ?
                       WHERE host_id = ? AND ticks_reserved < ?""",
                    (
                        _encode(min(plan.expires_at, now + timedelta(seconds=90))),
                        _encode(now),
                        permit.host_id,
                        plan.max_ticks,
                    ),
                )
                if cursor.rowcount != 1:
                    raise WorkerDeniedError("worker polling budget exhausted")
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise

    async def check(self, permit: WorkerPermit) -> None:
        async with self._operation_lock:
            await check_worker_permit(await self._get_connection(), permit, host_id=permit.host_id)

    async def release(self, permit: WorkerPermit) -> None:
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute(
                """UPDATE proactivity_worker_controls SET owner_token = NULL,
                       lease_expires_at = NULL, updated_at = ?
                   WHERE host_id = ? AND generation = ? AND owner_token = ?""",
                (_encode(utc_now()), permit.host_id, permit.generation, permit.owner_token),
            )
            await connection.commit()

    async def stop(self, *, host_id: str) -> None:
        """Revoke and erase the plan; retain a content-free generation against replay."""
        async with self._operation_lock:
            connection = await self._get_connection()
            now = _encode(utc_now())
            await connection.execute(
                """INSERT INTO proactivity_worker_controls
                       (host_id, generation, enabled, expires_at, updated_at)
                   VALUES (?, 1, 0, ?, ?)
                   ON CONFLICT(host_id) DO UPDATE SET
                       generation = generation + 1, enabled = 0, plan_json = NULL,
                       owner_token = NULL, lease_expires_at = NULL,
                       expires_at = excluded.expires_at,
                       updated_at = excluded.updated_at""",
                (host_id, now, now),
            )
            await connection.commit()


def _encode(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")
