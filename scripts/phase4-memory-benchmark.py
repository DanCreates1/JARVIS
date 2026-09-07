"""Reproducible Phase 4 retrieval, latency, growth, concurrency, and deletion benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sqlite3
import statistics
import sys
import time
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Any, Final

from jarvis.memory import (
    MemoryCategory,
    MemoryQuery,
    SQLiteMemoryStore,
    explicit_provenance,
)

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
_RUNTIME_ROOT: Final = (_REPOSITORY_ROOT / "runtime").resolve()
_GOLDEN_PATH: Final = _REPOSITORY_ROOT / "tests" / "fixtures" / "phase4_memory_golden.json"
_HOST: Final = "host-phase4-benchmark"
_TARGETS: Final = {
    "precision": 0.90,
    "recall": 0.90,
    "accepted_hit_rate": 0.90,
    "false_recall": 0.05,
    "warm_p95_ms": 50.0,
    "storage_bytes_per_record": 16 * 1024,
    "deletion_completeness": 1.0,
    "cross_host_hits": 0,
    "concurrency_failures": 0,
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", default="phase4-memory-benchmark.json")
    parser.add_argument("--records", type=int, default=2_500)
    parser.add_argument("--queries", type=int, default=500)
    parser.add_argument("--concurrency-operations", type=int, default=100)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args(argv)
    if args.records < 2_500:
        parser.error("--records must be at least 2500")
    if args.queries < 500:
        parser.error("--queries must be at least 500")
    if args.concurrency_operations < 100:
        parser.error("--concurrency-operations must be at least 100")
    if Path(args.output).name != args.output or not args.output.endswith(".json"):
        parser.error("--output must be a plain JSON filename")
    return args


def prepare_work_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    try:
        resolved.relative_to(_RUNTIME_ROOT)
    except ValueError as exc:
        raise ValueError("work directory must be a new child of repository runtime/") from exc
    if resolved == _RUNTIME_ROOT or resolved.exists() or resolved.is_symlink():
        raise FileExistsError("work directory must be a new non-link child of runtime/")
    resolved.mkdir(parents=True)
    return resolved


async def run_benchmark(args: argparse.Namespace, work_dir: Path) -> dict[str, Any]:
    fixture = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    database = work_dir / "benchmark.db"
    store = SQLiteMemoryStore(database, busy_timeout_ms=10_000)
    await store.initialize()
    labels: dict[str, str] = {}
    try:
        for item in fixture["items"]:
            record = await store.remember(
                host_id=_HOST,
                category=MemoryCategory(item["category"]),
                key=item["key"],
                content=item["content"],
                confidence=item["confidence"],
                provenance=explicit_provenance(
                    source_id=f"golden:{item['label']}",
                    source_label="fixed synthetic Phase 4 golden fixture",
                ),
            )
            labels[item["label"]] = record.id
        filler_count = args.records - len(labels)
        for index in range(filler_count):
            await store.remember(
                host_id=_HOST,
                category=MemoryCategory.SEMANTIC,
                key=f"filler.{index}",
                content=(
                    f"Synthetic filler memory {index} for bounded storage corpus "
                    f"with unique token filler{index}"
                ),
                confidence=0.75,
                provenance=explicit_provenance(
                    source_id=f"filler:{index}",
                    source_label="fixed synthetic filler fixture",
                ),
            )

        quality = await evaluate_quality(store, fixture["queries"], labels)
        latency = await measure_latency(store, fixture["queries"], args.queries)
        cross_host = await store.search(
            MemoryQuery(host_id="host-phase4-other", text="FTS5 lexical baseline", limit=8)
        )
        deletion = await measure_deletion(store, database)
        backup = work_dir / "verified-backup.db"
        await store.backup_to(backup)
    finally:
        await store.close()

    storage_bytes = sum(
        path.stat().st_size
        for path in (database, database.with_name(database.name + "-wal"))
        if path.exists()
    )
    bytes_per_record = storage_bytes / args.records
    cold_latency = await measure_cold_latency(database, fixture["queries"][:20])
    concurrency = await measure_concurrency(database, operations=args.concurrency_operations)
    restore = await verify_restore(backup, labels["semantic_fts"])
    with closing(sqlite3.connect(database)) as connection:
        migration_versions = [
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        fts5 = bool(
            connection.execute("SELECT sqlite_compileoption_used('ENABLE_FTS5')").fetchone()[0]
        )

    metrics = {
        **quality,
        "warm_latency_ms": latency,
        "cold_latency_ms": cold_latency,
        "storage": {
            "records": args.records,
            "checkpointed_bytes": storage_bytes,
            "bytes_per_record": bytes_per_record,
        },
        "deletion": deletion,
        "cross_host_hits": len(cross_host),
        "concurrency": concurrency,
        "backup_restore": restore,
        "migration_versions": migration_versions,
        "integrity_check": integrity,
        "sqlite_fts5": fts5,
    }
    checks = {
        "precision": metrics["precision"] >= _TARGETS["precision"],
        "recall": metrics["recall"] >= _TARGETS["recall"],
        "accepted_hit_rate": (metrics["accepted_hit_rate"] >= _TARGETS["accepted_hit_rate"]),
        "false_recall": metrics["false_recall"] <= _TARGETS["false_recall"],
        "warm_p95_ms": latency["p95"] <= _TARGETS["warm_p95_ms"],
        "storage_bytes_per_record": (bytes_per_record <= _TARGETS["storage_bytes_per_record"]),
        "deletion_completeness": (deletion["completeness"] >= _TARGETS["deletion_completeness"]),
        "cross_host_hits": len(cross_host) == _TARGETS["cross_host_hits"],
        "concurrency_failures": (concurrency["failures"] == _TARGETS["concurrency_failures"]),
        "backup_restore": restore["passed"],
        "migration": migration_versions[:5] == [1, 2, 3, 4, 5],
        "integrity": integrity == "ok",
        "fts5": fts5,
    }
    return {
        "format": "jarvis-phase4-memory-benchmark-v1",
        "settings": {
            "records": args.records,
            "warm_queries": args.queries,
            "concurrency_operations": args.concurrency_operations,
            "retrieval_limit": 3,
            "retrieval_min_score": 0.55,
            "fts_tokenizer": "unicode61 remove_diacritics 2",
            "embeddings_enabled": False,
        },
        "targets": _TARGETS,
        "metrics": metrics,
        "embedding_decision": {
            "adopted": False,
            "candidate_samples": 0,
            "reason": (
                "FTS5 baseline is evaluated first. No local embedding dependency/model is added "
                "unless lexical recall misses the fixed target and a candidate proves at least "
                "five absolute recall points without precision, latency, storage, privacy, or "
                "backup regression."
            ),
        },
        "checks": checks,
        "passed": all(checks.values()),
        "runtime": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(),
        },
    }


async def evaluate_quality(
    store: SQLiteMemoryStore,
    queries: Sequence[dict[str, Any]],
    labels: dict[str, str],
) -> dict[str, float | int]:
    true_positive = 0
    retrieved = 0
    expected_total = 0
    positive_queries = 0
    accepted_queries = 0
    negative_queries = 0
    false_recall_queries = 0
    for case in queries:
        expected = {labels[label] for label in case["expected"]}
        hits = await store.search(
            MemoryQuery(
                host_id=_HOST,
                text=case["query"],
                limit=3,
                min_score=0.55,
            )
        )
        actual = {hit.item.id for hit in hits}
        true_positive += len(actual & expected)
        retrieved += len(actual)
        expected_total += len(expected)
        if expected:
            positive_queries += 1
            accepted_queries += int(bool(actual & expected))
        else:
            negative_queries += 1
            false_recall_queries += int(bool(actual))
    return {
        "golden_queries": len(queries),
        "precision": true_positive / retrieved if retrieved else 1.0,
        "recall": true_positive / expected_total if expected_total else 1.0,
        "accepted_hit_rate": (accepted_queries / positive_queries if positive_queries else 1.0),
        "false_recall": (false_recall_queries / negative_queries if negative_queries else 0.0),
    }


async def measure_latency(
    store: SQLiteMemoryStore,
    queries: Sequence[dict[str, Any]],
    samples: int,
) -> dict[str, float | int]:
    for case in queries[:20]:
        await store.search(MemoryQuery(host_id=_HOST, text=case["query"], limit=3, min_score=0.55))
    durations: list[float] = []
    for index in range(samples):
        case = queries[index % len(queries)]
        started = time.perf_counter_ns()
        await store.search(MemoryQuery(host_id=_HOST, text=case["query"], limit=3, min_score=0.55))
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
    return summarize(durations)


async def measure_cold_latency(
    database: Path,
    queries: Sequence[dict[str, Any]],
) -> dict[str, float | int]:
    durations: list[float] = []
    for case in queries:
        started = time.perf_counter_ns()
        store = SQLiteMemoryStore(database)
        await store.initialize()
        await store.search(MemoryQuery(host_id=_HOST, text=case["query"], limit=3, min_score=0.55))
        await store.close()
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
    return summarize(durations)


async def measure_deletion(
    store: SQLiteMemoryStore,
    database: Path,
) -> dict[str, float | int]:
    source = await store.remember(
        host_id=_HOST,
        category=MemoryCategory.SEMANTIC,
        key="benchmark.deletion.source",
        content="Synthetic deletion benchmark source marker 48f1",
        provenance=explicit_provenance(
            source_id="benchmark-deletion-source",
            source_label="synthetic deletion benchmark",
        ),
    )
    derived = await store.create_derived(
        host_id=_HOST,
        category=MemoryCategory.SEMANTIC,
        key="benchmark.deletion.derived",
        content="Synthetic deletion benchmark derived marker 71c3",
        source_memory_ids=(source.id,),
        derivation_type="summary",
    )
    receipt = await store.delete(host_id=_HOST, memory_id=source.id)
    connection = await store._get_connection()
    remaining = 0
    for table, column in (
        ("memory_items", "id"),
        ("memory_provenance", "memory_id"),
        ("memory_fts", "memory_id"),
    ):
        async with connection.execute(
            f"SELECT count(*) FROM {table} WHERE {column} IN (?, ?)",
            (source.id, derived.id),
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        remaining += int(row[0])
    expected_removed = 6
    observed_removed = expected_removed if remaining == 0 else expected_removed - remaining
    return {
        "requested_and_derived": 2,
        "canonical_rows": receipt.canonical_rows,
        "fts_rows": receipt.fts_rows,
        "provenance_rows": receipt.provenance_rows,
        "remaining_content_rows": remaining,
        "completeness": observed_removed / expected_removed,
        "database_bytes_observed": (await asyncio.to_thread(database.stat)).st_size,
    }


async def measure_concurrency(database: Path, *, operations: int) -> dict[str, int]:
    stores = [SQLiteMemoryStore(database, busy_timeout_ms=10_000) for _ in range(4)]
    for store in stores:
        await store.initialize()
    failures = 0
    ids: list[str] = []

    async def operation(index: int) -> None:
        nonlocal failures
        try:
            item = await stores[index % len(stores)].remember(
                host_id=f"host-concurrency-{index % 2}",
                category=MemoryCategory.TASK,
                key=f"concurrency.{index}",
                content=f"Synthetic concurrency operation {index}",
                provenance=explicit_provenance(
                    source_id=f"concurrency:{index}",
                    source_label="synthetic concurrency fixture",
                ),
            )
            ids.append(item.id)
        except Exception:
            failures += 1

    try:
        await asyncio.gather(*(operation(index) for index in range(operations)))
    finally:
        await asyncio.gather(*(store.close() for store in stores))
    return {
        "operations": operations,
        "failures": failures,
        "unique_committed_ids": len(set(ids)),
    }


async def verify_restore(backup: Path, expected_id: str) -> dict[str, bool]:
    async with SQLiteMemoryStore(backup) as store:
        item = await store.get(host_id=_HOST, memory_id=expected_id)
        return {"passed": item is not None and item.id == expected_id}


def summarize(samples: Sequence[float]) -> dict[str, float | int]:
    ordered = sorted(samples)
    return {
        "samples": len(ordered),
        "p50": statistics.median(ordered),
        "p95": ordered[max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))],
        "max": max(ordered),
    }


def write_result(path: Path, result: dict[str, Any]) -> None:
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        work_dir = prepare_work_dir(args.work_dir)
        result = asyncio.run(run_benchmark(args, work_dir))
        output = work_dir / args.output
        write_result(output, result)
    except Exception as exc:
        print(f"Phase 4 benchmark failed safely: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps({"passed": result["passed"], "output": str(output)}, sort_keys=True))
    return 0 if result["passed"] or not args.enforce else 1


if __name__ == "__main__":
    raise SystemExit(main())
