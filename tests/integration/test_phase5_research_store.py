from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis.research import (
    Citation,
    ClaimLifecycle,
    ClaimStatus,
    FetchedDocument,
    ParsedDocument,
    ResearchConflictStatus,
    ResearchCorruptionError,
    ResearchNotFoundError,
    ResearchStateError,
    SourceState,
    SQLiteResearchStore,
)

HOST_A = "host-a"
HOST_B = "host-b"
NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def document(
    text: str,
    *,
    url: str = "https://docs.example.test/report",
    retrieved_at: datetime = NOW,
) -> tuple[FetchedDocument, ParsedDocument]:
    return (
        FetchedDocument(
            requested_url=url,
            final_url=url,
            media_type="text/plain",
            body=text.encode(),
            retrieved_at=retrieved_at,
            status_code=200,
            etag=f'"fixture-{len(text)}"',
            last_modified="Sat, 05 Sep 2026 12:00:00 GMT",
        ),
        ParsedDocument(
            source_url=url,
            title="Synthetic public report",
            text=text,
            publisher="Example Standards Body",
            published_at=datetime(2026, 9, 1, tzinfo=UTC),
            language="en",
        ),
    )


async def add_source(
    store: SQLiteResearchStore,
    text: str,
    *,
    host_id: str = HOST_A,
    url: str = "https://docs.example.test/report",
    now: datetime = NOW,
):  # type: ignore[no-untyped-def]
    fetched, parsed = document(text, url=url, retrieved_at=now)
    return await store.record_document(
        host_id=host_id,
        topic="synthetic standards",
        fetched=fetched,
        parsed=parsed,
        usage_notes="Compiled public fixture only",
        now=now,
    )


async def test_source_versioning_revalidation_search_and_restart(tmp_path: Path) -> None:
    database = tmp_path / "research.db"
    store = SQLiteResearchStore(database)
    await store.initialize()
    first = await add_source(store, "Alpha latency standard")
    same = await add_source(store, "Alpha latency standard", now=NOW + timedelta(minutes=1))
    assert same.id == first.id
    assert same.version == 1
    assert same.last_checked_at == NOW + timedelta(minutes=1)
    assert same.etag == f'"fixture-{len("Alpha latency standard")}"'
    assert same.last_modified == "Sat, 05 Sep 2026 12:00:00 GMT"

    claim = await store.add_claim(
        host_id=HOST_A,
        topic="synthetic standards",
        statement="The synthetic standard names alpha latency.",
        status=ClaimStatus.VERIFIED,
        citations=(Citation(source_id=first.id, locator="paragraph 1"),),
        now=NOW + timedelta(minutes=1),
    )
    second = await add_source(
        store,
        "Beta latency standard is current",
        now=NOW + timedelta(minutes=2),
    )
    assert second.version == 2
    assert second.supersedes_id == first.id
    assert (await store.get_source(host_id=HOST_A, source_id=first.id)).state is SourceState.STALE  # type: ignore[union-attr]
    assert (await store.get_claim(host_id=HOST_A, claim_id=claim.id)).status is ClaimStatus.STALE  # type: ignore[union-attr]
    assert not await store.search_sources(host_id=HOST_A, text="Alpha")
    assert (await store.search_sources(host_id=HOST_A, text="Beta"))[0].id == second.id

    recurrence = await add_source(
        store,
        "Alpha latency standard",
        now=NOW + timedelta(minutes=3),
    )
    assert recurrence.version == 3
    assert recurrence.id != first.id
    current_claim = await store.add_claim(
        host_id=HOST_A,
        topic="synthetic standards",
        statement="The recurring source again names alpha latency.",
        status=ClaimStatus.VERIFIED,
        citations=(Citation(source_id=recurrence.id, locator="paragraph 1"),),
        now=NOW + timedelta(minutes=3),
    )
    unavailable = await store.mark_source_unavailable(
        host_id=HOST_A,
        source_id=recurrence.id,
        reason_code="fixture_unavailable",
        now=NOW + timedelta(minutes=4),
    )
    assert unavailable.state is SourceState.UNAVAILABLE
    assert (
        await store.get_claim(host_id=HOST_A, claim_id=current_claim.id)
    ).status is ClaimStatus.STALE  # type: ignore[union-attr]
    assert not await store.search_sources(host_id=HOST_A, text="Alpha")
    await store.close()

    async with SQLiteResearchStore(database) as reopened:
        assert (await reopened.get_source(host_id=HOST_A, source_id=recurrence.id)).version == 3  # type: ignore[union-attr]
        assert len(await reopened.list_sources(host_id=HOST_A, state=None)) == 3


async def test_claim_versions_conflicts_and_evidence_boundaries(tmp_path: Path) -> None:
    async with SQLiteResearchStore(tmp_path / "research.db") as store:
        first_source = await add_source(store, "Source one")
        second_source = await add_source(
            store,
            "Source two",
            url="https://docs.example.test/second",
        )
        first_claim = await store.add_claim(
            host_id=HOST_A,
            topic="synthetic standards",
            statement="Source one supports value A.",
            status=ClaimStatus.VERIFIED,
            citations=(Citation(source_id=first_source.id, locator="section A"),),
            now=NOW,
        )
        second_claim = await store.add_claim(
            host_id=HOST_A,
            topic="synthetic standards",
            statement="Source two supports value B.",
            status=ClaimStatus.VERIFIED,
            citations=(Citation(source_id=second_source.id, locator="section B"),),
            now=NOW,
        )
        conflict = await store.open_conflict(
            host_id=HOST_A,
            left_claim_id=first_claim.id,
            right_claim_id=second_claim.id,
            now=NOW,
        )
        with pytest.raises(ResearchStateError, match="one of the conflicting claims"):
            await store.resolve_conflict(
                host_id=HOST_A,
                conflict_id=conflict.id,
                winner_claim_id="unrelated-claim",
            )
        resolved = await store.resolve_conflict(
            host_id=HOST_A,
            conflict_id=conflict.id,
            winner_claim_id=second_claim.id,
            now=NOW + timedelta(minutes=1),
        )
        assert resolved.status is ResearchConflictStatus.RESOLVED

        open_conflict = await store.open_conflict(
            host_id=HOST_A,
            left_claim_id=first_claim.id,
            right_claim_id=second_claim.id,
            reason_code="new_source_disagreement",
            now=NOW + timedelta(minutes=2),
        )
        updated = await store.update_claim(
            host_id=HOST_A,
            claim_id=first_claim.id,
            expected_version=1,
            statement="Updated source one claim.",
            status=ClaimStatus.LIKELY,
            citations=(Citation(source_id=first_source.id, locator="section A"),),
            now=NOW + timedelta(minutes=3),
        )
        assert updated.version == 2
        assert updated.supersedes_id == first_claim.id
        old = await store.get_claim(host_id=HOST_A, claim_id=first_claim.id)
        assert old is not None and old.lifecycle is ClaimLifecycle.SUPERSEDED
        dismissed = (await store.list_conflicts(host_id=HOST_A))[0]
        assert dismissed.id == open_conflict.id
        assert dismissed.status is ResearchConflictStatus.DISMISSED
        with pytest.raises(ResearchStateError, match="version changed"):
            await store.update_claim(
                host_id=HOST_A,
                claim_id=updated.id,
                expected_version=1,
                statement="Replay",
                status=ClaimStatus.LIKELY,
                citations=(Citation(source_id=first_source.id, locator="section A"),),
            )
        with pytest.raises(ResearchNotFoundError, match="citation source"):
            await store.add_claim(
                host_id=HOST_B,
                topic="cross host",
                statement="Cross-host citation attempt.",
                status=ClaimStatus.VERIFIED,
                citations=(Citation(source_id=first_source.id, locator="section A"),),
            )


async def test_host_isolation_and_transitive_source_deletion(tmp_path: Path) -> None:
    database = tmp_path / "research.db"
    async with SQLiteResearchStore(database) as store:
        source_v1 = await add_source(store, "Private synthetic marker one")
        source_v2 = await add_source(
            store,
            "Private synthetic marker two",
            now=NOW + timedelta(minutes=1),
        )
        other_source = await add_source(
            store,
            "Second source marker",
            url="https://docs.example.test/other",
        )
        claim_one = await store.add_claim(
            host_id=HOST_A,
            topic="deletion",
            statement="First version claim.",
            status=ClaimStatus.VERIFIED,
            citations=(Citation(source_id=source_v1.id, locator="line 1"),),
        )
        claim_two = await store.add_claim(
            host_id=HOST_A,
            topic="deletion",
            statement="Combined source claim.",
            status=ClaimStatus.VERIFIED,
            citations=(
                Citation(source_id=source_v2.id, locator="line 1"),
                Citation(source_id=other_source.id, locator="line 1"),
            ),
        )
        conflict = await store.open_conflict(
            host_id=HOST_A,
            left_claim_id=claim_one.id,
            right_claim_id=claim_two.id,
        )

        assert await store.get_source(host_id=HOST_B, source_id=source_v2.id) is None
        assert await store.get_claim(host_id=HOST_B, claim_id=claim_one.id) is None
        assert await store.list_sources(host_id=HOST_B) == ()
        assert await store.list_claims(host_id=HOST_B) == ()
        assert await store.list_conflicts(host_id=HOST_B) == ()
        assert await store.search_sources(host_id=HOST_B, text="marker") == ()
        with pytest.raises(ResearchNotFoundError):
            await store.delete_source(host_id=HOST_B, source_id=source_v2.id)

        receipt = await store.delete_source(host_id=HOST_A, source_id=source_v2.id)
        assert set(receipt.deleted_source_ids) == {source_v1.id, source_v2.id}
        assert set(receipt.deleted_claim_ids) == {claim_one.id, claim_two.id}
        assert receipt.conflict_rows == 1
        assert await store.get_source(host_id=HOST_A, source_id=source_v1.id) is None
        assert await store.get_source(host_id=HOST_A, source_id=source_v2.id) is None
        assert await store.get_claim(host_id=HOST_A, claim_id=claim_one.id) is None
        assert not await store.search_sources(host_id=HOST_A, text="Private")
        assert await store.get_source(host_id=HOST_A, source_id=other_source.id) is not None

    with closing(sqlite3.connect(database)) as connection:
        source_tombstones = connection.execute(
            "SELECT count(*) FROM research_source_tombstones"
        ).fetchone()[0]
        claim_tombstones = connection.execute(
            "SELECT count(*) FROM research_claim_tombstones"
        ).fetchone()[0]
        source_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(research_source_tombstones)")
        }
        claim_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(research_claim_tombstones)")
        }
        event_columns = {row[1] for row in connection.execute("PRAGMA table_info(research_events)")}
        remaining_conflicts = connection.execute(
            "SELECT count(*) FROM research_conflicts WHERE id = ?", (conflict.id,)
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE research_events SET reason_code = 'rewritten'")
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM research_events")
        connection.rollback()
    assert (source_tombstones, claim_tombstones, remaining_conflicts) == (2, 2, 0)
    assert "content_sha256" not in source_columns
    assert "extracted_text" not in source_columns
    assert "statement" not in claim_columns
    assert not {"content_sha256", "extracted_text", "statement"} & event_columns


async def test_host_scoped_export_and_corrupt_record_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "research.db"
    destination = tmp_path / "research-export.json"
    store = SQLiteResearchStore(database)
    await store.initialize()
    source_a = await add_source(store, "Export host A marker")
    await add_source(store, "Export host B marker", host_id=HOST_B)
    claim_a = await store.add_claim(
        host_id=HOST_A,
        topic="export",
        statement="Host A export claim.",
        status=ClaimStatus.VERIFIED,
        citations=(Citation(source_id=source_a.id, locator="line 1", quote="short quote"),),
    )
    receipt = await store.export_json(host_id=HOST_A, destination=destination)
    assert (receipt.source_count, receipt.claim_count, receipt.conflict_count) == (1, 1, 0)
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["host_id"] == HOST_A
    assert payload["sources"][0]["id"] == source_a.id
    assert payload["claims"][0]["id"] == claim_a.id
    assert "host-b" not in destination.read_text(encoding="utf-8").casefold()
    with pytest.raises(FileExistsError):
        await store.export_json(host_id=HOST_A, destination=destination)
    await store.close()

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE research_claim_citations SET quote = ? WHERE claim_id = ?",
            ("word " * 26, claim_a.id),
        )
        connection.commit()
    async with SQLiteResearchStore(database) as corrupt:
        with pytest.raises(ResearchCorruptionError, match="invalid research claim"):
            await corrupt.get_claim(host_id=HOST_A, claim_id=claim_a.id)


async def test_concurrent_connections_preserve_research_rows(tmp_path: Path) -> None:
    database = tmp_path / "research.db"
    stores = [SQLiteResearchStore(database, busy_timeout_ms=10_000) for _ in range(4)]
    for store in stores:
        await store.initialize()
    try:

        async def write(index: int) -> str:
            source = await add_source(
                stores[index % len(stores)],
                f"Concurrent fixture {index}",
                host_id=HOST_A if index % 2 == 0 else HOST_B,
                url=f"https://docs.example.test/concurrent/{index}",
            )
            return source.id

        source_ids = await asyncio.gather(*(write(index) for index in range(20)))
        assert len(set(source_ids)) == 20
        assert len(await stores[0].list_sources(host_id=HOST_A)) == 10
        assert len(await stores[1].list_sources(host_id=HOST_B)) == 10
    finally:
        await asyncio.gather(*(store.close() for store in stores))
