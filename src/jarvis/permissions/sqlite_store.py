"""Durable SQLite authority state for Phase 3 approvals and broker execution.

The store owns a separate serialized connection. Cross-process one-use grant claims
are protected by ``BEGIN IMMEDIATE`` plus an exact conditional update; process-local
locks alone are never treated as an authorization boundary.
"""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Final, Self, TypeVar

import aiosqlite
from pydantic import Field, JsonValue, StringConstraints, field_validator

from jarvis.core import ApprovalRule, PermissionLevel, ToolRisk
from jarvis.core.models import Identifier

from .canonical import canonical_json, canonical_json_bytes
from .models import (
    ActionAuditEvent,
    ActionAuditEventType,
    ApprovalDecision,
    ApprovalGrant,
    ApprovalRequest,
    AuthenticationAssurance,
    DomainModel,
    ExecutionOutcome,
    ExecutionReceipt,
    InteractionInterface,
    RollbackStatus,
)

_MIGRATION_PATTERN: Final = re.compile(r"^(?P<version>[0-9]{3})_(?P<name>[a-z0-9_]+)\.sql$")
_DEFAULT_BUSY_TIMEOUT_MS: Final = 5_000
_DEFAULT_MAX_LIST_ITEMS: Final = 500
_DEFAULT_MAX_AUDIT_EVENTS_PER_REQUEST: Final = 100
_DEFAULT_MAX_AUDIT_DETAIL_BYTES: Final = 4_096
_DEFAULT_MAX_AUDIT_EVENT_BYTES: Final = 16_384
_DEFAULT_MAX_RECEIPT_BYTES: Final = 262_144
_MAX_REQUEST_BYTES: Final = 262_144
_SAFE_AUDIT_DETAIL_KEYS: Final = frozenset(
    {
        "duration_ms",
        "postcondition_status",
        "reason_code",
        "result_bytes",
        "rollback_status",
    }
)

Now = Callable[[], datetime]
ModelT = TypeVar("ModelT", bound=DomainModel)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ApprovalSource(StrEnum):
    LOCAL_CLI = "local_cli"
    LOCAL_WEB = "local_web"
    VOICE = "voice"
    SYSTEM = "system"
    TEST = "test"
    CHAT = "chat"
    HANDS_FREE = "hands_free"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNCERTAIN = "uncertain"
    ROLLED_BACK = "rolled_back"


class GrantStatus(StrEnum):
    ACTIVE = "active"
    CLAIMED = "claimed"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ControlIntentOutcome(StrEnum):
    PROPOSED = "proposed"
    DENIED = "denied"
    DUPLICATE = "duplicate"
    STALE = "stale"
    RATE_LIMITED = "rate_limited"
    CANCELLED = "cancelled"


class ActionLifecycleEventType(StrEnum):
    """Sanitized append-only authority transition visible to local operators."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    GRANT_ISSUED = "grant_issued"
    GRANT_CLAIMED = "grant_claimed"
    GRANT_REVOKED = "grant_revoked"
    GRANT_EXPIRED = "grant_expired"
    EXECUTION_STARTED = "execution_started"
    BROKER_REJECTED = "broker_rejected"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_CANCELLED = "execution_cancelled"
    EXECUTION_UNCERTAIN = "execution_uncertain"
    EXECUTION_ROLLED_BACK = "execution_rolled_back"


class ActionLifecycleEvent(DomainModel):
    """Bounded audit projection containing no arguments, results, actors, or hashes."""

    event_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    type: ActionLifecycleEventType
    request_id: Identifier
    approval_id: Identifier
    grant_id: Identifier | None = None
    action_id: Annotated[str, Field(min_length=1, max_length=100)]
    action_version: Annotated[str, Field(min_length=1, max_length=32)]
    permission_level: PermissionLevel
    source: ApprovalSource
    risk: ToolRisk
    approval_rule: ApprovalRule
    outcome: ExecutionOutcome | None = None
    reason_code: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="occurred_at")


class ActionAuditSummary(DomainModel):
    """Execution-event projection safe for bounded operator views."""

    event_id: Identifier
    type: ActionAuditEventType
    request_id: Identifier
    grant_id: Identifier
    action_id: Annotated[str, Field(min_length=1, max_length=100)]
    action_version: Annotated[str, Field(min_length=1, max_length=32)]
    outcome: ExecutionOutcome | None = None
    reason_code: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="occurred_at")


class ActionReceiptSummary(DomainModel):
    """Terminal receipt projection that omits private result and authority payloads."""

    receipt_id: Identifier
    request_id: Identifier
    grant_id: Identifier
    action_id: Annotated[str, Field(min_length=1, max_length=100)]
    action_version: Annotated[str, Field(min_length=1, max_length=32)]
    outcome: ExecutionOutcome
    postcondition_status: Annotated[str, Field(min_length=1, max_length=100)]
    rollback_status: Annotated[str, Field(min_length=1, max_length=100)]
    reason_code: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    finished_at: datetime

    @field_validator("finished_at")
    @classmethod
    def normalize_finished_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="finished_at")


class ApprovalRequestRecord(DomainModel):
    """Approval plus queryable trusted policy metadata and lifecycle state."""

    request: ApprovalRequest
    source: ApprovalSource
    risk: ToolRisk
    rule_id: Identifier
    status: ApprovalStatus
    decision: ApprovalDecision | None = None
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="updated_at")


class GrantRecord(DomainModel):
    grant: ApprovalGrant
    status: GrantStatus
    claimed_at: datetime | None = None
    revoked_at: datetime | None = None

    @field_validator("claimed_at", "revoked_at")
    @classmethod
    def normalize_optional_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, field_name="grant lifecycle timestamp")


IntentName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$",
    ),
]


class ControlIntentEvent(DomainModel):
    event_id: Identifier
    actor_id: Identifier
    session_id: Identifier
    source: ApprovalSource
    intent: IntentName
    outcome: ControlIntentOutcome
    request_id: Identifier | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="created_at")


class ExpirationResult(DomainModel):
    approval_requests: Annotated[int, Field(ge=0)]
    grants: Annotated[int, Field(ge=0)]


class ActionStoreConflictError(ValueError):
    """Persisted authority is bound to different exact data."""


class ActionAuditSequenceConflictError(ActionStoreConflictError):
    """An action audit append did not use the exact next request sequence."""


class ActionStoreStateError(RuntimeError):
    """Requested lifecycle transition is not valid for durable state."""


class SQLiteActionStore:
    """SQLite implementation of action state, approval state, and action audit ports."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
        max_list_items: int = _DEFAULT_MAX_LIST_ITEMS,
        max_audit_events_per_request: int = _DEFAULT_MAX_AUDIT_EVENTS_PER_REQUEST,
        max_audit_detail_bytes: int = _DEFAULT_MAX_AUDIT_DETAIL_BYTES,
        max_audit_event_bytes: int = _DEFAULT_MAX_AUDIT_EVENT_BYTES,
        max_receipt_bytes: int = _DEFAULT_MAX_RECEIPT_BYTES,
        now: Now = _utc_now,
    ) -> None:
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        if max_list_items < 1 or max_list_items > 5_000:
            raise ValueError("max_list_items must be between 1 and 5000")
        if not 2 <= max_audit_events_per_request <= 10_000:
            raise ValueError("max_audit_events_per_request must be between 2 and 10000")
        if not 64 <= max_audit_detail_bytes <= 65_536:
            raise ValueError("max_audit_detail_bytes must be between 64 and 65536")
        if max_audit_event_bytes < max_audit_detail_bytes or max_audit_event_bytes > 262_144:
            raise ValueError("max_audit_event_bytes must cover detail and be at most 262144")
        if not 4_096 <= max_receipt_bytes <= 1_048_576:
            raise ValueError("max_receipt_bytes must be between 4096 and 1048576")

        self._database_path = Path(database_path)
        self._busy_timeout_ms = busy_timeout_ms
        self._max_list_items = max_list_items
        self._max_audit_events_per_request = max_audit_events_per_request
        self._max_audit_detail_bytes = max_audit_detail_bytes
        self._max_audit_event_bytes = max_audit_event_bytes
        self._max_receipt_bytes = max_receipt_bytes
        self._now = now
        self._connection: aiosqlite.Connection | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()

    @property
    def database_path(self) -> Path:
        return self._database_path

    async def initialize(self) -> None:
        """Open a hardened connection and apply all packaged migrations."""
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
                await connection.execute("PRAGMA synchronous = FULL")
                await self._apply_migrations(connection)
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

    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    async def create_approval_request(
        self,
        request: ApprovalRequest,
        *,
        source: ApprovalSource | InteractionInterface | str,
        risk: ToolRisk | str,
        rule_id: str,
    ) -> ApprovalRequestRecord:
        """Persist one exact pending approval and its trusted display metadata."""
        request = _revalidate(ApprovalRequest, request)
        source_value = ApprovalSource(str(source))
        risk_value = ToolRisk(str(risk))
        record = ApprovalRequestRecord(
            request=request,
            source=source_value,
            risk=risk_value,
            rule_id=rule_id,
            status=ApprovalStatus.PENDING,
            updated_at=request.requested_at,
        )
        request_json = request.model_dump_json()
        if len(request_json.encode("utf-8")) > _MAX_REQUEST_BYTES:
            raise ValueError("approval request exceeds durable size limit")

        action = request.action
        timestamp = _timestamp(request.requested_at)
        values = (
            action.request_id,
            request.approval_id,
            action.conversation_id,
            action.tool_call_id,
            action.actor.host_id,
            action.actor.session_id,
            action.actor.device_id,
            action.actor.model_dump_json(),
            source_value.value,
            action.action_id,
            action.action_version,
            int(action.permission_level),
            action.approval_rule.value,
            risk_value.value,
            action.policy_version,
            record.rule_id,
            canonical_json(action.normalized_arguments),
            action.fingerprint,
            action.idempotency_key,
            action.human_effect,
            action.recovery_limits,
            canonical_json(action.precondition),
            request_json,
            ApprovalStatus.PENDING.value,
            _timestamp(request.expires_at),
            timestamp,
            timestamp,
        )
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    """
                    INSERT INTO action_requests (
                        id, approval_id, conversation_id, tool_call_id, actor_id, session_id,
                        device_id, actor_json, source, action_id, action_version,
                        permission_level, approval_rule, risk, policy_version, rule_id,
                        normalized_arguments_json, fingerprint, idempotency_key, human_effect,
                        recovery_limits, precondition_json, request_json, status, expires_at,
                        created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?
                    )
                    """,
                    values,
                )
                await self._append_lifecycle_event(
                    connection,
                    record=record,
                    event_type=ActionLifecycleEventType.PROPOSED,
                    occurred_at=request.requested_at,
                )
                await connection.commit()
            except sqlite3.IntegrityError as error:
                await connection.rollback()
                existing = await self._select_request_record(
                    connection, approval_id=request.approval_id
                )
                if existing == record:
                    return existing
                raise ActionStoreConflictError(
                    "approval request identifier or idempotency binding already exists"
                ) from error
            except BaseException:
                await connection.rollback()
                raise
        return record

    async def get_approval_request(
        self,
        approval_id: str,
        *,
        expire_as_of: datetime | None = None,
    ) -> ApprovalRequestRecord | None:
        if expire_as_of is not None:
            await self.expire_stale(now=expire_as_of)
        async with self._operation_lock:
            connection = await self._get_connection()
            return await self._select_request_record(connection, approval_id=approval_id)

    async def get_approval_request_by_idempotency_key(
        self,
        idempotency_key: str,
        *,
        expire_as_of: datetime | None = None,
    ) -> ApprovalRequestRecord | None:
        """Load the proposal bound to an idempotency key, if any."""
        if expire_as_of is not None:
            await self.expire_stale(now=expire_as_of)
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                "SELECT * FROM action_requests WHERE idempotency_key = ?",
                (idempotency_key,),
            ) as cursor:
                row = await cursor.fetchone()
        return _request_record_from_row(row) if row is not None else None

    async def list_pending_approval_requests(
        self,
        *,
        limit: int = 100,
        expire_as_of: datetime | None = None,
    ) -> Sequence[ApprovalRequestRecord]:
        self._validate_limit(limit, label="approval request")
        await self.expire_stale(now=expire_as_of or self._now_utc())
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT * FROM action_requests
                WHERE status = 'pending'
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [_request_record_from_row(row) for row in rows]

    async def record_approval_decision(
        self,
        decision: ApprovalDecision,
    ) -> ApprovalRequestRecord:
        """Record an exact approval or denial; conflicting retries fail closed."""
        decision = _revalidate(ApprovalDecision, decision)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                record = await self._select_request_record(
                    connection, approval_id=decision.approval_id
                )
                if record is None:
                    raise KeyError(f"approval request does not exist: {decision.approval_id}")
                self._validate_decision(record.request, decision)
                target = ApprovalStatus.APPROVED if decision.approved else ApprovalStatus.DENIED
                if record.decision is not None:
                    if record.decision != decision or record.status is not target:
                        raise ActionStoreConflictError(
                            "approval already has a different exact decision"
                        )
                    await connection.commit()
                    return record
                if record.status is not ApprovalStatus.PENDING:
                    raise ActionStoreStateError(
                        f"approval cannot be decided from state {record.status.value}"
                    )
                await connection.execute(
                    """
                    UPDATE action_requests
                    SET status = ?, decision_json = ?, updated_at = ?
                    WHERE approval_id = ? AND status = 'pending' AND decision_json IS NULL
                    """,
                    (
                        target.value,
                        decision.model_dump_json(),
                        _timestamp(decision.decided_at),
                        decision.approval_id,
                    ),
                )
                await self._append_lifecycle_event(
                    connection,
                    record=record,
                    event_type=(
                        ActionLifecycleEventType.APPROVED
                        if decision.approved
                        else ActionLifecycleEventType.DENIED
                    ),
                    occurred_at=decision.decided_at,
                    reason_code=None if decision.approved else "approval_denied",
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        updated = await self.get_approval_request(decision.approval_id)
        assert updated is not None
        return updated

    async def record_denial(self, decision: ApprovalDecision) -> ApprovalRequestRecord:
        if decision.approved:
            raise ValueError("record_denial requires a denied ApprovalDecision")
        return await self.record_approval_decision(decision)

    async def expire_approval(
        self,
        approval_id: str,
        *,
        expired_at: datetime,
    ) -> bool:
        expired_at = _aware_utc(expired_at, field_name="expired_at")
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    "SELECT * FROM action_requests WHERE approval_id = ?",
                    (approval_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if row is None:
                    await connection.commit()
                    return False
                if expired_at < _parse_timestamp(row["expires_at"]):
                    raise ValueError("approval cannot expire before its stored expiry")
                cursor = await connection.execute(
                    """
                    UPDATE action_requests
                    SET status = 'expired', updated_at = ?
                    WHERE approval_id = ? AND status IN ('pending', 'approved')
                    """,
                    (_timestamp(expired_at), approval_id),
                )
                if cursor.rowcount == 1:
                    await self._append_lifecycle_event(
                        connection,
                        record=_request_record_from_row(row),
                        event_type=ActionLifecycleEventType.EXPIRED,
                        occurred_at=expired_at,
                        reason_code="approval_expired",
                    )
                await connection.commit()
                return cursor.rowcount == 1
            except BaseException:
                await connection.rollback()
                raise

    async def issue_grant(
        self,
        decision: ApprovalDecision,
        *,
        grant_id: str,
        nonce: str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> ApprovalGrant:
        """Atomically bind an approved decision to one exact, short-lived grant."""
        decision = _revalidate(ApprovalDecision, decision)
        issued_at = _aware_utc(issued_at, field_name="issued_at")
        expires_at = _aware_utc(expires_at, field_name="expires_at")
        if not decision.approved:
            raise ValueError("a denied decision cannot issue a grant")
        if issued_at < decision.decided_at:
            raise ValueError("grant cannot be issued before its approval decision")

        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                record = await self._select_request_record(
                    connection, approval_id=decision.approval_id
                )
                if record is None:
                    raise KeyError(f"approval request does not exist: {decision.approval_id}")
                self._validate_decision(record.request, decision)
                if expires_at > record.request.expires_at:
                    raise ValueError("grant cannot outlive its approval request")
                if record.status not in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}:
                    raise ActionStoreStateError(
                        f"grant cannot be issued from state {record.status.value}"
                    )
                if record.decision is not None and record.decision != decision:
                    raise ActionStoreConflictError(
                        "grant decision differs from the stored exact decision"
                    )

                grant = ApprovalGrant.create(
                    grant_id=grant_id,
                    approval_id=decision.approval_id,
                    action=record.request.action,
                    approved_by=decision.approver,
                    issued_at=issued_at,
                    expires_at=expires_at,
                    nonce=nonce,
                )
                async with connection.execute(
                    "SELECT grant_json, status FROM action_grants WHERE request_id = ?",
                    (grant.action.request_id,),
                ) as cursor:
                    existing_row = await cursor.fetchone()
                if existing_row is not None:
                    if existing_row["status"] != GrantStatus.ACTIVE.value:
                        raise ActionStoreStateError(
                            "approval request already has an inactive grant state"
                        )
                    existing = ApprovalGrant.model_validate_json(existing_row["grant_json"])
                    if existing != grant:
                        raise ActionStoreConflictError(
                            "approval request already has a different exact grant"
                        )
                    await connection.commit()
                    return existing

                await connection.execute(
                    """
                    UPDATE action_requests
                    SET status = 'approved', decision_json = ?, updated_at = ?
                    WHERE id = ? AND status IN ('pending', 'approved')
                    """,
                    (
                        decision.model_dump_json(),
                        _timestamp(decision.decided_at),
                        grant.action.request_id,
                    ),
                )
                await connection.execute(
                    """
                    INSERT INTO action_grants (
                        id, request_id, actor_id, session_id, device_id, action_id,
                        action_version, permission_level, policy_version, fingerprint, nonce,
                        idempotency_key, approval_id, approved_by, approved_by_json,
                        grant_fingerprint, grant_json, status, issued_at, expires_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?
                    )
                    """,
                    (
                        grant.grant_id,
                        grant.action.request_id,
                        grant.action.actor.host_id,
                        grant.action.actor.session_id,
                        grant.action.actor.device_id,
                        grant.action.action_id,
                        grant.action.action_version,
                        int(grant.action.permission_level),
                        grant.action.policy_version,
                        grant.action.fingerprint,
                        grant.nonce,
                        grant.action.idempotency_key,
                        grant.approval_id,
                        grant.approved_by.host_id,
                        grant.approved_by.model_dump_json(),
                        grant.grant_fingerprint,
                        grant.model_dump_json(),
                        _timestamp(grant.issued_at),
                        _timestamp(grant.expires_at),
                    ),
                )
                if record.decision is None:
                    await self._append_lifecycle_event(
                        connection,
                        record=record,
                        event_type=ActionLifecycleEventType.APPROVED,
                        occurred_at=decision.decided_at,
                    )
                await self._append_lifecycle_event(
                    connection,
                    record=record,
                    event_type=ActionLifecycleEventType.GRANT_ISSUED,
                    occurred_at=grant.issued_at,
                    grant_id=grant.grant_id,
                )
                await connection.commit()
                return grant
            except sqlite3.IntegrityError as error:
                await connection.rollback()
                raise ActionStoreConflictError(
                    "grant identifier, nonce, approval, or idempotency binding already exists"
                ) from error
            except BaseException:
                await connection.rollback()
                raise

    async def get_grant(self, grant_id: str) -> ApprovalGrant | None:
        record = await self.get_grant_record(grant_id)
        return record.grant if record is not None else None

    async def load_grant(self, grant_id: str) -> ApprovalGrant | None:
        """Alias emphasizing that the exact durable grant is revalidated on load."""
        return await self.get_grant(grant_id)

    async def get_grant_record(self, grant_id: str) -> GrantRecord | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT grant_json, status, claimed_at, revoked_at
                FROM action_grants WHERE id = ?
                """,
                (grant_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return _grant_record_from_row(row)

    async def get_grant_for_approval(self, approval_id: str) -> GrantRecord | None:
        """Load the unique exact grant issued for an approval lifecycle."""
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT grant_json, status, claimed_at, revoked_at
                FROM action_grants WHERE approval_id = ?
                """,
                (approval_id,),
            ) as cursor:
                row = await cursor.fetchone()
        return _grant_record_from_row(row) if row is not None else None

    async def revoke_grant(self, grant_id: str, *, revoked_at: datetime) -> bool:
        revoked_at = _aware_utc(revoked_at, field_name="revoked_at")
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    """
                    SELECT r.* FROM action_grants AS g
                    JOIN action_requests AS r ON r.id = g.request_id
                    WHERE g.id = ? AND g.status = 'active'
                    """,
                    (grant_id,),
                ) as record_cursor:
                    request_row = await record_cursor.fetchone()
                if request_row is None:
                    await connection.commit()
                    return False
                cursor = await connection.execute(
                    """
                    UPDATE action_grants
                    SET status = 'revoked', revoked_at = ?
                    WHERE id = ? AND status = 'active'
                    """,
                    (_timestamp(revoked_at), grant_id),
                )
                if cursor.rowcount != 1:
                    raise ActionStoreStateError("active grant changed during revocation")
                await self._append_lifecycle_event(
                    connection,
                    record=_request_record_from_row(request_row),
                    event_type=ActionLifecycleEventType.GRANT_REVOKED,
                    occurred_at=revoked_at,
                    grant_id=grant_id,
                    reason_code="grant_revoked",
                )
                await connection.commit()
                return True
            except BaseException:
                await connection.rollback()
                raise

    async def expire_stale(self, *, now: datetime | None = None) -> ExpirationResult:
        now = _aware_utc(now or self._now(), field_name="now")
        timestamp = _timestamp(now)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    """
                    SELECT * FROM action_requests
                    WHERE status IN ('pending', 'approved') AND expires_at <= ?
                    ORDER BY id
                    """,
                    (timestamp,),
                ) as request_cursor:
                    expired_request_rows = await request_cursor.fetchall()
                async with connection.execute(
                    """
                    SELECT r.*, g.id AS expired_grant_id
                    FROM action_grants AS g
                    JOIN action_requests AS r ON r.id = g.request_id
                    WHERE g.status = 'active' AND g.expires_at <= ?
                    ORDER BY g.id
                    """,
                    (timestamp,),
                ) as grant_cursor:
                    expired_grant_rows = await grant_cursor.fetchall()
                requests = await connection.execute(
                    """
                    UPDATE action_requests
                    SET status = 'expired', updated_at = ?
                    WHERE status IN ('pending', 'approved') AND expires_at <= ?
                    """,
                    (timestamp, timestamp),
                )
                grants = await connection.execute(
                    """
                    UPDATE action_grants
                    SET status = 'expired'
                    WHERE status = 'active' AND expires_at <= ?
                    """,
                    (timestamp,),
                )
                for row in expired_request_rows:
                    await self._append_lifecycle_event(
                        connection,
                        record=_request_record_from_row(row),
                        event_type=ActionLifecycleEventType.EXPIRED,
                        occurred_at=now,
                        reason_code="approval_expired",
                    )
                for row in expired_grant_rows:
                    await self._append_lifecycle_event(
                        connection,
                        record=_request_record_from_row(row),
                        event_type=ActionLifecycleEventType.GRANT_EXPIRED,
                        occurred_at=now,
                        grant_id=_require_text(row["expired_grant_id"]),
                        reason_code="grant_expired",
                    )
                await connection.commit()
                return ExpirationResult(
                    approval_requests=requests.rowcount,
                    grants=grants.rowcount,
                )
            except BaseException:
                await connection.rollback()
                raise

    async def claim_grant(self, grant: ApprovalGrant, *, claimed_at: datetime) -> bool:
        """Atomically claim one exact active grant across processes and restarts."""
        try:
            grant = _revalidate(ApprovalGrant, grant)
        except ValueError:
            return False
        claimed_at = _aware_utc(claimed_at, field_name="claimed_at")
        timestamp = _timestamp(claimed_at)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    "SELECT grant_json, status FROM action_grants WHERE id = ?",
                    (grant.grant_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if row is None:
                    await connection.commit()
                    return False
                stored = ApprovalGrant.model_validate_json(row["grant_json"])
                if stored != grant or row["status"] != GrantStatus.ACTIVE.value:
                    await connection.commit()
                    return False
                cursor = await connection.execute(
                    """
                    UPDATE action_grants
                    SET status = 'claimed', claimed_at = ?
                    WHERE id = ? AND status = 'active' AND expires_at > ?
                      AND grant_fingerprint = ? AND fingerprint = ?
                      AND actor_id = ? AND session_id = ? AND device_id = ?
                      AND policy_version = ? AND action_version = ?
                    """,
                    (
                        timestamp,
                        grant.grant_id,
                        timestamp,
                        grant.grant_fingerprint,
                        grant.action.fingerprint,
                        grant.action.actor.host_id,
                        grant.action.actor.session_id,
                        grant.action.actor.device_id,
                        grant.action.policy_version,
                        grant.action.action_version,
                    ),
                )
                if cursor.rowcount != 1:
                    await connection.execute(
                        """
                        UPDATE action_grants SET status = 'expired'
                        WHERE id = ? AND status = 'active' AND expires_at <= ?
                        """,
                        (grant.grant_id, timestamp),
                    )
                    await connection.commit()
                    return False
                request_cursor = await connection.execute(
                    """
                    UPDATE action_requests SET status = 'claimed', updated_at = ?
                    WHERE id = ? AND status = 'approved'
                    """,
                    (timestamp, grant.action.request_id),
                )
                if request_cursor.rowcount != 1:
                    raise ActionStoreStateError("grant request was not in approved state")
                async with connection.execute(
                    "SELECT * FROM action_requests WHERE id = ?",
                    (grant.action.request_id,),
                ) as lifecycle_cursor:
                    request_row = await lifecycle_cursor.fetchone()
                assert request_row is not None
                await self._append_lifecycle_event(
                    connection,
                    record=_request_record_from_row(request_row),
                    event_type=ActionLifecycleEventType.GRANT_CLAIMED,
                    occurred_at=claimed_at,
                    grant_id=grant.grant_id,
                )
                await connection.commit()
                return True
            except BaseException:
                await connection.rollback()
                raise

    async def get_receipt(self, idempotency_key: str) -> ExecutionReceipt | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                "SELECT receipt_json FROM action_executions WHERE idempotency_key = ?",
                (idempotency_key,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return ExecutionReceipt.model_validate_json(row["receipt_json"])

    async def complete_grant(
        self,
        grant: ApprovalGrant,
        receipt: ExecutionReceipt,
    ) -> None:
        """Persist exactly one terminal receipt and close the claimed request."""
        grant = _revalidate(ApprovalGrant, grant)
        receipt = _revalidate(ExecutionReceipt, receipt)
        self._validate_receipt_binding(grant, receipt)
        receipt_json = receipt.model_dump_json()
        if len(receipt_json.encode("utf-8")) > self._max_receipt_bytes:
            raise ValueError("execution receipt exceeds durable size limit")
        if receipt.result is not None:
            actual_result_bytes = len(canonical_json_bytes(receipt.result))
            if actual_result_bytes != receipt.result_bytes:
                raise ActionStoreConflictError("receipt result byte count is not exact")

        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    "SELECT grant_json, status FROM action_grants WHERE id = ?",
                    (grant.grant_id,),
                ) as cursor:
                    grant_row = await cursor.fetchone()
                if grant_row is None:
                    raise KeyError(f"grant does not exist: {grant.grant_id}")
                stored_grant = ApprovalGrant.model_validate_json(grant_row["grant_json"])
                if stored_grant != grant:
                    raise ActionStoreConflictError("receipt grant binding is not exact")

                async with connection.execute(
                    """
                    SELECT receipt_json FROM action_executions
                    WHERE idempotency_key = ? OR request_id = ? OR grant_id = ?
                    """,
                    (
                        receipt.idempotency_key,
                        receipt.request_id,
                        receipt.grant_id,
                    ),
                ) as cursor:
                    existing_row = await cursor.fetchone()
                if existing_row is not None:
                    existing = ExecutionReceipt.model_validate_json(existing_row["receipt_json"])
                    if existing != receipt:
                        raise ActionStoreConflictError(
                            "terminal receipt binding already has different exact data"
                        )
                    await connection.commit()
                    return
                if grant_row["status"] != GrantStatus.CLAIMED.value:
                    raise ActionStoreStateError("terminal receipt requires a claimed grant")

                execution_status = _execution_status(receipt)
                duration_ms = (receipt.finished_at - receipt.started_at).total_seconds() * 1_000
                await connection.execute(
                    """
                    INSERT INTO action_executions (
                        id, request_id, grant_id, idempotency_key, status, result_json,
                        postcondition_json, rollback_json, error_code, started_at,
                        completed_at, duration_ms, receipt_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt.receipt_id,
                        receipt.request_id,
                        receipt.grant_id,
                        receipt.idempotency_key,
                        execution_status,
                        canonical_json(receipt.result),
                        receipt.postcondition.model_dump_json(),
                        receipt.rollback.model_dump_json(),
                        receipt.error_code,
                        _timestamp(receipt.started_at),
                        _timestamp(receipt.finished_at),
                        duration_ms,
                        receipt_json,
                    ),
                )
                request_cursor = await connection.execute(
                    """
                    UPDATE action_requests SET status = ?, updated_at = ?
                    WHERE id = ? AND status = 'claimed'
                    """,
                    (
                        _request_terminal_status(receipt),
                        _timestamp(receipt.finished_at),
                        receipt.request_id,
                    ),
                )
                if request_cursor.rowcount != 1:
                    raise ActionStoreStateError("terminal receipt request was not in claimed state")
                async with connection.execute(
                    "SELECT * FROM action_requests WHERE id = ?",
                    (receipt.request_id,),
                ) as lifecycle_cursor:
                    request_row = await lifecycle_cursor.fetchone()
                assert request_row is not None
                await self._append_lifecycle_event(
                    connection,
                    record=_request_record_from_row(request_row),
                    event_type=_terminal_lifecycle_type(receipt),
                    occurred_at=receipt.finished_at,
                    grant_id=receipt.grant_id,
                    outcome=receipt.outcome,
                    reason_code=_safe_reason_code(receipt.error_code),
                )
                await connection.commit()
            except sqlite3.IntegrityError as error:
                await connection.rollback()
                raise ActionStoreConflictError(
                    "terminal receipt identifier or authority binding already exists"
                ) from error
            except BaseException:
                await connection.rollback()
                raise

    async def list_receipts(self, *, limit: int = 100) -> Sequence[ExecutionReceipt]:
        self._validate_limit(limit, label="receipt")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT receipt_json FROM action_executions
                ORDER BY started_at DESC, id DESC LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [ExecutionReceipt.model_validate_json(row["receipt_json"]) for row in rows]

    async def list_receipt_summaries(
        self,
        *,
        limit: int = 100,
    ) -> Sequence[ActionReceiptSummary]:
        """Return terminal metadata without loading private results into the viewer API."""
        self._validate_limit(limit, label="receipt summary")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT e.id, e.request_id, e.grant_id, e.error_code, e.completed_at,
                       r.action_id, r.action_version,
                       json_extract(e.receipt_json, '$.outcome') AS outcome,
                       json_extract(e.postcondition_json, '$.status') AS postcondition_status,
                       json_extract(e.rollback_json, '$.status') AS rollback_status
                FROM action_executions AS e
                JOIN action_requests AS r ON r.id = e.request_id
                ORDER BY e.completed_at DESC, e.id DESC LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            ActionReceiptSummary(
                receipt_id=_require_text(row["id"]),
                request_id=_require_text(row["request_id"]),
                grant_id=_require_text(row["grant_id"]),
                action_id=_require_text(row["action_id"]),
                action_version=_require_text(row["action_version"]),
                outcome=ExecutionOutcome(_require_text(row["outcome"])),
                postcondition_status=_require_text(row["postcondition_status"]),
                rollback_status=_require_text(row["rollback_status"]),
                reason_code=_safe_reason_code(
                    _require_text(row["error_code"]) if row["error_code"] is not None else None
                ),
                finished_at=_parse_timestamp(row["completed_at"]),
            )
            for row in rows
        ]

    async def list_lifecycle_events(
        self,
        *,
        limit: int = 100,
    ) -> Sequence[ActionLifecycleEvent]:
        """Return newest sanitized authority transitions with stable bounded ordering."""
        self._validate_limit(limit, label="lifecycle audit")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT * FROM action_lifecycle_events
                ORDER BY created_at DESC, id DESC LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [_lifecycle_event_from_row(row) for row in rows]

    async def append_action_event(self, event: ActionAuditEvent) -> None:
        """Append sanitized execution metadata; raw arguments/results are forbidden."""
        event = _revalidate(ActionAuditEvent, event)
        detail = _sanitize_audit_detail(event.detail)
        detail_json = canonical_json(detail)
        if len(detail_json.encode("utf-8")) > self._max_audit_detail_bytes:
            raise ValueError("action audit detail exceeds size limit")
        if len(event.model_dump_json().encode("utf-8")) > self._max_audit_event_bytes:
            raise ValueError("action audit event exceeds size limit")
        if event.sequence > self._max_audit_events_per_request:
            raise ValueError("action audit sequence exceeds per-request limit")

        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    "SELECT * FROM action_requests WHERE id = ?", (event.request_id,)
                ) as cursor:
                    request_row = await cursor.fetchone()
                if request_row is None:
                    raise KeyError(f"action request does not exist: {event.request_id}")
                if (
                    request_row["action_id"] != event.action_id
                    or request_row["action_version"] != event.action_version
                    or request_row["fingerprint"] != event.action_fingerprint
                ):
                    raise ActionStoreConflictError("audit event action binding is not exact")
                if event.type is not ActionAuditEventType.BROKER_REJECTED:
                    async with connection.execute(
                        """
                        SELECT 1 FROM action_grants
                        WHERE id = ? AND request_id = ? AND fingerprint = ?
                        """,
                        (event.grant_id, event.request_id, event.action_fingerprint),
                    ) as cursor:
                        if await cursor.fetchone() is None:
                            raise ActionStoreConflictError("audit event grant binding is not exact")
                async with connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
                    FROM action_audit_events WHERE request_id = ?
                    """,
                    (event.request_id,),
                ) as cursor:
                    sequence_row = await cursor.fetchone()
                assert sequence_row is not None
                if int(sequence_row["next_sequence"]) != event.sequence:
                    raise ActionAuditSequenceConflictError(
                        "audit sequence must be the exact next request sequence"
                    )
                await connection.execute(
                    """
                    INSERT INTO action_audit_events (
                        id, request_id, grant_id, sequence, event_type, action_id,
                        action_version, action_fingerprint, actor_id, session_id, device_id,
                        outcome, error_code, detail_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.request_id,
                        event.grant_id,
                        event.sequence,
                        event.type.value,
                        event.action_id,
                        event.action_version,
                        event.action_fingerprint,
                        request_row["actor_id"],
                        request_row["session_id"],
                        request_row["device_id"],
                        event.outcome.value if event.outcome is not None else None,
                        event.error_code,
                        detail_json,
                        _timestamp(event.occurred_at),
                    ),
                )
                lifecycle_type = {
                    ActionAuditEventType.BROKER_REJECTED: (
                        ActionLifecycleEventType.BROKER_REJECTED
                    ),
                    ActionAuditEventType.EXECUTION_STARTED: (
                        ActionLifecycleEventType.EXECUTION_STARTED
                    ),
                }.get(event.type)
                if lifecycle_type is not None:
                    await self._append_lifecycle_event(
                        connection,
                        record=_request_record_from_row(request_row),
                        event_type=lifecycle_type,
                        occurred_at=event.occurred_at,
                        grant_id=event.grant_id,
                        outcome=event.outcome,
                        reason_code=_safe_reason_code(event.error_code),
                    )
                await connection.commit()
            except sqlite3.IntegrityError as error:
                await connection.rollback()
                raise ActionStoreConflictError(
                    "audit event identifier or sequence already exists"
                ) from error
            except BaseException:
                await connection.rollback()
                raise

    async def list_action_events(
        self,
        request_id: str,
        *,
        limit: int = 100,
    ) -> Sequence[ActionAuditEvent]:
        self._validate_limit(limit, label="action audit")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT * FROM action_audit_events
                WHERE request_id = ? ORDER BY sequence ASC LIMIT ?
                """,
                (request_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return [_audit_event_from_row(row) for row in rows]

    async def list_action_event_summaries(
        self,
        *,
        limit: int = 100,
        request_id: str | None = None,
    ) -> Sequence[ActionAuditSummary]:
        """Return execution-event metadata without fingerprints, actors, or details."""
        self._validate_limit(limit, label="action audit summary")
        where = "WHERE request_id = ?" if request_id is not None else ""
        parameters: tuple[object, ...] = (request_id, limit) if request_id is not None else (limit,)
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                f"""
                SELECT id, event_type, request_id, grant_id, action_id, action_version,
                       outcome, error_code, created_at
                FROM action_audit_events {where}
                ORDER BY created_at DESC, id DESC LIMIT ?
                """,
                parameters,
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            ActionAuditSummary(
                event_id=_require_text(row["id"]),
                type=ActionAuditEventType(_require_text(row["event_type"])),
                request_id=_require_text(row["request_id"]),
                grant_id=_require_text(row["grant_id"]),
                action_id=_require_text(row["action_id"]),
                action_version=_require_text(row["action_version"]),
                outcome=(
                    ExecutionOutcome(_require_text(row["outcome"]))
                    if row["outcome"] is not None
                    else None
                ),
                reason_code=_safe_reason_code(
                    _require_text(row["error_code"]) if row["error_code"] is not None else None
                ),
                occurred_at=_parse_timestamp(row["created_at"]),
            )
            for row in rows
        ]

    async def record_control_intent(self, event: ControlIntentEvent) -> bool:
        """Persist an already-sanitized intent envelope; exact event IDs deduplicate."""
        event = _revalidate(ControlIntentEvent, event)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                cursor = await connection.execute(
                    """
                    INSERT OR IGNORE INTO control_intent_events (
                        event_id, actor_id, session_id, source, intent, outcome,
                        request_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.actor_id,
                        event.session_id,
                        event.source.value,
                        event.intent,
                        event.outcome.value,
                        event.request_id,
                        _timestamp(event.created_at),
                    ),
                )
                if cursor.rowcount == 1:
                    await connection.commit()
                    return True
                async with connection.execute(
                    "SELECT * FROM control_intent_events WHERE event_id = ?",
                    (event.event_id,),
                ) as existing_cursor:
                    row = await existing_cursor.fetchone()
                assert row is not None
                if _intent_event_from_row(row) != event:
                    raise ActionStoreConflictError(
                        "intent event identifier is bound to different exact data"
                    )
                await connection.commit()
                return False
            except BaseException:
                await connection.rollback()
                raise

    async def _append_lifecycle_event(
        self,
        connection: aiosqlite.Connection,
        *,
        record: ApprovalRequestRecord,
        event_type: ActionLifecycleEventType,
        occurred_at: datetime,
        grant_id: str | None = None,
        outcome: ExecutionOutcome | None = None,
        reason_code: str | None = None,
    ) -> ActionLifecycleEvent:
        """Append one sanitized transition inside the caller's active transaction."""
        async with connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
            FROM action_lifecycle_events WHERE request_id = ?
            """,
            (record.request.action.request_id,),
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        action = record.request.action
        event = ActionLifecycleEvent(
            event_id=f"lifecycle-{secrets.token_hex(16)}",
            sequence=int(_require_scalar(row["next_sequence"])),
            type=event_type,
            request_id=action.request_id,
            approval_id=record.request.approval_id,
            grant_id=grant_id,
            action_id=action.action_id,
            action_version=action.action_version,
            permission_level=action.permission_level,
            source=record.source,
            risk=record.risk,
            approval_rule=action.approval_rule,
            outcome=outcome,
            reason_code=_safe_reason_code(reason_code),
            occurred_at=occurred_at,
        )
        await connection.execute(
            """
            INSERT INTO action_lifecycle_events (
                id, request_id, sequence, event_type, approval_id, grant_id,
                action_id, action_version, permission_level, source, risk,
                approval_rule, outcome, reason_code, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.request_id,
                event.sequence,
                event.type.value,
                event.approval_id,
                event.grant_id,
                event.action_id,
                event.action_version,
                int(event.permission_level),
                event.source.value,
                event.risk.value,
                event.approval_rule.value,
                event.outcome.value if event.outcome is not None else None,
                event.reason_code,
                _timestamp(event.occurred_at),
            ),
        )
        return event

    async def _get_connection(self) -> aiosqlite.Connection:
        await self.initialize()
        connection = self._connection
        if connection is None:
            raise RuntimeError("SQLite action store is not initialized")
        return connection

    async def _select_request_record(
        self,
        connection: aiosqlite.Connection,
        *,
        approval_id: str,
    ) -> ApprovalRequestRecord | None:
        async with connection.execute(
            "SELECT * FROM action_requests WHERE approval_id = ?", (approval_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _request_record_from_row(row) if row is not None else None

    @staticmethod
    def _validate_decision(request: ApprovalRequest, decision: ApprovalDecision) -> None:
        if request.approval_id != decision.approval_id:
            raise ActionStoreConflictError("approval decision identifier does not match request")
        if request.action.fingerprint != decision.action_fingerprint:
            raise ActionStoreConflictError("approval decision fingerprint does not match request")
        if not decision.approver.same_identity(request.action.actor):
            raise ActionStoreConflictError(
                "approval decision actor, session, or device does not match request"
            )
        if decision.approver.interface is not InteractionInterface.LOCAL_CLI:
            raise ActionStoreConflictError("approval decision requires the trusted local CLI")
        if decision.approver.assurance < AuthenticationAssurance.LOCAL_SESSION:
            raise ActionStoreConflictError("approval decision requires an authenticated approver")
        if not set(request.action.actor.capabilities).issubset(decision.approver.capabilities):
            raise ActionStoreConflictError(
                "approval decision lost capabilities held by the proposal actor"
            )
        if decision.decided_at < request.requested_at:
            raise ActionStoreConflictError("approval decision predates its request")
        if decision.decided_at >= request.expires_at:
            raise ActionStoreStateError("approval request expired before its decision")

    @staticmethod
    def _validate_receipt_binding(grant: ApprovalGrant, receipt: ExecutionReceipt) -> None:
        action = grant.action
        if (
            receipt.grant_id != grant.grant_id
            or receipt.request_id != action.request_id
            or receipt.action_id != action.action_id
            or receipt.action_version != action.action_version
            or receipt.action_fingerprint != action.fingerprint
            or receipt.policy_version != action.policy_version
            or receipt.idempotency_key != action.idempotency_key
            or receipt.actor != action.actor
        ):
            raise ActionStoreConflictError("execution receipt authority binding is not exact")

    def _validate_limit(self, limit: int, *, label: str) -> None:
        if not 1 <= limit <= self._max_list_items:
            raise ValueError(f"{label} limit must be between 1 and {self._max_list_items}")

    def _now_utc(self) -> datetime:
        return _aware_utc(self._now(), field_name="action store clock")

    @staticmethod
    async def _apply_migrations(connection: aiosqlite.Connection) -> None:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            )
            """
        )
        await connection.commit()
        async with connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ) as cursor:
            applied = {int(row[0]): str(row[1]) for row in await cursor.fetchall()}

        migration_root = files("jarvis.memory.migrations")
        migrations: list[tuple[int, str, str]] = []
        for resource in migration_root.iterdir():
            match = _MIGRATION_PATTERN.fullmatch(resource.name)
            if match is None:
                continue
            migrations.append(
                (
                    int(match.group("version")),
                    resource.name,
                    resource.read_text(encoding="utf-8"),
                )
            )

        seen_versions: set[int] = set()
        for version, name, sql in sorted(migrations):
            if version in seen_versions:
                raise RuntimeError(f"duplicate SQLite migration version: {version:03d}")
            seen_versions.add(version)
            applied_name = applied.get(version)
            if applied_name is not None:
                if applied_name != name:
                    raise RuntimeError(
                        f"migration {version:03d} was applied as {applied_name!r}, not {name!r}"
                    )
                continue
            timestamp = _timestamp(datetime.now(UTC))
            script = (
                "BEGIN IMMEDIATE;\n"
                f"{sql.rstrip()}\n"
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES "
                f"({version}, {_sql_literal(name)}, {_sql_literal(timestamp)});\n"
                "COMMIT;"
            )
            try:
                await connection.executescript(script)
            except BaseException:
                await connection.rollback()
                raise


def _request_record_from_row(row: sqlite3.Row) -> ApprovalRequestRecord:
    raw_decision = row["decision_json"]
    return ApprovalRequestRecord(
        request=ApprovalRequest.model_validate_json(_require_text(row["request_json"])),
        source=ApprovalSource(_require_text(row["source"])),
        risk=ToolRisk(_require_text(row["risk"])),
        rule_id=_require_text(row["rule_id"]),
        status=ApprovalStatus(_require_text(row["status"])),
        decision=(
            ApprovalDecision.model_validate_json(_require_text(raw_decision))
            if raw_decision is not None
            else None
        ),
        updated_at=_parse_timestamp(row["updated_at"]),
    )


def _grant_record_from_row(row: sqlite3.Row) -> GrantRecord:
    return GrantRecord(
        grant=ApprovalGrant.model_validate_json(_require_text(row["grant_json"])),
        status=GrantStatus(_require_text(row["status"])),
        claimed_at=_optional_timestamp(row["claimed_at"]),
        revoked_at=_optional_timestamp(row["revoked_at"]),
    )


def _audit_event_from_row(row: sqlite3.Row) -> ActionAuditEvent:
    outcome = row["outcome"]
    return ActionAuditEvent(
        event_id=_require_text(row["id"]),
        sequence=int(_require_scalar(row["sequence"])),
        type=ActionAuditEventType(_require_text(row["event_type"])),
        request_id=_require_text(row["request_id"]),
        grant_id=_require_text(row["grant_id"]),
        action_id=_require_text(row["action_id"]),
        action_version=_require_text(row["action_version"]),
        action_fingerprint=_require_text(row["action_fingerprint"]),
        occurred_at=_parse_timestamp(row["created_at"]),
        outcome=ExecutionOutcome(_require_text(outcome)) if outcome is not None else None,
        error_code=_require_text(row["error_code"]) if row["error_code"] is not None else None,
        detail=json.loads(_require_text(row["detail_json"])),
    )


def _lifecycle_event_from_row(row: sqlite3.Row) -> ActionLifecycleEvent:
    outcome = row["outcome"]
    reason_code = row["reason_code"]
    grant_id = row["grant_id"]
    return ActionLifecycleEvent(
        event_id=_require_text(row["id"]),
        sequence=int(_require_scalar(row["sequence"])),
        type=ActionLifecycleEventType(_require_text(row["event_type"])),
        request_id=_require_text(row["request_id"]),
        approval_id=_require_text(row["approval_id"]),
        grant_id=_require_text(grant_id) if grant_id is not None else None,
        action_id=_require_text(row["action_id"]),
        action_version=_require_text(row["action_version"]),
        permission_level=PermissionLevel(int(_require_scalar(row["permission_level"]))),
        source=ApprovalSource(_require_text(row["source"])),
        risk=ToolRisk(_require_text(row["risk"])),
        approval_rule=ApprovalRule(_require_text(row["approval_rule"])),
        outcome=ExecutionOutcome(_require_text(outcome)) if outcome is not None else None,
        reason_code=_require_text(reason_code) if reason_code is not None else None,
        occurred_at=_parse_timestamp(row["created_at"]),
    )


def _intent_event_from_row(row: sqlite3.Row) -> ControlIntentEvent:
    return ControlIntentEvent(
        event_id=_require_text(row["event_id"]),
        actor_id=_require_text(row["actor_id"]),
        session_id=_require_text(row["session_id"]),
        source=ApprovalSource(_require_text(row["source"])),
        intent=_require_text(row["intent"]),
        outcome=ControlIntentOutcome(_require_text(row["outcome"])),
        request_id=(_require_text(row["request_id"]) if row["request_id"] is not None else None),
        created_at=_parse_timestamp(row["created_at"]),
    )


def _sanitize_audit_detail(detail: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    unknown = set(detail) - _SAFE_AUDIT_DETAIL_KEYS
    if unknown:
        raise ValueError(
            "action audit detail contains non-sanitized keys: " + ", ".join(sorted(unknown))
        )
    sanitized = dict(detail)
    result_bytes = sanitized.get("result_bytes")
    if result_bytes is not None and (
        isinstance(result_bytes, bool) or not isinstance(result_bytes, int) or result_bytes < 0
    ):
        raise ValueError("audit result_bytes must be a non-negative integer")
    duration = sanitized.get("duration_ms")
    if duration is not None and (
        isinstance(duration, bool) or not isinstance(duration, int | float) or duration < 0
    ):
        raise ValueError("audit duration_ms must be a non-negative number")
    for key in ("postcondition_status", "rollback_status", "reason_code"):
        value = sanitized.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 100):
            raise ValueError(f"audit {key} must be a string of at most 100 characters")
    return sanitized


def _execution_status(receipt: ExecutionReceipt) -> str:
    if receipt.rollback.status is RollbackStatus.SUCCEEDED:
        return "rolled_back"
    if receipt.outcome is ExecutionOutcome.SUCCEEDED:
        return "completed"
    if receipt.outcome is ExecutionOutcome.CANCELLED:
        return "cancelled"
    if receipt.outcome is ExecutionOutcome.UNCERTAIN:
        return "uncertain"
    return "failed"


def _request_terminal_status(receipt: ExecutionReceipt) -> str:
    return _execution_status(receipt)


def _terminal_lifecycle_type(receipt: ExecutionReceipt) -> ActionLifecycleEventType:
    if receipt.rollback.status is RollbackStatus.SUCCEEDED:
        return ActionLifecycleEventType.EXECUTION_ROLLED_BACK
    if receipt.outcome is ExecutionOutcome.SUCCEEDED:
        return ActionLifecycleEventType.EXECUTION_COMPLETED
    if receipt.outcome is ExecutionOutcome.CANCELLED:
        return ActionLifecycleEventType.EXECUTION_CANCELLED
    if receipt.outcome is ExecutionOutcome.UNCERTAIN:
        return ActionLifecycleEventType.EXECUTION_UNCERTAIN
    return ActionLifecycleEventType.EXECUTION_FAILED


def _safe_reason_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    if re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", normalized) is None:
        return "unsafe_reason_redacted"
    return normalized


def _revalidate(model: type[ModelT], value: ModelT) -> ModelT:
    return model.model_validate(value.model_dump())


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _aware_utc(value, field_name="timestamp").isoformat(timespec="microseconds")


def _parse_timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(_require_text(value))
    return _aware_utc(parsed, field_name="stored timestamp")


def _optional_timestamp(value: object) -> datetime | None:
    return _parse_timestamp(value) if value is not None else None


def _require_text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("stored SQLite value is not text")
    return value


def _require_scalar(value: object) -> str | bytes | int | float:
    if not isinstance(value, str | bytes | int | float):
        raise TypeError("stored SQLite value is not scalar")
    return value


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
