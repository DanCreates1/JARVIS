"""Reproducible Phase 9B backup, restore, shadow, cutover, and rollback benchmark."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import sqlite3
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jarvis.memory import SQLiteConversationStore
from jarvis.remote import (
    MigrationError,
    TopologyProfile,
    build_local_only_manifest,
    build_remote_manifest,
    compare_shadow,
    create_cutover_receipt,
    create_encrypted_backup,
    create_rollback_receipt,
    restore_encrypted_backup,
)

CYCLES = 100
CAPACITY_BYTES = 64 * 1_024 * 1_024
BACKUP_P95_LIMIT_MS = 2_000.0
RESTORE_P95_LIMIT_MS = 2_000.0
SHADOW_P95_LIMIT_MS = 1_000.0
TRANSITION_P95_LIMIT_MS = 100.0
RSS_GROWTH_LIMIT_MIB = 100.0
RUNTIME_ROOT = (Path(__file__).resolve().parents[1] / "runtime").resolve()
KEY = bytes(range(32))
KEY_ID = "phase9b-benchmark"
HOST_ID = "host:benchmark"
LAPTOP_ID = "node:laptop"
SERVER_ID = "node:server"


def _run(*, cycles: int, capacity_bytes: int) -> dict[str, Any]:
    if cycles < 1 or capacity_bytes < 1:
        raise ValueError("cycles and capacity bytes must be positive")
    remote = build_remote_manifest(
        profile=TopologyProfile.SPLIT,
        host_id=HOST_ID,
        server_node_id=SERVER_ID,
        laptop_node_id=LAPTOP_ID,
        server_capabilities=(
            "core.chat",
            "core.identity",
            "core.memory",
            "core.permissions",
            "core.research",
            "core.tasks",
        ),
        laptop_capabilities=("node.computer", "node.vision", "node.voice"),
        laptop_offline_capabilities=("node.voice",),
        epoch=40,
    )
    local = build_local_only_manifest(
        host_id=HOST_ID,
        node_id=LAPTOP_ID,
        capabilities=("core.chat", "node.voice"),
        epoch=41,
    )
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    backup_latencies: list[float] = []
    restore_latencies: list[float] = []
    shadow_latencies: list[float] = []
    transition_latencies: list[float] = []
    failures = 0
    false_accepts = 0
    mismatches = 0
    rss_start = _rss_bytes()

    with tempfile.TemporaryDirectory(prefix="phase9b-", dir=RUNTIME_ROOT) as raw_root:
        root = Path(raw_root)
        source = _database(root / "source.db", payload_bytes=256 * 1_024)
        for cycle in range(cycles):
            bundle = root / f"bundle-{cycle}.j9b"
            target = root / f"target-{cycle}.db"
            cutover = root / f"cutover-{cycle}.json"
            rollback = root / f"rollback-{cycle}.json"
            try:
                started = time.perf_counter_ns()
                backup = create_encrypted_backup(
                    source,
                    bundle,
                    topology=remote,
                    source_owner_node_id=LAPTOP_ID,
                    key=KEY,
                    key_id=KEY_ID,
                )
                backup_latencies.append(_elapsed_ms(started))

                started = time.perf_counter_ns()
                restore = restore_encrypted_backup(
                    bundle,
                    target,
                    topology=remote,
                    key=KEY,
                    expected_key_id=KEY_ID,
                )
                restore_latencies.append(_elapsed_ms(started))

                started = time.perf_counter_ns()
                comparison = compare_shadow(source, target)
                shadow_latencies.append(_elapsed_ms(started))
                if not comparison.matched or (
                    comparison.accepted_state_sha256 != backup.accepted_state_sha256
                    or restore.accepted_state_sha256 != backup.accepted_state_sha256
                ):
                    mismatches += 1

                started = time.perf_counter_ns()
                first = create_cutover_receipt(
                    source,
                    target,
                    cutover,
                    topology=remote,
                    source_owner_node_id=LAPTOP_ID,
                    accepted_state_sha256=backup.accepted_state_sha256,
                )
                create_rollback_receipt(
                    target,
                    source,
                    rollback,
                    topology=local,
                    previous_receipt=cutover,
                    accepted_state_sha256=backup.accepted_state_sha256,
                )
                transition_latencies.append(_elapsed_ms(started))
                if first.active_owner_node_id != SERVER_ID:
                    mismatches += 1

                corrupted = bytearray(bundle.read_bytes())
                corrupted[-1] ^= 0x01
                hostile = root / f"hostile-{cycle}.j9b"
                hostile.write_bytes(corrupted)
                try:
                    restore_encrypted_backup(
                        hostile,
                        root / f"hostile-{cycle}.db",
                        topology=remote,
                        key=KEY,
                        expected_key_id=KEY_ID,
                    )
                    false_accepts += 1
                except MigrationError:
                    pass
            except (MigrationError, OSError, sqlite3.Error):
                failures += 1

        capacity_source = _database(root / "capacity-source.db", payload_bytes=capacity_bytes)
        capacity_bundle = root / "capacity.j9b"
        capacity_target = root / "capacity-target.db"
        capacity_backup = create_encrypted_backup(
            capacity_source,
            capacity_bundle,
            topology=remote,
            source_owner_node_id=LAPTOP_ID,
            key=KEY,
            key_id=KEY_ID,
        )
        capacity_restore = restore_encrypted_backup(
            capacity_bundle,
            capacity_target,
            topology=remote,
            key=KEY,
            expected_key_id=KEY_ID,
        )
        capacity_shadow = compare_shadow(capacity_source, capacity_target)
        capacity_result = {
            "requested_payload_bytes": capacity_bytes,
            "database_bytes": capacity_restore.database_bytes,
            "bundle_bytes": capacity_backup.encrypted_bytes,
            "matched": capacity_shadow.matched,
        }

    rss_growth_mib = max(0, _rss_bytes() - rss_start) / (1_024 * 1_024)
    metrics = {
        "backup": _latencies(backup_latencies),
        "restore": _latencies(restore_latencies),
        "shadow": _latencies(shadow_latencies),
        "cutover_rollback": _latencies(transition_latencies),
    }
    result: dict[str, Any] = {
        "profile": "phase9b-migration-rehearsal-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "platform": sys.platform,
        "cycles": cycles,
        "operation_failures": failures,
        "corruption_attempts": cycles,
        "false_accepts": false_accepts,
        "data_mismatches": mismatches,
        "metrics_ms": metrics,
        "capacity": capacity_result,
        "rss_growth_mib": round(rss_growth_mib, 3),
        "thresholds": {
            "backup_p95_ms_max": BACKUP_P95_LIMIT_MS,
            "restore_p95_ms_max": RESTORE_P95_LIMIT_MS,
            "shadow_p95_ms_max": SHADOW_P95_LIMIT_MS,
            "cutover_rollback_p95_ms_max": TRANSITION_P95_LIMIT_MS,
            "rss_growth_mib_max": RSS_GROWTH_LIMIT_MIB,
            "operation_failures": 0,
            "false_accepts": 0,
            "data_mismatches": 0,
        },
    }
    result["passed"] = (
        cycles >= CYCLES
        and capacity_bytes >= CAPACITY_BYTES
        and failures == 0
        and false_accepts == 0
        and mismatches == 0
        and capacity_result["matched"] is True
        and metrics["backup"]["p95"] <= BACKUP_P95_LIMIT_MS
        and metrics["restore"]["p95"] <= RESTORE_P95_LIMIT_MS
        and metrics["shadow"]["p95"] <= SHADOW_P95_LIMIT_MS
        and metrics["cutover_rollback"]["p95"] <= TRANSITION_P95_LIMIT_MS
        and rss_growth_mib <= RSS_GROWTH_LIMIT_MIB
    )
    return result


def _database(path: Path, *, payload_bytes: int) -> Path:
    async def initialize() -> None:
        store = SQLiteConversationStore(path)
        await store.initialize()
        await store.close()

    asyncio.run(initialize())
    chunk_bytes = 16 * 1_024
    rows, remainder = divmod(payload_bytes, chunk_bytes)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE phase9b_benchmark_payload (id INTEGER PRIMARY KEY, payload BLOB NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO phase9b_benchmark_payload (payload) VALUES (zeroblob(?))",
            ((chunk_bytes,) for _ in range(rows)),
        )
        if remainder:
            connection.execute(
                "INSERT INTO phase9b_benchmark_payload (payload) VALUES (zeroblob(?))",
                (remainder,),
            )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return path


def _elapsed_ms(started: int) -> float:
    return (time.perf_counter_ns() - started) / 1_000_000


def _latencies(values: list[float]) -> dict[str, float]:
    return {
        "p50": round(statistics.median(values), 3),
        "p95": round(_percentile(values, 0.95), 3),
        "max": round(max(values), 3),
    }


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * quantile) - 1))
    return ordered[index]


def _rss_bytes() -> int:
    if os.name != "nt":
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1_024)

    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    process = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
    return int(counters.WorkingSetSize)


def _prepare_output_path(path: Path) -> Path:
    output = path.resolve()
    try:
        output.relative_to(RUNTIME_ROOT)
    except ValueError as exc:
        raise ValueError("benchmark output must stay under repository runtime") from exc
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("output path must be new and its parent must exist")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=CYCLES)
    parser.add_argument("--capacity-bytes", type=int, default=CAPACITY_BYTES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = _run(cycles=args.cycles, capacity_bytes=args.capacity_bytes)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        output = _prepare_output_path(args.output)
        with output.open("x", encoding="utf-8") as target:
            target.write(rendered + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
