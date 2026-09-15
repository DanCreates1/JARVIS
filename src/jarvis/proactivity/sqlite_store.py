"""Transactional host-isolated Phase 11A proactivity persistence."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiosqlite
from pydantic import ValidationError

from jarvis.memory.sqlite_store import SQLiteConversationStore

from .models import (
    EvaluationCode,
    EvaluationDecision,
    ProactivityEvent,
    ProactivityEventType,
    ProactivityExplanation,
    ProactivityExportReceipt,
    ProactivityRule,
    RuleDeletionReceipt,
    RulePreview,
    RuleStatus,
    SuggestionCandidate,
    TriggerEvent,
    TrustedActivation,
)
from .policy import HostProactivityPolicy, ProactivityPolicyError, local_day_bounds


class ProactivityStoreError(RuntimeError):
    pass


class ProactivityNotFoundError(ProactivityStoreError):
    pass


class ProactivityStateError(ProactivityStoreError):
    pass


class ProactivityConflictError(ProactivityStoreError):
    pass


class ProactivityCorruptionError(ProactivityStoreError):
    pass


class SQLiteProactivityStore:
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
                async with connection.execute("PRAGMA quick_check") as cursor:
                    row = await cursor.fetchone()
                if row is None or row[0] != "ok":
                    raise ProactivityCorruptionError("SQLite quick_check failed")
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

    async def __aenter__(self) -> SQLiteProactivityStore:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    async def create_rule(
        self,
        *,
        host_id: str,
        preview: RulePreview,
        now: datetime | None = None,
    ) -> ProactivityRule:
        timestamp = _aware(now or datetime.now(UTC))
        rule = ProactivityRule(
            id=f"proactivity:{uuid4()}",
            host_id=host_id,
            proposal=preview.proposal,
            proposal_sha256=preview.proposal_sha256,
            created_at=timestamp,
            updated_at=timestamp,
        )
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    """
                    INSERT INTO proactivity_rules
                        (id, host_id, status, proposal_sha256, record_json, version,
                         expires_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rule.id,
                        rule.host_id,
                        rule.status.value,
                        rule.proposal_sha256,
                        rule.model_dump_json(),
                        rule.version,
                        rule.proposal.expires_at.isoformat(timespec="microseconds"),
                        rule.created_at.isoformat(timespec="microseconds"),
                        rule.updated_at.isoformat(timespec="microseconds"),
                    ),
                )
                await self._append_event(
                    connection,
                    rule=rule,
                    event_type=ProactivityEventType.RULE_CREATED,
                    reason_code="preview_persisted_no_authority",
                    created_at=timestamp,
                )
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                await connection.rollback()
                raise ProactivityConflictError("proactivity rule ID already exists") from exc
            except BaseException:
                await connection.rollback()
                raise
        return rule

    async def get_rule(self, *, host_id: str, rule_id: str) -> ProactivityRule | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                "SELECT record_json FROM proactivity_rules WHERE host_id = ? AND id = ?",
                (host_id, rule_id),
            ) as cursor:
                row = await cursor.fetchone()
        return None if row is None else _rule(row["record_json"])

    async def require_rule(self, *, host_id: str, rule_id: str) -> ProactivityRule:
        rule = await self.get_rule(host_id=host_id, rule_id=rule_id)
        if rule is None:
            raise ProactivityNotFoundError("proactivity rule not found")
        return rule

    async def list_rules(
        self,
        *,
        host_id: str,
        status: RuleStatus | None = None,
        limit: int = 100,
    ) -> Sequence[ProactivityRule]:
        if not 1 <= limit <= 500:
            raise ValueError("rule limit must be between 1 and 500")
        sql = "SELECT record_json FROM proactivity_rules WHERE host_id = ?"
        parameters: list[object] = [host_id]
        if status is not None:
            sql += " AND status = ?"
            parameters.append(status.value)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        parameters.append(limit)
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(sql, parameters) as cursor:
                rows = await cursor.fetchall()
        return tuple(_rule(row["record_json"]) for row in rows)

    async def activate(
        self,
        approval: TrustedActivation,
        *,
        policy: HostProactivityPolicy,
        now: datetime | None = None,
    ) -> ProactivityRule:
        timestamp = _aware(now or datetime.now(UTC))
        if timestamp < approval.approved_at - timedelta(seconds=policy.clock_skew_seconds):
            raise ProactivityStateError("activation approval is from the future")
        if timestamp >= approval.expires_at:
            raise ProactivityStateError("activation approval expired")
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                rule = await self._load_rule(
                    connection, host_id=approval.host_id, rule_id=approval.rule_id
                )
                if rule is None:
                    raise ProactivityNotFoundError("proactivity rule not found")
                if rule.status is not RuleStatus.DRAFT:
                    raise ProactivityStateError("only a draft rule can be activated")
                if rule.version != approval.expected_version:
                    raise ProactivityConflictError("proactivity rule version changed")
                if rule.proposal_sha256 != approval.expected_proposal_sha256:
                    raise ProactivityConflictError("proactivity proposal digest changed")
                policy.preview(rule.proposal, now=timestamp)
                updated = rule.model_copy(
                    update={
                        "status": RuleStatus.ACTIVE,
                        "version": rule.version + 1,
                        "activated_at": timestamp,
                        "updated_at": timestamp,
                    }
                )
                updated = ProactivityRule.model_validate(updated.model_dump())
                await connection.execute(
                    """
                    INSERT INTO proactivity_activations
                        (approval_id, host_id, rule_id, proposal_sha256, interface,
                         approved_at, expires_at, consumed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        approval.approval_id,
                        approval.host_id,
                        approval.rule_id,
                        approval.expected_proposal_sha256,
                        approval.interface,
                        approval.approved_at.isoformat(timespec="microseconds"),
                        approval.expires_at.isoformat(timespec="microseconds"),
                        timestamp.isoformat(timespec="microseconds"),
                    ),
                )
                cursor = await connection.execute(
                    """
                    UPDATE proactivity_rules
                    SET status = ?, record_json = ?, version = ?, updated_at = ?
                    WHERE id = ? AND host_id = ? AND version = ?
                    """,
                    (
                        updated.status.value,
                        updated.model_dump_json(),
                        updated.version,
                        timestamp.isoformat(timespec="microseconds"),
                        updated.id,
                        updated.host_id,
                        rule.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ProactivityConflictError("proactivity rule changed")
                await self._append_event(
                    connection,
                    rule=updated,
                    event_type=ProactivityEventType.RULE_ACTIVATED,
                    reason_code="exact_trusted_preview_activated",
                    created_at=timestamp,
                )
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                await connection.rollback()
                raise ProactivityConflictError("activation approval was already consumed") from exc
            except BaseException:
                await connection.rollback()
                raise
        return updated

    async def disable(
        self,
        *,
        host_id: str,
        rule_id: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> ProactivityRule:
        timestamp = _aware(now or datetime.now(UTC))
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                rule = await self._load_rule(connection, host_id=host_id, rule_id=rule_id)
                if rule is None:
                    raise ProactivityNotFoundError("proactivity rule not found")
                if rule.version != expected_version:
                    raise ProactivityConflictError("proactivity rule version changed")
                if rule.status is RuleStatus.DISABLED:
                    raise ProactivityStateError("proactivity rule is already disabled")
                updated = ProactivityRule.model_validate(
                    rule.model_copy(
                        update={
                            "status": RuleStatus.DISABLED,
                            "version": rule.version + 1,
                            "updated_at": timestamp,
                        }
                    ).model_dump()
                )
                cursor = await connection.execute(
                    """
                    UPDATE proactivity_rules
                    SET status = ?, record_json = ?, version = ?, updated_at = ?
                    WHERE id = ? AND host_id = ? AND version = ?
                    """,
                    (
                        updated.status.value,
                        updated.model_dump_json(),
                        updated.version,
                        timestamp.isoformat(timespec="microseconds"),
                        updated.id,
                        updated.host_id,
                        rule.version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ProactivityConflictError("proactivity rule changed")
                await self._append_event(
                    connection,
                    rule=updated,
                    event_type=ProactivityEventType.RULE_DISABLED,
                    reason_code="trusted_host_disabled",
                    created_at=timestamp,
                )
                async with connection.execute(
                    """
                    SELECT candidate_id FROM proactivity_dispatches
                    WHERE host_id = ? AND rule_id = ?
                      AND state IN ('claimed', 'notified', 'snoozed')
                    """,
                    (host_id, rule_id),
                ) as cursor:
                    active_dispatches = await cursor.fetchall()
                for dispatch in active_dispatches:
                    await connection.execute(
                        """
                        UPDATE proactivity_dispatches
                        SET state = 'cancelled', version = version + 1,
                            lease_id = NULL, lease_expires_at = NULL,
                            snoozed_until = NULL, updated_at = ?
                        WHERE candidate_id = ?
                        """,
                        (
                            timestamp.isoformat(timespec="microseconds"),
                            dispatch["candidate_id"],
                        ),
                    )
                    await connection.execute(
                        """
                        UPDATE proactivity_notifications
                        SET state = 'cancelled', updated_at = ? WHERE candidate_id = ?
                        """,
                        (
                            timestamp.isoformat(timespec="microseconds"),
                            dispatch["candidate_id"],
                        ),
                    )
                    await connection.execute(
                        """
                        INSERT INTO proactivity_runner_events
                            (id, host_id, rule_id, candidate_id, event_type,
                             reason_code, created_at)
                        VALUES (?, ?, ?, ?, 'cancelled', 'rule_disabled_kill_switch', ?)
                        """,
                        (
                            f"proactivity-runner-event:{uuid4()}",
                            host_id,
                            rule_id,
                            dispatch["candidate_id"],
                            timestamp.isoformat(timespec="microseconds"),
                        ),
                    )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return updated

    async def evaluate_and_record(
        self,
        *,
        host_id: str,
        rule_id: str,
        policy: HostProactivityPolicy,
        now: datetime | None = None,
        event: TriggerEvent | None = None,
    ) -> tuple[EvaluationDecision, SuggestionCandidate | None]:
        timestamp = _aware(now or datetime.now(UTC))
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                rule = await self._load_rule(connection, host_id=host_id, rule_id=rule_id)
                if rule is None:
                    raise ProactivityNotFoundError("proactivity rule not found")
                if rule.status is RuleStatus.ACTIVE and timestamp >= rule.proposal.expires_at:
                    expired = ProactivityRule.model_validate(
                        rule.model_copy(
                            update={
                                "status": RuleStatus.EXPIRED,
                                "version": rule.version + 1,
                                "updated_at": timestamp,
                            }
                        ).model_dump()
                    )
                    await connection.execute(
                        """
                        UPDATE proactivity_rules
                        SET status = ?, record_json = ?, version = ?, updated_at = ?
                        WHERE id = ? AND host_id = ? AND version = ?
                        """,
                        (
                            expired.status.value,
                            expired.model_dump_json(),
                            expired.version,
                            timestamp.isoformat(timespec="microseconds"),
                            expired.id,
                            expired.host_id,
                            rule.version,
                        ),
                    )
                    await self._append_event(
                        connection,
                        rule=expired,
                        event_type=ProactivityEventType.RULE_EXPIRED,
                        reason_code="scope_expired",
                        created_at=timestamp,
                    )
                    await connection.commit()
                    return (
                        EvaluationDecision(
                            rule_id=rule_id,
                            code=EvaluationCode.RULE_EXPIRED,
                            eligible=False,
                        ),
                        None,
                    )
                initial = policy.evaluate(rule, now=timestamp, event=event)
                if not initial.eligible:
                    await connection.rollback()
                    return initial, None
                assert initial.occurrence_key is not None and initial.scheduled_for is not None
                async with connection.execute(
                    """
                    SELECT 1 FROM proactivity_candidates
                    WHERE host_id = ? AND rule_id = ? AND occurrence_key = ?
                    """,
                    (host_id, rule_id, initial.occurrence_key),
                ) as cursor:
                    duplicate = await cursor.fetchone() is not None
                hour_start = timestamp - timedelta(hours=1)
                day_start, day_end = local_day_bounds(timestamp, rule.proposal.schedule.timezone)
                hourly_count = await _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM proactivity_candidates
                    WHERE host_id = ? AND created_at > ?
                    """,
                    (host_id, hour_start.isoformat(timespec="microseconds")),
                )
                daily_count = await _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM proactivity_candidates
                    WHERE host_id = ? AND created_at >= ? AND created_at < ?
                    """,
                    (
                        host_id,
                        day_start.isoformat(timespec="microseconds"),
                        day_end.isoformat(timespec="microseconds"),
                    ),
                )
                daily_attention = await _scalar(
                    connection,
                    """
                    SELECT COALESCE(SUM(attention_seconds), 0) FROM proactivity_candidates
                    WHERE host_id = ? AND created_at >= ? AND created_at < ?
                    """,
                    (
                        host_id,
                        day_start.isoformat(timespec="microseconds"),
                        day_end.isoformat(timespec="microseconds"),
                    ),
                )
                active_candidates = await _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM proactivity_candidates
                    WHERE host_id = ? AND expires_at > ?
                    """,
                    (host_id, timestamp.isoformat(timespec="microseconds")),
                )
                decision = policy.evaluate(
                    rule,
                    now=timestamp,
                    event=event,
                    hourly_count=hourly_count,
                    daily_count=daily_count,
                    daily_attention_seconds=daily_attention,
                    active_candidates=active_candidates,
                    duplicate=duplicate,
                )
                if not decision.eligible:
                    await connection.rollback()
                    return decision, None
                candidate = SuggestionCandidate(
                    id=f"suggestion:{uuid4()}",
                    host_id=host_id,
                    rule_id=rule_id,
                    feature=rule.proposal.feature,
                    occurrence_key=decision.occurrence_key,
                    scheduled_for=decision.scheduled_for,
                    attention_seconds=rule.proposal.estimated_attention_seconds,
                    created_at=timestamp,
                    expires_at=min(
                        rule.proposal.expires_at,
                        timestamp + timedelta(seconds=max(1, policy.clock_skew_seconds)),
                    ),
                )
                await connection.execute(
                    """
                    INSERT INTO proactivity_candidates
                        (id, host_id, rule_id, feature, occurrence_key, scheduled_for,
                         attention_seconds, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.id,
                        candidate.host_id,
                        candidate.rule_id,
                        candidate.feature,
                        candidate.occurrence_key,
                        candidate.scheduled_for.isoformat(timespec="microseconds"),
                        candidate.attention_seconds,
                        candidate.created_at.isoformat(timespec="microseconds"),
                        candidate.expires_at.isoformat(timespec="microseconds"),
                    ),
                )
                await self._append_event(
                    connection,
                    rule=rule,
                    candidate_id=candidate.id,
                    event_type=ProactivityEventType.CANDIDATE_CREATED,
                    reason_code="inert_suggestion_only",
                    created_at=timestamp,
                )
                await connection.commit()
            except aiosqlite.IntegrityError:
                await connection.rollback()
                return (
                    EvaluationDecision(
                        rule_id=rule_id,
                        code=EvaluationCode.DUPLICATE,
                        eligible=False,
                    ),
                    None,
                )
            except BaseException:
                await connection.rollback()
                raise
        return decision, candidate

    async def list_candidates(
        self, *, host_id: str, rule_id: str | None = None, limit: int = 100
    ) -> Sequence[SuggestionCandidate]:
        if not 1 <= limit <= 500:
            raise ValueError("candidate limit must be between 1 and 500")
        sql = "SELECT * FROM proactivity_candidates WHERE host_id = ?"
        parameters: list[object] = [host_id]
        if rule_id is not None:
            sql += " AND rule_id = ?"
            parameters.append(rule_id)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        parameters.append(limit)
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(sql, parameters) as cursor:
                rows = await cursor.fetchall()
        return tuple(_candidate(row) for row in rows)

    async def explain_candidate(self, *, host_id: str, candidate_id: str) -> ProactivityExplanation:
        """Return a content-minimized local explanation without granting authority."""
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT c.id AS candidate_id, c.rule_id, c.feature, c.scheduled_for,
                       r.record_json,
                       COALESCE(e.reason_code, 'inert_suggestion_only') AS decision_reason,
                       o.owner_kind
                FROM proactivity_candidates AS c
                JOIN proactivity_rules AS r
                  ON r.id = c.rule_id AND r.host_id = c.host_id
                LEFT JOIN proactivity_events AS e
                  ON e.candidate_id = c.id AND e.event_type = 'candidate_created'
                LEFT JOIN proactivity_ownerships AS o ON o.candidate_id = c.id
                WHERE c.host_id = ? AND c.id = ?
                ORDER BY e.sequence
                LIMIT 1
                """,
                (host_id, candidate_id),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            raise ProactivityNotFoundError("proactivity candidate not found")
        rule = _rule(row["record_json"])
        audience = "scoped_pwa_device" if row["owner_kind"] == "device" else "local_host"
        return ProactivityExplanation(
            candidate_id=row["candidate_id"],
            rule_id=row["rule_id"],
            feature=row["feature"],
            trigger_kind=rule.proposal.schedule.kind,
            scheduled_for=datetime.fromisoformat(row["scheduled_for"]),
            decision_reason=row["decision_reason"],
            proposal_source=rule.proposal.provenance.source_type,
            declared_data_classes=rule.proposal.scope.data_classes,
            effective_audience=audience,
        )

    async def list_events(
        self, *, host_id: str, rule_id: str, limit: int = 500
    ) -> Sequence[ProactivityEvent]:
        if not 1 <= limit <= 2_000:
            raise ValueError("event limit must be between 1 and 2000")
        if await self.get_rule(host_id=host_id, rule_id=rule_id) is None:
            raise ProactivityNotFoundError("proactivity rule not found")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT sequence, id, host_id, rule_id, candidate_id, event_type,
                       reason_code, created_at
                FROM proactivity_events
                WHERE host_id = ? AND rule_id = ? ORDER BY sequence LIMIT ?
                """,
                (host_id, rule_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return tuple(ProactivityEvent.model_validate(dict(row)) for row in rows)

    async def delete_rule(
        self, *, host_id: str, rule_id: str, now: datetime | None = None
    ) -> RuleDeletionReceipt:
        timestamp = _aware(now or datetime.now(UTC))
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                rule = await self._load_rule(connection, host_id=host_id, rule_id=rule_id)
                if rule is None:
                    raise ProactivityNotFoundError("proactivity rule not found")
                candidates = await _scalar(
                    connection,
                    "SELECT COUNT(*) FROM proactivity_candidates WHERE host_id = ? AND rule_id = ?",
                    (host_id, rule_id),
                )
                events = await _scalar(
                    connection,
                    "SELECT COUNT(*) FROM proactivity_events WHERE host_id = ? AND rule_id = ?",
                    (host_id, rule_id),
                )
                events += await _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM proactivity_runner_events
                    WHERE host_id = ? AND rule_id = ?
                    """,
                    (host_id, rule_id),
                )
                events += await _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM proactivity_ownership_events AS e
                    JOIN proactivity_candidates AS c ON c.id = e.candidate_id
                    WHERE e.host_id = ? AND c.rule_id = ?
                    """,
                    (host_id, rule_id),
                )
                await connection.execute(
                    "DELETE FROM proactivity_rules WHERE host_id = ? AND id = ?",
                    (host_id, rule_id),
                )
                await connection.execute(
                    """
                    INSERT INTO proactivity_tombstones
                        (rule_id, host_id, deleted_candidates, deleted_events, deleted_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        rule_id,
                        host_id,
                        candidates,
                        events,
                        timestamp.isoformat(timespec="microseconds"),
                    ),
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return RuleDeletionReceipt(
            rule_id=rule_id,
            deleted_candidates=candidates,
            deleted_events=events,
            deleted_at=timestamp,
        )

    async def export(
        self, *, host_id: str, path: str | Path, now: datetime | None = None
    ) -> ProactivityExportReceipt:
        timestamp = _aware(now or datetime.now(UTC))
        rules = await self.list_rules(host_id=host_id, limit=500)
        candidates = await self.list_candidates(host_id=host_id, limit=500)
        event_rows: list[ProactivityEvent] = []
        for rule in rules:
            event_rows.extend(await self.list_events(host_id=host_id, rule_id=rule.id, limit=2_000))
        destination = Path(path)
        payload = {
            "schema": "jarvis-proactivity-export-v3",
            "exported_at": timestamp.isoformat(timespec="microseconds"),
            "rules": [rule.model_dump(mode="json") for rule in rules],
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            "events": [event.model_dump(mode="json") for event in event_rows],
            "runner": await self._export_runner_rows(host_id=host_id),
            "devices": await self._export_device_rows(host_id=host_id),
        }
        await asyncio.to_thread(_write_exclusive_json, destination, payload)
        return ProactivityExportReceipt(
            path=str(destination),
            rule_count=len(rules),
            candidate_count=len(candidates),
            event_count=len(event_rows),
            exported_at=timestamp,
        )

    async def _export_runner_rows(self, *, host_id: str) -> dict[str, list[dict[str, object]]]:
        async with self._operation_lock:
            connection = await self._get_connection()
            tables = {
                "dispatches": "proactivity_dispatches",
                "notifications": "proactivity_notifications",
                "events": "proactivity_runner_events",
            }
            exported: dict[str, list[dict[str, object]]] = {}
            for label, table in tables.items():
                async with connection.execute(
                    f"SELECT * FROM {table} WHERE host_id = ? ORDER BY rowid", (host_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                exported[label] = [dict(row) for row in rows]
            return exported

    async def _export_device_rows(self, *, host_id: str) -> dict[str, list[dict[str, object]]]:
        async with self._operation_lock:
            connection = await self._get_connection()
            tables = {
                "control": "proactivity_adapter_controls",
                "bindings": "proactivity_device_bindings",
                "ownerships": "proactivity_ownerships",
                "events": "proactivity_ownership_events",
            }
            exported: dict[str, list[dict[str, object]]] = {}
            for label, table in tables.items():
                async with connection.execute(
                    f"SELECT * FROM {table} WHERE host_id = ? ORDER BY rowid", (host_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                exported[label] = [dict(row) for row in rows]
            return exported

    async def _get_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise ProactivityStoreError("proactivity store is not initialized")
        return self._connection

    @staticmethod
    async def _load_rule(
        connection: aiosqlite.Connection, *, host_id: str, rule_id: str
    ) -> ProactivityRule | None:
        async with connection.execute(
            "SELECT record_json FROM proactivity_rules WHERE host_id = ? AND id = ?",
            (host_id, rule_id),
        ) as cursor:
            row = await cursor.fetchone()
        return None if row is None else _rule(row["record_json"])

    @staticmethod
    async def _append_event(
        connection: aiosqlite.Connection,
        *,
        rule: ProactivityRule,
        event_type: ProactivityEventType,
        reason_code: str,
        created_at: datetime,
        candidate_id: str | None = None,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO proactivity_events
                (id, host_id, rule_id, candidate_id, event_type, reason_code, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"proactivity-event:{uuid4()}",
                rule.host_id,
                rule.id,
                candidate_id,
                event_type.value,
                reason_code,
                created_at.isoformat(timespec="microseconds"),
            ),
        )


async def _scalar(
    connection: aiosqlite.Connection, sql: str, parameters: tuple[object, ...]
) -> int:
    async with connection.execute(sql, parameters) as cursor:
        row = await cursor.fetchone()
    return 0 if row is None else int(row[0])


def _rule(payload: str) -> ProactivityRule:
    try:
        return ProactivityRule.model_validate_json(payload)
    except ValidationError as exc:
        raise ProactivityCorruptionError("stored proactivity rule is invalid") from exc


def _candidate(row: aiosqlite.Row) -> SuggestionCandidate:
    try:
        return SuggestionCandidate.model_validate(dict(row))
    except ValidationError as exc:
        raise ProactivityCorruptionError("stored suggestion candidate is invalid") from exc


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProactivityPolicyError("store clock must include a timezone")
    return value.astimezone(UTC)


def _write_exclusive_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
