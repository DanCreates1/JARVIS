"""Transactional host-isolated Phase 5 research source and claim ledger."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import uuid4

import aiosqlite
from pydantic import ValidationError

from jarvis.memory.sqlite_store import SQLiteConversationStore
from jarvis.research.models import (
    Citation,
    ClaimLifecycle,
    ClaimStatus,
    FetchedDocument,
    ParsedDocument,
    ResearchClaimRecord,
    ResearchConflict,
    ResearchConflictStatus,
    ResearchDeletionReceipt,
    ResearchExportReceipt,
    ResearchInterface,
    ResearchReport,
    ResearchReportState,
    SourceRecord,
    SourceState,
    StoredResearchReport,
    UnansweredQuestionRecord,
    UnansweredQuestionStatus,
)

_DEFAULT_BUSY_TIMEOUT_MS: Final = 5_000
_MAX_LIST_LIMIT: Final = 500
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


class ResearchStoreError(RuntimeError):
    """Base normalized research persistence error."""


class ResearchNotFoundError(ResearchStoreError):
    """Record is absent or belongs to another host."""


class ResearchStateError(ResearchStoreError):
    """Requested lifecycle transition is stale or invalid."""


class ResearchCorruptionError(ResearchStoreError):
    """Stored research data failed typed validation or integrity checks."""


class SQLiteResearchStore:
    """Own Phase 5 research persistence on a serialized SQLite connection."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        self._database_path = Path(database_path)
        self._busy_timeout_ms = busy_timeout_ms
        self._connection: aiosqlite.Connection | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()

    @property
    def database_path(self) -> Path:
        return self._database_path

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
                    raise ResearchCorruptionError("SQLite quick_check failed")
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

    async def __aenter__(self) -> SQLiteResearchStore:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    async def record_document(
        self,
        *,
        host_id: str,
        topic: str,
        fetched: FetchedDocument,
        parsed: ParsedDocument,
        usage_notes: str = "",
        now: datetime | None = None,
    ) -> SourceRecord:
        """Record exact acquired content, creating a new immutable version when content changes."""
        if parsed.source_url != fetched.final_url:
            raise ResearchStateError("parsed source URL does not match fetched final URL")
        timestamp = _as_utc(now or fetched.retrieved_at)
        digest = hashlib.sha256(fetched.body).hexdigest()
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                exact = await _fetchone(
                    connection,
                    "SELECT * FROM research_sources WHERE host_id = ? AND url = ? "
                    "AND content_sha256 = ? AND state = 'active' ORDER BY version DESC LIMIT 1",
                    (host_id, fetched.final_url, digest),
                )
                if exact is not None:
                    await connection.execute(
                        "UPDATE research_sources SET last_checked_at = ?, "
                        "etag = COALESCE(?, etag), last_modified = COALESCE(?, last_modified) "
                        "WHERE id = ?",
                        (
                            _timestamp(timestamp),
                            fetched.etag,
                            fetched.last_modified,
                            exact["id"],
                        ),
                    )
                    await self._append_event(
                        connection,
                        host_id=host_id,
                        resource_type="source",
                        resource_id=exact["id"],
                        event_type="source_revalidated",
                        reason_code="content_unchanged",
                        now=timestamp,
                    )
                    await connection.commit()
                    refreshed = await _fetchone(
                        connection, "SELECT * FROM research_sources WHERE id = ?", (exact["id"],)
                    )
                    assert refreshed is not None
                    return _row_to_source(refreshed)

                latest = await _fetchone(
                    connection,
                    "SELECT * FROM research_sources WHERE host_id = ? AND url = ? "
                    "ORDER BY version DESC LIMIT 1",
                    (host_id, fetched.final_url),
                )
                version = int(latest["version"]) + 1 if latest is not None else 1
                supersedes_id = str(latest["id"]) if latest is not None else None
                if latest is not None:
                    await connection.execute(
                        "UPDATE research_sources SET state = 'stale', last_checked_at = ? "
                        "WHERE host_id = ? AND url = ? AND state = 'active'",
                        (_timestamp(timestamp), host_id, fetched.final_url),
                    )
                    await self._stale_claims_for_url(
                        connection,
                        host_id=host_id,
                        url=fetched.final_url,
                        now=timestamp,
                        reason_code="source_content_changed",
                    )
                source_id = str(uuid4())
                source = SourceRecord(
                    id=source_id,
                    host_id=host_id,
                    url=fetched.final_url,
                    publisher=parsed.publisher,
                    title=parsed.title,
                    topic=topic,
                    media_type=fetched.media_type,
                    content_sha256=digest,
                    extracted_text=parsed.text,
                    retrieved_at=fetched.retrieved_at,
                    published_at=parsed.published_at,
                    last_checked_at=timestamp,
                    usage_notes=usage_notes,
                    state=SourceState.ACTIVE,
                    version=version,
                    supersedes_id=supersedes_id,
                    etag=fetched.etag,
                    last_modified=fetched.last_modified,
                )
                await connection.execute(
                    """
                    INSERT INTO research_sources (
                        id, host_id, url, publisher, title, topic, media_type, content_sha256,
                        extracted_text, retrieved_at, published_at, last_checked_at, usage_notes,
                        state, version, supersedes_id, etag, last_modified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _source_values(source),
                )
                await self._append_event(
                    connection,
                    host_id=host_id,
                    resource_type="source",
                    resource_id=source.id,
                    event_type="source_updated" if latest is not None else "source_recorded",
                    reason_code="content_changed" if latest is not None else "new_source",
                    now=timestamp,
                )
                await connection.commit()
                return source
            except BaseException:
                await connection.rollback()
                raise

    async def mark_source_unavailable(
        self,
        *,
        host_id: str,
        source_id: str,
        reason_code: str,
        now: datetime | None = None,
    ) -> SourceRecord:
        timestamp = _as_utc(now)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                row = await self._source_row(connection, host_id, source_id)
                if row is None:
                    raise ResearchNotFoundError("research source not found")
                await connection.execute(
                    "UPDATE research_sources SET state = 'unavailable', last_checked_at = ? "
                    "WHERE id = ?",
                    (_timestamp(timestamp), source_id),
                )
                await self._stale_claims_for_source(
                    connection,
                    host_id=host_id,
                    source_id=source_id,
                    now=timestamp,
                    reason_code="source_unavailable",
                )
                await self._append_event(
                    connection,
                    host_id=host_id,
                    resource_type="source",
                    resource_id=source_id,
                    event_type="source_unavailable",
                    reason_code=reason_code,
                    now=timestamp,
                )
                await connection.commit()
                updated = await _fetchone(
                    connection, "SELECT * FROM research_sources WHERE id = ?", (source_id,)
                )
                assert updated is not None
                return _row_to_source(updated)
            except BaseException:
                await connection.rollback()
                raise

    async def get_source(self, *, host_id: str, source_id: str) -> SourceRecord | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            row = await self._source_row(connection, host_id, source_id)
            return None if row is None else _row_to_source(row)

    async def list_sources(
        self,
        *,
        host_id: str,
        state: SourceState | None = None,
        limit: int = 100,
    ) -> Sequence[SourceRecord]:
        _check_limit(limit)
        sql = "SELECT * FROM research_sources WHERE host_id = ?"
        values: list[object] = [host_id]
        if state is not None:
            sql += " AND state = ?"
            values.append(state.value)
        sql += " ORDER BY retrieved_at DESC, id DESC LIMIT ?"
        values.append(limit)
        async with self._operation_lock:
            connection = await self._get_connection()
            rows = await _fetchall(connection, sql, values)
        return tuple(_row_to_source(row) for row in rows)

    async def search_sources(
        self, *, host_id: str, text: str, limit: int = 20
    ) -> Sequence[SourceRecord]:
        _check_limit(limit)
        terms = tuple(dict.fromkeys(token.casefold() for token in _TOKEN.findall(text)))[:20]
        if not terms:
            return ()
        expression = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
        async with self._operation_lock:
            connection = await self._get_connection()
            rows = await _fetchall(
                connection,
                """
                SELECT source.*
                FROM research_source_fts AS fts
                JOIN research_sources AS source ON source.id = fts.source_id
                WHERE research_source_fts MATCH ? AND source.host_id = ? AND source.state = 'active'
                ORDER BY bm25(research_source_fts), source.retrieved_at DESC
                LIMIT ?
                """,
                (expression, host_id, limit),
            )
        return tuple(_row_to_source(row) for row in rows)

    async def add_claim(
        self,
        *,
        host_id: str,
        topic: str,
        statement: str,
        status: ClaimStatus,
        citations: Sequence[Citation] = (),
        is_material: bool = True,
        is_inference: bool = False,
        uncertainty: str = "",
        now: datetime | None = None,
    ) -> ResearchClaimRecord:
        timestamp = _as_utc(now)
        claim = ResearchClaimRecord(
            id=str(uuid4()),
            host_id=host_id,
            topic=topic,
            statement=statement,
            status=status,
            citations=tuple(citations),
            is_material=is_material,
            is_inference=is_inference,
            uncertainty=uncertainty,
            created_at=timestamp,
            updated_at=timestamp,
        )
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await self._validate_citations(connection, host_id, claim.citations)
                await self._insert_claim(connection, claim)
                await self._append_event(
                    connection,
                    host_id=host_id,
                    resource_type="claim",
                    resource_id=claim.id,
                    event_type="claim_recorded",
                    reason_code="explicit_research_record",
                    now=timestamp,
                )
                await connection.commit()
                return claim
            except BaseException:
                await connection.rollback()
                raise

    async def update_claim(
        self,
        *,
        host_id: str,
        claim_id: str,
        expected_version: int,
        statement: str,
        status: ClaimStatus,
        citations: Sequence[Citation],
        is_material: bool = True,
        is_inference: bool = False,
        uncertainty: str = "",
        now: datetime | None = None,
    ) -> ResearchClaimRecord:
        timestamp = _as_utc(now)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                old = await self._claim_row(connection, host_id, claim_id)
                if old is None:
                    raise ResearchNotFoundError("research claim not found")
                if old["lifecycle"] != ClaimLifecycle.ACTIVE.value:
                    raise ResearchStateError("only active research claims can be updated")
                if int(old["version"]) != expected_version:
                    raise ResearchStateError("research claim version changed")
                new_claim = ResearchClaimRecord(
                    id=str(uuid4()),
                    host_id=host_id,
                    topic=old["topic"],
                    statement=statement,
                    status=status,
                    citations=tuple(citations),
                    is_material=is_material,
                    is_inference=is_inference,
                    uncertainty=uncertainty,
                    version=expected_version + 1,
                    supersedes_id=claim_id,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                await self._validate_citations(connection, host_id, new_claim.citations)
                await connection.execute(
                    "UPDATE research_claims SET lifecycle = 'superseded', updated_at = ? "
                    "WHERE id = ?",
                    (_timestamp(timestamp), claim_id),
                )
                conflict_rows = await _fetchall(
                    connection,
                    "SELECT id FROM research_conflicts WHERE host_id = ? AND status = 'open' "
                    "AND (left_claim_id = ? OR right_claim_id = ?)",
                    (host_id, claim_id, claim_id),
                )
                await connection.execute(
                    "UPDATE research_conflicts SET status = 'dismissed', resolved_at = ? "
                    "WHERE host_id = ? AND status = 'open' "
                    "AND (left_claim_id = ? OR right_claim_id = ?)",
                    (_timestamp(timestamp), host_id, claim_id, claim_id),
                )
                for conflict_row in conflict_rows:
                    await self._append_event(
                        connection,
                        host_id=host_id,
                        resource_type="conflict",
                        resource_id=conflict_row["id"],
                        event_type="conflict_dismissed",
                        reason_code="claim_superseded",
                        now=timestamp,
                    )
                await self._insert_claim(connection, new_claim)
                await self._append_event(
                    connection,
                    host_id=host_id,
                    resource_type="claim",
                    resource_id=new_claim.id,
                    event_type="claim_updated",
                    reason_code="supersedes_prior_claim",
                    now=timestamp,
                )
                await connection.commit()
                return new_claim
            except BaseException:
                await connection.rollback()
                raise

    async def get_claim(self, *, host_id: str, claim_id: str) -> ResearchClaimRecord | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            row = await self._claim_row(connection, host_id, claim_id)
            if row is None:
                return None
            return await self._load_claim(connection, row)

    async def list_claims(
        self,
        *,
        host_id: str,
        lifecycle: ClaimLifecycle | None = ClaimLifecycle.ACTIVE,
        limit: int = 100,
    ) -> Sequence[ResearchClaimRecord]:
        _check_limit(limit)
        sql = "SELECT * FROM research_claims WHERE host_id = ?"
        values: list[object] = [host_id]
        if lifecycle is not None:
            sql += " AND lifecycle = ?"
            values.append(lifecycle.value)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        values.append(limit)
        async with self._operation_lock:
            connection = await self._get_connection()
            rows = await _fetchall(connection, sql, values)
            return tuple([await self._load_claim(connection, row) for row in rows])

    async def open_conflict(
        self,
        *,
        host_id: str,
        left_claim_id: str,
        right_claim_id: str,
        reason_code: str = "source_disagreement",
        now: datetime | None = None,
    ) -> ResearchConflict:
        if left_claim_id == right_claim_id:
            raise ResearchStateError("research conflict requires two distinct claims")
        left_id, right_id = sorted((left_claim_id, right_claim_id))
        timestamp = _as_utc(now)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                for claim_id in (left_id, right_id):
                    row = await self._claim_row(connection, host_id, claim_id)
                    if row is None:
                        raise ResearchNotFoundError("research claim not found")
                    if row["lifecycle"] != ClaimLifecycle.ACTIVE.value:
                        raise ResearchStateError("research conflicts require active claims")
                conflict = ResearchConflict(
                    id=str(uuid4()),
                    host_id=host_id,
                    left_claim_id=left_id,
                    right_claim_id=right_id,
                    status=ResearchConflictStatus.OPEN,
                    reason_code=reason_code,
                    created_at=timestamp,
                )
                await connection.execute(
                    """
                    INSERT INTO research_conflicts (
                        id, host_id, left_claim_id, right_claim_id, status, winner_claim_id,
                        reason_code, created_at, resolved_at
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, NULL)
                    """,
                    (
                        conflict.id,
                        host_id,
                        left_id,
                        right_id,
                        conflict.status.value,
                        reason_code,
                        _timestamp(timestamp),
                    ),
                )
                await self._append_event(
                    connection,
                    host_id=host_id,
                    resource_type="conflict",
                    resource_id=conflict.id,
                    event_type="conflict_opened",
                    reason_code=reason_code,
                    now=timestamp,
                )
                await connection.commit()
                return conflict
            except BaseException:
                await connection.rollback()
                raise

    async def list_conflicts(
        self,
        *,
        host_id: str,
        status: ResearchConflictStatus | None = None,
        limit: int = 100,
    ) -> Sequence[ResearchConflict]:
        _check_limit(limit)
        sql = "SELECT * FROM research_conflicts WHERE host_id = ?"
        values: list[object] = [host_id]
        if status is not None:
            sql += " AND status = ?"
            values.append(status.value)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        values.append(limit)
        async with self._operation_lock:
            connection = await self._get_connection()
            rows = await _fetchall(connection, sql, values)
        return tuple(_row_to_conflict(row) for row in rows)

    async def resolve_conflict(
        self,
        *,
        host_id: str,
        conflict_id: str,
        winner_claim_id: str,
        now: datetime | None = None,
    ) -> ResearchConflict:
        timestamp = _as_utc(now)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                row = await _fetchone(
                    connection,
                    "SELECT * FROM research_conflicts WHERE host_id = ? AND id = ?",
                    (host_id, conflict_id),
                )
                if row is None:
                    raise ResearchNotFoundError("research conflict not found")
                if row["status"] != ResearchConflictStatus.OPEN.value:
                    raise ResearchStateError("research conflict is not open")
                if winner_claim_id not in {row["left_claim_id"], row["right_claim_id"]}:
                    raise ResearchStateError("winner must be one of the conflicting claims")
                await connection.execute(
                    "UPDATE research_conflicts SET status = 'resolved', winner_claim_id = ?, "
                    "resolved_at = ? WHERE id = ?",
                    (winner_claim_id, _timestamp(timestamp), conflict_id),
                )
                await self._append_event(
                    connection,
                    host_id=host_id,
                    resource_type="conflict",
                    resource_id=conflict_id,
                    event_type="conflict_resolved",
                    reason_code="host_selected_winner",
                    now=timestamp,
                )
                await connection.commit()
                updated = await _fetchone(
                    connection, "SELECT * FROM research_conflicts WHERE id = ?", (conflict_id,)
                )
                assert updated is not None
                return _row_to_conflict(updated)
            except BaseException:
                await connection.rollback()
                raise

    async def store_approved_report(
        self,
        *,
        host_id: str,
        report: ResearchReport,
        report_sha256: str,
        interface: ResearchInterface,
        approved_at: datetime,
        supersedes_report_id: str | None = None,
    ) -> StoredResearchReport:
        """Atomically persist a reviewed report only after an exact host approval."""
        timestamp = _as_utc(approved_at)
        if any(source.host_id != host_id for source in report.sources):
            raise ResearchStateError("research report contains a source from another host")
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                duplicate = await _fetchone(
                    connection,
                    "SELECT id FROM research_reports WHERE host_id = ? AND report_sha256 = ?",
                    (host_id, report_sha256),
                )
                if duplicate is not None:
                    raise ResearchStateError("approved research report already exists")
                if supersedes_report_id is not None:
                    previous = await _fetchone(
                        connection,
                        "SELECT id, state FROM research_reports WHERE host_id = ? AND id = ?",
                        (host_id, supersedes_report_id),
                    )
                    if previous is None:
                        raise ResearchNotFoundError("superseded research report not found")
                    if previous["state"] != ResearchReportState.CURRENT.value:
                        raise ResearchStateError("superseded research report is not current")

                source_id_map: dict[str, str] = {}
                stored_sources: list[SourceRecord] = []
                for source_candidate in report.sources:
                    exact = await _fetchone(
                        connection,
                        "SELECT * FROM research_sources WHERE host_id = ? AND url = ? "
                        "AND content_sha256 = ? AND state = 'active' ORDER BY version DESC LIMIT 1",
                        (host_id, source_candidate.url, source_candidate.content_sha256),
                    )
                    if exact is not None:
                        await connection.execute(
                            "UPDATE research_sources SET last_checked_at = ?, "
                            "etag = COALESCE(?, etag), last_modified = COALESCE(?, last_modified) "
                            "WHERE id = ?",
                            (
                                _timestamp(source_candidate.last_checked_at),
                                source_candidate.etag,
                                source_candidate.last_modified,
                                exact["id"],
                            ),
                        )
                        stored = _row_to_source(exact).model_copy(
                            update={"last_checked_at": source_candidate.last_checked_at}
                        )
                        await self._append_event(
                            connection,
                            host_id=host_id,
                            resource_type="source",
                            resource_id=stored.id,
                            event_type="source_revalidated",
                            reason_code="approved_report_content_unchanged",
                            now=timestamp,
                        )
                    else:
                        latest = await _fetchone(
                            connection,
                            "SELECT * FROM research_sources WHERE host_id = ? AND url = ? "
                            "ORDER BY version DESC LIMIT 1",
                            (host_id, source_candidate.url),
                        )
                        version = int(latest["version"]) + 1 if latest is not None else 1
                        supersedes_id = str(latest["id"]) if latest is not None else None
                        if latest is not None:
                            await connection.execute(
                                "UPDATE research_sources SET state = 'stale', last_checked_at = ? "
                                "WHERE host_id = ? AND url = ? AND state = 'active'",
                                (_timestamp(timestamp), host_id, source_candidate.url),
                            )
                            await self._stale_claims_for_url(
                                connection,
                                host_id=host_id,
                                url=source_candidate.url,
                                now=timestamp,
                                reason_code="approved_source_content_changed",
                            )
                        stored = source_candidate.model_copy(
                            update={
                                "id": str(uuid4()),
                                "host_id": host_id,
                                "state": SourceState.ACTIVE,
                                "version": version,
                                "supersedes_id": supersedes_id,
                                "usage_notes": source_candidate.usage_notes
                                or "Stored after explicit host research approval",
                            }
                        )
                        await connection.execute(
                            """
                            INSERT INTO research_sources (
                                id, host_id, url, publisher, title, topic, media_type,
                                content_sha256, extracted_text, retrieved_at, published_at,
                                last_checked_at, usage_notes, state, version, supersedes_id,
                                etag, last_modified
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            _source_values(stored),
                        )
                        await self._append_event(
                            connection,
                            host_id=host_id,
                            resource_type="source",
                            resource_id=stored.id,
                            event_type="source_updated"
                            if latest is not None
                            else "source_recorded",
                            reason_code="explicit_report_approval",
                            now=timestamp,
                        )
                    source_id_map[source_candidate.id] = stored.id
                    stored_sources.append(stored)

                stored_claims: list[ResearchClaimRecord] = []
                for claim_candidate in report.claims:
                    claim = ResearchClaimRecord(
                        id=str(uuid4()),
                        host_id=host_id,
                        topic=report.objective[:500],
                        statement=claim_candidate.statement,
                        status=claim_candidate.status,
                        citations=tuple(
                            citation.model_copy(
                                update={"source_id": source_id_map[citation.source_id]}
                            )
                            for citation in claim_candidate.citations
                        ),
                        is_material=claim_candidate.is_material,
                        is_inference=claim_candidate.is_inference,
                        uncertainty=claim_candidate.uncertainty,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    await self._insert_claim(connection, claim)
                    await self._append_event(
                        connection,
                        host_id=host_id,
                        resource_type="claim",
                        resource_id=claim.id,
                        event_type="claim_recorded",
                        reason_code="explicit_report_approval",
                        now=timestamp,
                    )
                    stored_claims.append(claim)

                stored_answer = report.answer
                for pending_source_id, stored_source_id in source_id_map.items():
                    stored_answer = stored_answer.replace(
                        f"[source:{pending_source_id}]", f"[source:{stored_source_id}]"
                    )
                report_id = str(uuid4())
                if supersedes_report_id is not None:
                    await connection.execute(
                        "UPDATE research_reports SET state = 'superseded' WHERE id = ?",
                        (supersedes_report_id,),
                    )
                    await self._append_workflow_event(
                        connection,
                        host_id=host_id,
                        resource_type="report",
                        resource_id=supersedes_report_id,
                        event_type="report_superseded",
                        interface=interface,
                        now=timestamp,
                    )
                await connection.execute(
                    "INSERT INTO research_reports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        report_id,
                        host_id,
                        report.objective,
                        stored_answer,
                        report_sha256,
                        ResearchReportState.CURRENT.value,
                        supersedes_report_id,
                        interface.value,
                        _timestamp(timestamp),
                        _timestamp(report.generated_at),
                    ),
                )
                await connection.executemany(
                    "INSERT INTO research_report_sources VALUES (?, ?)",
                    [(report_id, source.id) for source in stored_sources],
                )
                await connection.executemany(
                    "INSERT INTO research_report_claims VALUES (?, ?)",
                    [(report_id, claim.id) for claim in stored_claims],
                )
                for question in report.unanswered_questions:
                    question_id = str(uuid4())
                    await connection.execute(
                        "INSERT INTO research_unanswered_questions "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            question_id,
                            host_id,
                            report_id,
                            question,
                            UnansweredQuestionStatus.OPEN.value,
                            None,
                            1,
                            _timestamp(timestamp),
                            _timestamp(timestamp),
                        ),
                    )
                    await self._append_workflow_event(
                        connection,
                        host_id=host_id,
                        resource_type="question",
                        resource_id=question_id,
                        event_type="question_opened",
                        interface=interface,
                        now=timestamp,
                    )
                await self._append_workflow_event(
                    connection,
                    host_id=host_id,
                    resource_type="report",
                    resource_id=report_id,
                    event_type="report_approved",
                    interface=interface,
                    now=timestamp,
                )
                await connection.commit()
                return StoredResearchReport(
                    id=report_id,
                    host_id=host_id,
                    objective=report.objective,
                    answer=stored_answer,
                    report_sha256=report_sha256,
                    state=ResearchReportState.CURRENT,
                    supersedes_id=supersedes_report_id,
                    source_ids=tuple(source.id for source in stored_sources),
                    claim_ids=tuple(claim.id for claim in stored_claims),
                    approved_interface=interface,
                    approved_at=timestamp,
                    generated_at=report.generated_at,
                )
            except BaseException:
                await connection.rollback()
                raise

    async def get_report(self, *, host_id: str, report_id: str) -> StoredResearchReport | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            row = await _fetchone(
                connection,
                "SELECT * FROM research_reports WHERE host_id = ? AND id = ?",
                (host_id, report_id),
            )
            return None if row is None else await self._load_report(connection, row)

    async def list_reports(
        self,
        *,
        host_id: str,
        state: ResearchReportState | None = None,
        limit: int = 100,
    ) -> Sequence[StoredResearchReport]:
        _check_limit(limit)
        sql = "SELECT * FROM research_reports WHERE host_id = ?"
        values: list[object] = [host_id]
        if state is not None:
            sql += " AND state = ?"
            values.append(state.value)
        sql += " ORDER BY generated_at DESC, id DESC LIMIT ?"
        values.append(limit)
        async with self._operation_lock:
            connection = await self._get_connection()
            rows = await _fetchall(connection, sql, values)
            return tuple([await self._load_report(connection, row) for row in rows])

    async def list_unanswered_questions(
        self,
        *,
        host_id: str,
        status: UnansweredQuestionStatus | None = UnansweredQuestionStatus.OPEN,
        limit: int = 100,
    ) -> Sequence[UnansweredQuestionRecord]:
        _check_limit(limit)
        sql = "SELECT * FROM research_unanswered_questions WHERE host_id = ?"
        values: list[object] = [host_id]
        if status is not None:
            sql += " AND status = ?"
            values.append(status.value)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        values.append(limit)
        async with self._operation_lock:
            connection = await self._get_connection()
            rows = await _fetchall(connection, sql, values)
            return tuple(_row_to_unanswered(row) for row in rows)

    async def update_unanswered_question(
        self,
        *,
        host_id: str,
        question_id: str,
        expected_version: int,
        status: UnansweredQuestionStatus,
        interface: ResearchInterface,
        answer_claim_id: str | None = None,
        now: datetime | None = None,
    ) -> UnansweredQuestionRecord:
        if status is UnansweredQuestionStatus.OPEN:
            raise ResearchStateError("unanswered question can only be answered or dismissed")
        timestamp = _as_utc(now)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                row = await _fetchone(
                    connection,
                    "SELECT * FROM research_unanswered_questions WHERE host_id = ? AND id = ?",
                    (host_id, question_id),
                )
                if row is None:
                    raise ResearchNotFoundError("unanswered research question not found")
                if int(row["version"]) != expected_version or row["status"] != "open":
                    raise ResearchStateError("unanswered research question changed or is closed")
                if status is UnansweredQuestionStatus.ANSWERED:
                    if answer_claim_id is None:
                        raise ResearchStateError("answered question requires an answer claim")
                    claim = await self._claim_row(connection, host_id, answer_claim_id)
                    if claim is None or claim["lifecycle"] != ClaimLifecycle.ACTIVE.value:
                        raise ResearchNotFoundError("answer research claim not found")
                elif answer_claim_id is not None:
                    raise ResearchStateError("dismissed question cannot reference an answer claim")
                await connection.execute(
                    "UPDATE research_unanswered_questions SET status = ?, answer_claim_id = ?, "
                    "version = version + 1, updated_at = ? WHERE id = ?",
                    (status.value, answer_claim_id, _timestamp(timestamp), question_id),
                )
                await self._append_workflow_event(
                    connection,
                    host_id=host_id,
                    resource_type="question",
                    resource_id=question_id,
                    event_type=(
                        "question_answered"
                        if status is UnansweredQuestionStatus.ANSWERED
                        else "question_dismissed"
                    ),
                    interface=interface,
                    now=timestamp,
                )
                await connection.commit()
                updated = await _fetchone(
                    connection,
                    "SELECT * FROM research_unanswered_questions WHERE id = ?",
                    (question_id,),
                )
                assert updated is not None
                return _row_to_unanswered(updated)
            except BaseException:
                await connection.rollback()
                raise

    async def delete_source(
        self,
        *,
        host_id: str,
        source_id: str,
        reason_code: str = "host_deleted",
        now: datetime | None = None,
    ) -> ResearchDeletionReceipt:
        """Delete every URL version and every claim derived from any deleted version."""
        timestamp = _as_utc(now)
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                requested = await self._source_row(connection, host_id, source_id)
                if requested is None:
                    raise ResearchNotFoundError("research source not found")
                source_rows = await _fetchall(
                    connection,
                    "SELECT id, version FROM research_sources WHERE host_id = ? AND url = ?",
                    (host_id, requested["url"]),
                )
                source_ids = tuple(str(row["id"]) for row in source_rows)
                placeholders = ",".join("?" for _ in source_ids)
                await connection.execute(
                    f"DELETE FROM research_reports WHERE host_id = ? AND id IN "
                    f"(SELECT report_id FROM research_report_sources WHERE source_id IN "
                    f"({placeholders}))",
                    (host_id, *source_ids),
                )
                claim_rows = await _fetchall(
                    connection,
                    f"SELECT DISTINCT claim.id, claim.version FROM research_claims AS claim "
                    f"JOIN research_claim_citations AS citation ON citation.claim_id = claim.id "
                    f"WHERE claim.host_id = ? AND citation.source_id IN ({placeholders})",
                    (host_id, *source_ids),
                )
                claim_ids = tuple(str(row["id"]) for row in claim_rows)
                citation_count = int(
                    await _scalar(
                        connection,
                        f"SELECT count(*) FROM research_claim_citations WHERE source_id IN "
                        f"({placeholders})",
                        source_ids,
                    )
                )
                fts_count = int(
                    await _scalar(
                        connection,
                        f"SELECT count(*) FROM research_source_fts WHERE source_id IN "
                        f"({placeholders})",
                        source_ids,
                    )
                )
                conflict_count = 0
                if claim_ids:
                    claim_placeholders = ",".join("?" for _ in claim_ids)
                    conflict_count = int(
                        await _scalar(
                            connection,
                            f"SELECT count(*) FROM research_conflicts WHERE left_claim_id IN "
                            f"({claim_placeholders}) OR right_claim_id IN ({claim_placeholders})",
                            (*claim_ids, *claim_ids),
                        )
                    )
                for row in claim_rows:
                    await connection.execute(
                        "INSERT INTO research_claim_tombstones VALUES (?, ?, ?, ?, ?)",
                        (
                            row["id"],
                            host_id,
                            row["version"],
                            reason_code,
                            _timestamp(timestamp),
                        ),
                    )
                    await self._append_event(
                        connection,
                        host_id=host_id,
                        resource_type="claim",
                        resource_id=row["id"],
                        event_type="claim_deleted",
                        reason_code=reason_code,
                        now=timestamp,
                    )
                for row in source_rows:
                    await connection.execute(
                        "INSERT INTO research_source_tombstones VALUES (?, ?, ?, ?, ?)",
                        (
                            row["id"],
                            host_id,
                            row["version"],
                            reason_code,
                            _timestamp(timestamp),
                        ),
                    )
                    await self._append_event(
                        connection,
                        host_id=host_id,
                        resource_type="source",
                        resource_id=row["id"],
                        event_type="source_deleted",
                        reason_code=reason_code,
                        now=timestamp,
                    )
                if claim_ids:
                    await connection.execute(
                        f"DELETE FROM research_claims WHERE id IN "
                        f"({','.join('?' for _ in claim_ids)})",
                        claim_ids,
                    )
                await connection.execute(
                    f"DELETE FROM research_sources WHERE id IN ({placeholders})", source_ids
                )
                await connection.commit()
                return ResearchDeletionReceipt(
                    host_id=host_id,
                    requested_source_id=source_id,
                    deleted_source_ids=source_ids,
                    deleted_claim_ids=claim_ids,
                    source_rows=len(source_ids),
                    claim_rows=len(claim_ids),
                    citation_rows=citation_count,
                    conflict_rows=conflict_count,
                    fts_rows=fts_count,
                    tombstones_written=len(source_ids) + len(claim_ids),
                    deleted_at=timestamp,
                )
            except BaseException:
                await connection.rollback()
                raise

    async def export_json(
        self, *, host_id: str, destination: str | Path, now: datetime | None = None
    ) -> ResearchExportReceipt:
        timestamp = _as_utc(now)
        path = Path(destination)
        async with self._operation_lock:
            connection = await self._get_connection()
            source_rows = await _fetchall(
                connection,
                "SELECT * FROM research_sources WHERE host_id = ? "
                "ORDER BY retrieved_at DESC, id DESC",
                (host_id,),
            )
            claim_rows = await _fetchall(
                connection,
                "SELECT * FROM research_claims WHERE host_id = ? ORDER BY updated_at DESC, id DESC",
                (host_id,),
            )
            conflict_rows = await _fetchall(
                connection,
                "SELECT * FROM research_conflicts WHERE host_id = ? "
                "ORDER BY created_at DESC, id DESC",
                (host_id,),
            )
            sources = tuple(_row_to_source(row) for row in source_rows)
            claims = tuple([await self._load_claim(connection, row) for row in claim_rows])
            conflicts = tuple(_row_to_conflict(row) for row in conflict_rows)
            payload = {
                "schema_version": 1,
                "host_id": host_id,
                "exported_at": _timestamp(timestamp),
                "sources": [source.model_dump(mode="json") for source in sources],
                "claims": [claim.model_dump(mode="json") for claim in claims],
                "conflicts": [conflict.model_dump(mode="json") for conflict in conflicts],
            }
            encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode(
                "utf-8"
            )
            resolved_path = await asyncio.to_thread(_write_export, path, encoded)
            await self._append_event(
                connection,
                host_id=host_id,
                resource_type="export",
                resource_id=str(uuid4()),
                event_type="exported",
                reason_code="explicit_local_export",
                now=timestamp,
            )
            await connection.commit()
        return ResearchExportReceipt(
            host_id=host_id,
            path=str(resolved_path),
            source_count=len(sources),
            claim_count=len(claims),
            conflict_count=len(conflicts),
            byte_count=len(encoded),
            exported_at=timestamp,
        )

    async def _get_connection(self) -> aiosqlite.Connection:
        await self.initialize()
        connection = self._connection
        if connection is None:
            raise RuntimeError("SQLite research store is not initialized")
        return connection

    @staticmethod
    async def _source_row(
        connection: aiosqlite.Connection, host_id: str, source_id: str
    ) -> aiosqlite.Row | None:
        return await _fetchone(
            connection,
            "SELECT * FROM research_sources WHERE host_id = ? AND id = ?",
            (host_id, source_id),
        )

    @staticmethod
    async def _claim_row(
        connection: aiosqlite.Connection, host_id: str, claim_id: str
    ) -> aiosqlite.Row | None:
        return await _fetchone(
            connection,
            "SELECT * FROM research_claims WHERE host_id = ? AND id = ?",
            (host_id, claim_id),
        )

    @staticmethod
    async def _load_report(
        connection: aiosqlite.Connection, row: aiosqlite.Row
    ) -> StoredResearchReport:
        source_rows = await _fetchall(
            connection,
            "SELECT source_id FROM research_report_sources WHERE report_id = ? ORDER BY source_id",
            (row["id"],),
        )
        claim_rows = await _fetchall(
            connection,
            "SELECT claim_id FROM research_report_claims WHERE report_id = ? ORDER BY claim_id",
            (row["id"],),
        )
        try:
            return StoredResearchReport(
                id=row["id"],
                host_id=row["host_id"],
                objective=row["objective"],
                answer=row["answer"],
                report_sha256=row["report_sha256"],
                state=row["state"],
                supersedes_id=row["supersedes_id"],
                source_ids=tuple(item["source_id"] for item in source_rows),
                claim_ids=tuple(item["claim_id"] for item in claim_rows),
                approved_interface=row["approved_interface"],
                approved_at=_parse_time(row["approved_at"]),
                generated_at=_parse_time(row["generated_at"]),
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise ResearchCorruptionError("invalid stored research report") from exc

    async def _validate_citations(
        self, connection: aiosqlite.Connection, host_id: str, citations: Sequence[Citation]
    ) -> None:
        for citation in citations:
            row = await self._source_row(connection, host_id, citation.source_id)
            if row is None:
                raise ResearchNotFoundError("research citation source not found")

    async def _stale_claims_for_url(
        self,
        connection: aiosqlite.Connection,
        *,
        host_id: str,
        url: str,
        now: datetime,
        reason_code: str,
    ) -> None:
        rows = await _fetchall(
            connection,
            "SELECT DISTINCT claim.id FROM research_claims AS claim "
            "JOIN research_claim_citations AS citation ON citation.claim_id = claim.id "
            "JOIN research_sources AS source ON source.id = citation.source_id "
            "WHERE claim.host_id = ? AND claim.lifecycle = 'active' "
            "AND claim.status != 'stale' AND source.url = ?",
            (host_id, url),
        )
        await self._stale_claim_rows(connection, host_id, rows, now, reason_code)

    async def _stale_claims_for_source(
        self,
        connection: aiosqlite.Connection,
        *,
        host_id: str,
        source_id: str,
        now: datetime,
        reason_code: str,
    ) -> None:
        rows = await _fetchall(
            connection,
            "SELECT DISTINCT claim.id FROM research_claims AS claim "
            "JOIN research_claim_citations AS citation ON citation.claim_id = claim.id "
            "WHERE claim.host_id = ? AND claim.lifecycle = 'active' "
            "AND claim.status != 'stale' AND citation.source_id = ?",
            (host_id, source_id),
        )
        await self._stale_claim_rows(connection, host_id, rows, now, reason_code)

    async def _stale_claim_rows(
        self,
        connection: aiosqlite.Connection,
        host_id: str,
        rows: Sequence[aiosqlite.Row],
        now: datetime,
        reason_code: str,
    ) -> None:
        for row in rows:
            await connection.execute(
                "UPDATE research_claims SET status = 'stale', updated_at = ? WHERE id = ?",
                (_timestamp(now), row["id"]),
            )
            await self._append_event(
                connection,
                host_id=host_id,
                resource_type="claim",
                resource_id=row["id"],
                event_type="claim_staled",
                reason_code=reason_code,
                now=now,
            )

    @staticmethod
    async def _insert_claim(connection: aiosqlite.Connection, claim: ResearchClaimRecord) -> None:
        await connection.execute(
            """
            INSERT INTO research_claims (
                id, host_id, topic, statement, status, lifecycle, is_material, is_inference,
                uncertainty, version, supersedes_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim.id,
                claim.host_id,
                claim.topic,
                claim.statement,
                claim.status.value,
                claim.lifecycle.value,
                int(claim.is_material),
                int(claim.is_inference),
                claim.uncertainty,
                claim.version,
                claim.supersedes_id,
                _timestamp(claim.created_at),
                _timestamp(claim.updated_at),
            ),
        )
        await connection.executemany(
            "INSERT INTO research_claim_citations (claim_id, source_id, locator, quote) "
            "VALUES (?, ?, ?, ?)",
            [
                (claim.id, citation.source_id, citation.locator, citation.quote)
                for citation in claim.citations
            ],
        )

    @staticmethod
    async def _load_claim(
        connection: aiosqlite.Connection, row: aiosqlite.Row
    ) -> ResearchClaimRecord:
        citation_rows = await _fetchall(
            connection,
            "SELECT source_id, locator, quote FROM research_claim_citations "
            "WHERE claim_id = ? ORDER BY source_id",
            (row["id"],),
        )
        try:
            return ResearchClaimRecord(
                id=row["id"],
                host_id=row["host_id"],
                topic=row["topic"],
                statement=row["statement"],
                status=row["status"],
                lifecycle=row["lifecycle"],
                citations=tuple(
                    Citation(
                        source_id=citation["source_id"],
                        locator=citation["locator"],
                        quote=citation["quote"],
                    )
                    for citation in citation_rows
                ),
                is_material=bool(row["is_material"]),
                is_inference=bool(row["is_inference"]),
                uncertainty=row["uncertainty"],
                version=int(row["version"]),
                supersedes_id=row["supersedes_id"],
                created_at=_parse_time(row["created_at"]),
                updated_at=_parse_time(row["updated_at"]),
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise ResearchCorruptionError("invalid research claim record") from exc

    @staticmethod
    async def _append_event(
        connection: aiosqlite.Connection,
        *,
        host_id: str,
        resource_type: str,
        resource_id: str,
        event_type: str,
        reason_code: str | None,
        now: datetime,
    ) -> None:
        await connection.execute(
            "INSERT INTO research_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                host_id,
                resource_type,
                resource_id,
                event_type,
                reason_code,
                _timestamp(now),
            ),
        )

    @staticmethod
    async def _append_workflow_event(
        connection: aiosqlite.Connection,
        *,
        host_id: str,
        resource_type: str,
        resource_id: str,
        event_type: str,
        interface: ResearchInterface | None,
        now: datetime,
    ) -> None:
        await connection.execute(
            "INSERT INTO research_workflow_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                host_id,
                resource_type,
                resource_id,
                event_type,
                None if interface is None else interface.value,
                _timestamp(now),
            ),
        )


def _row_to_source(row: aiosqlite.Row) -> SourceRecord:
    try:
        return SourceRecord(
            id=row["id"],
            host_id=row["host_id"],
            url=row["url"],
            publisher=row["publisher"],
            title=row["title"],
            topic=row["topic"],
            media_type=row["media_type"],
            content_sha256=row["content_sha256"],
            extracted_text=row["extracted_text"],
            retrieved_at=_parse_time(row["retrieved_at"]),
            published_at=_parse_optional_time(row["published_at"]),
            last_checked_at=_parse_time(row["last_checked_at"]),
            usage_notes=row["usage_notes"],
            state=row["state"],
            version=int(row["version"]),
            supersedes_id=row["supersedes_id"],
            etag=row["etag"],
            last_modified=row["last_modified"],
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise ResearchCorruptionError("invalid research source record") from exc


def _row_to_conflict(row: aiosqlite.Row) -> ResearchConflict:
    try:
        return ResearchConflict(
            id=row["id"],
            host_id=row["host_id"],
            left_claim_id=row["left_claim_id"],
            right_claim_id=row["right_claim_id"],
            status=row["status"],
            winner_claim_id=row["winner_claim_id"],
            reason_code=row["reason_code"],
            created_at=_parse_time(row["created_at"]),
            resolved_at=_parse_optional_time(row["resolved_at"]),
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise ResearchCorruptionError("invalid research conflict record") from exc


def _row_to_unanswered(row: aiosqlite.Row) -> UnansweredQuestionRecord:
    try:
        return UnansweredQuestionRecord(
            id=row["id"],
            host_id=row["host_id"],
            report_id=row["report_id"],
            question=row["question"],
            status=row["status"],
            answer_claim_id=row["answer_claim_id"],
            version=int(row["version"]),
            created_at=_parse_time(row["created_at"]),
            updated_at=_parse_time(row["updated_at"]),
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise ResearchCorruptionError("invalid unanswered research question") from exc


def _source_values(source: SourceRecord) -> tuple[object, ...]:
    return (
        source.id,
        source.host_id,
        source.url,
        source.publisher,
        source.title,
        source.topic,
        source.media_type,
        source.content_sha256,
        source.extracted_text,
        _timestamp(source.retrieved_at),
        _optional_timestamp(source.published_at),
        _timestamp(source.last_checked_at),
        source.usage_notes,
        source.state.value,
        source.version,
        source.supersedes_id,
        source.etag,
        source.last_modified,
    )


async def _fetchone(
    connection: aiosqlite.Connection, sql: str, values: Sequence[object]
) -> aiosqlite.Row | None:
    async with connection.execute(sql, values) as cursor:
        return await cursor.fetchone()


async def _fetchall(
    connection: aiosqlite.Connection, sql: str, values: Sequence[object]
) -> list[aiosqlite.Row]:
    async with connection.execute(sql, values) as cursor:
        return list(await cursor.fetchall())


async def _scalar(connection: aiosqlite.Connection, sql: str, values: Sequence[object]) -> int:
    row = await _fetchone(connection, sql, values)
    assert row is not None
    return int(row[0])


def _check_limit(limit: int) -> None:
    if not 1 <= limit <= _MAX_LIST_LIMIT:
        raise ValueError(f"limit must be between 1 and {_MAX_LIST_LIMIT}")


def _as_utc(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("research timestamps must be timezone-aware")
    return timestamp.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="microseconds")


def _optional_timestamp(value: datetime | None) -> str | None:
    return None if value is None else _timestamp(value)


def _parse_time(value: str) -> datetime:
    return _as_utc(datetime.fromisoformat(value))


def _parse_optional_time(value: str | None) -> datetime | None:
    return None if value is None else _parse_time(value)


def _write_export(path: Path, encoded: bytes) -> Path:
    resolved_path = path.resolve()
    with resolved_path.open("xb") as output:
        output.write(encoded)
    return resolved_path
