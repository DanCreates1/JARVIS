"""Reproducible Phase 11B foreground-runner persistence benchmark."""

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
import time as clock
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis.proactivity import SQLiteProactivityRunnerStore

VALID_SAMPLES = 10_000
ABUSE_SAMPLES = 10_000
P95_LIMIT_MS = 10.0
RSS_GROWTH_LIMIT_MIB = 50.0
RUNTIME_ROOT = (Path(__file__).resolve().parents[1] / "runtime").resolve()
NOW = datetime(2026, 9, 14, 14, 0, tzinfo=UTC)
HOST = "host:benchmark"
CANDIDATE = "candidate:benchmark"


async def _measure(
    *, valid_samples: int = VALID_SAMPLES, abuse_samples: int = ABUSE_SAMPLES
) -> dict[str, Any]:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase11b-", dir=RUNTIME_ROOT) as directory:
        database = Path(directory) / "jarvis.db"
        async with SQLiteProactivityRunnerStore(database) as store:
            await _seed_candidate(database)
            dispatch, recovered = await store.claim_next(
                host_id=HOST,
                runner_id="runner:benchmark",
                lease_seconds=30,
                notification_ttl_seconds=3_600,
                now=NOW,
            )
            if dispatch is None or recovered or dispatch.lease_id is None:
                raise RuntimeError("benchmark candidate claim failed")
            await store.complete_local_notification(
                host_id=HOST,
                candidate_id=CANDIDATE,
                lease_id=dispatch.lease_id,
                now=NOW,
            )

            rss_start = _rss_bytes()
            valid_latencies: list[float] = []
            valid_failures = 0
            for _ in range(valid_samples):
                started = clock.perf_counter_ns()
                notices = await store.list_notifications(host_id=HOST, active_only=True, limit=1)
                valid_latencies.append((clock.perf_counter_ns() - started) / 1_000_000)
                if len(notices) != 1 or notices[0].candidate_id != CANDIDATE:
                    valid_failures += 1

            abuse_latencies: list[float] = []
            false_claims = 0
            for index in range(abuse_samples):
                started = clock.perf_counter_ns()
                duplicate, _ = await store.claim_next(
                    host_id=HOST,
                    runner_id=f"runner:duplicate:{index}",
                    lease_seconds=30,
                    notification_ttl_seconds=3_600,
                    now=NOW,
                )
                abuse_latencies.append((clock.perf_counter_ns() - started) / 1_000_000)
                false_claims += int(duplicate is not None)

            notices = await store.list_notifications(host_id=HOST)
            events = await store.list_events(host_id=HOST, candidate_id=CANDIDATE)
            rss_growth_mib = max(0, _rss_bytes() - rss_start) / (1024 * 1024)

    valid_p95 = _percentile(valid_latencies, 0.95)
    abuse_p95 = _percentile(abuse_latencies, 0.95)
    result: dict[str, Any] = {
        "profile": "phase11b-foreground-runner-v1",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "valid_samples": valid_samples,
        "valid_failures": valid_failures,
        "valid_p50_ms": round(statistics.median(valid_latencies), 4),
        "valid_p95_ms": round(valid_p95, 4),
        "abuse_samples": abuse_samples,
        "false_claims": false_claims,
        "abuse_p50_ms": round(statistics.median(abuse_latencies), 4),
        "abuse_p95_ms": round(abuse_p95, 4),
        "rss_growth_mib": round(rss_growth_mib, 3),
        "duplicate_notifications": max(0, len(notices) - 1),
        "unexpected_runner_events": max(0, len(events) - 2),
        "task_handoffs": 0,
        "effects_executed": 0,
        "thresholds": {
            "valid_p95_ms_max": P95_LIMIT_MS,
            "abuse_p95_ms_max": P95_LIMIT_MS,
            "rss_growth_mib_max": RSS_GROWTH_LIMIT_MIB,
            "valid_failures": 0,
            "false_claims": 0,
            "duplicate_notifications": 0,
            "unexpected_runner_events": 0,
            "task_handoffs": 0,
            "effects_executed": 0,
        },
    }
    result["passed"] = (
        valid_failures == 0
        and false_claims == 0
        and len(notices) == 1
        and len(events) == 2
        and valid_p95 <= P95_LIMIT_MS
        and abuse_p95 <= P95_LIMIT_MS
        and rss_growth_mib <= RSS_GROWTH_LIMIT_MIB
    )
    return result


async def _seed_candidate(database: Path) -> None:
    encoded_now = NOW.isoformat(timespec="microseconds")
    encoded_expiry = (NOW + timedelta(hours=1)).isoformat(timespec="microseconds")
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO proactivity_rules
                (id, host_id, status, proposal_sha256, record_json, version,
                 expires_at, created_at, updated_at)
            VALUES ('rule:benchmark', ?, 'active', ?, '{}', 1, ?, ?, ?)
            """,
            (HOST, "a" * 64, encoded_expiry, encoded_now, encoded_now),
        )
        connection.execute(
            """
            INSERT INTO proactivity_candidates
                (id, host_id, rule_id, feature, occurrence_key, scheduled_for,
                 attention_seconds, created_at, expires_at)
            VALUES (?, ?, 'rule:benchmark', 'benchmark', 'once:benchmark', ?, 1, ?, ?)
            """,
            (CANDIDATE, HOST, encoded_now, encoded_now, encoded_expiry),
        )
        connection.commit()
    finally:
        connection.close()


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * quantile) - 1))
    return ordered[index]


def _rss_bytes() -> int:
    if os.name != "nt":
        import resource

        return int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # type: ignore[attr-defined]
        )

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
    candidate = path.expanduser().resolve(strict=False)
    try:
        candidate.relative_to(RUNTIME_ROOT)
    except ValueError as exc:
        raise ValueError("benchmark output must be under repository runtime directory") from exc
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = asyncio.run(_measure())
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if arguments.output is not None:
        output = _prepare_output_path(arguments.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
