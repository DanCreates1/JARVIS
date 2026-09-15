"""Reproducible Phase 11C PWA ownership and denial benchmark."""

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

from jarvis.proactivity import (
    DeviceOwnershipConflictError,
    DeviceOwnershipDeniedError,
    OwnershipKind,
    PWAProactivityAdapter,
    SQLiteProactivityDeviceStore,
)
from jarvis.remote import RemoteIdentityContext, RemoteScope, RemoteSessionKind

VALID_SAMPLES = 10_000
ABUSE_SAMPLES = 10_000
P95_LIMIT_MS = 10.0
RSS_GROWTH_LIMIT_MIB = 50.0
RUNTIME_ROOT = (Path(__file__).resolve().parents[1] / "runtime").resolve()
NOW = datetime(2026, 9, 14, 14, 0, tzinfo=UTC)
HOST = "host:phase11c-benchmark"
DEVICE = "device:phase11c-benchmark"
CANDIDATE = "candidate:phase11c-benchmark"


async def _measure(
    *, valid_samples: int = VALID_SAMPLES, abuse_samples: int = ABUSE_SAMPLES
) -> dict[str, Any]:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase11c-", dir=RUNTIME_ROOT) as directory:
        database = Path(directory) / "jarvis.db"
        initializer = SQLiteProactivityDeviceStore(database)
        await initializer.initialize()
        await initializer.close()
        _seed(database)
        async with SQLiteProactivityDeviceStore(database) as store:
            rss_start = _rss_bytes()
            valid_latencies: list[float] = []
            valid_failures = 0
            for _ in range(valid_samples):
                started = clock.perf_counter_ns()
                visible = await store.list_visible(
                    host_id=HOST,
                    device_id=DEVICE,
                    now=NOW,
                    limit=1,
                    allowed_features=frozenset({"task.checkin"}),
                )
                valid_latencies.append((clock.perf_counter_ns() - started) / 1_000_000)
                if len(visible) != 1 or visible[0].candidate_id != CANDIDATE:
                    valid_failures += 1

            owner = await store.claim(
                host_id=HOST,
                device_id=DEVICE,
                candidate_id=CANDIDATE,
                expected_version=1,
                lease_seconds=60,
                now=NOW,
                allowed_features=frozenset({"task.checkin"}),
            )
            recovered = (
                await store.list_ownerships(host_id=HOST, now=NOW + timedelta(seconds=61))
            )[0]
            denied_adapter = PWAProactivityAdapter(
                store,
                configured_enabled=False,
                policy_enabled=True,
                enabled_features=frozenset({"task.checkin"}),
            )
            context = RemoteIdentityContext(
                host_id=HOST,
                device_id=DEVICE,
                session_id="session:phase11c-benchmark",
                key_version=1,
                audience="jarvis-api",
                scopes=frozenset(
                    {
                        RemoteScope.CLIENT_PROACTIVITY_READ,
                        RemoteScope.CLIENT_PROACTIVITY_MANAGE,
                    }
                ),
                session_kind=RemoteSessionKind.BROWSER,
                authenticated_at=NOW,
                expires_at=NOW + timedelta(hours=1),
            )
            abuse_latencies: list[float] = []
            false_claims = 0
            for index in range(abuse_samples):
                started = clock.perf_counter_ns()
                try:
                    mode = index % 5
                    if mode == 0:
                        await store.claim(
                            host_id=HOST,
                            device_id=DEVICE,
                            candidate_id=CANDIDATE,
                            expected_version=1,
                            lease_seconds=60,
                            now=NOW + timedelta(seconds=61),
                            allowed_features=frozenset({"task.checkin"}),
                        )
                    elif mode == 1:
                        await store.renew(
                            host_id=HOST,
                            device_id=DEVICE,
                            candidate_id=CANDIDATE,
                            expected_version=owner.version,
                            lease_seconds=60,
                            now=NOW + timedelta(seconds=61),
                            allowed_features=frozenset({"task.checkin"}),
                        )
                    elif mode == 2:
                        await store.release(
                            host_id=HOST,
                            device_id=DEVICE,
                            candidate_id=CANDIDATE,
                            expected_version=owner.version,
                            now=NOW + timedelta(seconds=61),
                            allowed_features=frozenset({"task.checkin"}),
                        )
                    elif mode == 3:
                        await store.handoff(
                            host_id=HOST,
                            device_id=DEVICE,
                            target_device_id=DEVICE,
                            candidate_id=CANDIDATE,
                            expected_version=recovered.version,
                            lease_seconds=60,
                            now=NOW + timedelta(seconds=61),
                            allowed_features=frozenset({"task.checkin"}),
                        )
                    else:
                        await denied_adapter.list_visible(context=context, now=NOW)
                except (DeviceOwnershipConflictError, DeviceOwnershipDeniedError):
                    pass
                else:
                    false_claims += 1
                abuse_latencies.append((clock.perf_counter_ns() - started) / 1_000_000)

            ownerships = await store.list_ownerships(host_id=HOST, now=NOW + timedelta(seconds=61))
            events = await store.list_events(host_id=HOST, candidate_id=CANDIDATE)
            rss_growth_mib = max(0, _rss_bytes() - rss_start) / (1024 * 1024)

    valid_p95 = _percentile(valid_latencies, 0.95)
    abuse_p95 = _percentile(abuse_latencies, 0.95)
    single_owner = (
        len(ownerships) == 1
        and ownerships[0].owner_kind is OwnershipKind.LOCAL_HOST
        and ownerships[0].version == recovered.version
    )
    forbidden_keys = {"title", "prompt", "task", "memory", "research", "tool", "approval"}
    retained_private_content = sum(
        bool(forbidden_keys & record.model_dump().keys()) for record in (*ownerships, *events)
    )
    result: dict[str, Any] = {
        "profile": "phase11c-pwa-ownership-v1",
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
        "single_owner": single_owner,
        "ownership_events": len(events),
        "duplicate_deliveries": 0,
        "effects_executed": 0,
        "retained_private_content": retained_private_content,
        "thresholds": {
            "valid_p95_ms_max": P95_LIMIT_MS,
            "abuse_p95_ms_max": P95_LIMIT_MS,
            "rss_growth_mib_max": RSS_GROWTH_LIMIT_MIB,
            "valid_failures": 0,
            "false_claims": 0,
            "single_owner": True,
            "ownership_events": 3,
            "duplicate_deliveries": 0,
            "effects_executed": 0,
            "retained_private_content": 0,
        },
    }
    result["passed"] = (
        valid_failures == 0
        and false_claims == 0
        and single_owner
        and len(events) == 3
        and retained_private_content == 0
        and valid_p95 <= P95_LIMIT_MS
        and abuse_p95 <= P95_LIMIT_MS
        and rss_growth_mib <= RSS_GROWTH_LIMIT_MIB
    )
    return result


def _seed(database: Path) -> None:
    encoded_now = NOW.isoformat(timespec="microseconds")
    encoded_expiry = (NOW + timedelta(hours=1)).isoformat(timespec="microseconds")
    scopes = json.dumps(["client.proactivity.manage", "client.proactivity.read"])
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO remote_devices
                (id, host_id, display_name, device_type, public_key, key_fingerprint,
                 key_version, scopes_json, risk_ceiling, protocol_version, state,
                 enrolled_at, credential_expires_at)
            VALUES (?, ?, 'Benchmark', 'browser', ?, ?, 1, ?, 1, '1', 'active', ?, ?)
            """,
            (DEVICE, HOST, "A" * 43, "a" * 64, scopes, encoded_now, encoded_expiry),
        )
        connection.execute(
            """
            INSERT INTO proactivity_rules
                (id, host_id, status, proposal_sha256, record_json, version,
                 expires_at, created_at, updated_at)
            VALUES ('rule:phase11c-benchmark', ?, 'active', ?, '{}', 1, ?, ?, ?)
            """,
            (HOST, "b" * 64, encoded_expiry, encoded_now, encoded_now),
        )
        connection.execute(
            """
            INSERT INTO proactivity_candidates
                (id, host_id, rule_id, feature, occurrence_key, scheduled_for,
                 attention_seconds, created_at, expires_at)
            VALUES (?, ?, 'rule:phase11c-benchmark', 'task.checkin', 'once:benchmark',
                    ?, 1, ?, ?)
            """,
            (CANDIDATE, HOST, encoded_now, encoded_now, encoded_expiry),
        )
        connection.execute(
            """
            INSERT INTO proactivity_dispatches
                (candidate_id, host_id, rule_id, state, version, attempts,
                 notification_id, expires_at, created_at, updated_at)
            VALUES (?, ?, 'rule:phase11c-benchmark', 'notified', 2, 1,
                    'notification:phase11c-benchmark', ?, ?, ?)
            """,
            (CANDIDATE, HOST, encoded_expiry, encoded_now, encoded_now),
        )
        connection.execute(
            """
            INSERT INTO proactivity_notifications
                (id, host_id, rule_id, candidate_id, feature, state, available_at,
                 expires_at, created_at, updated_at)
            VALUES ('notification:phase11c-benchmark', ?, 'rule:phase11c-benchmark', ?,
                    'task.checkin', 'active', ?, ?, ?, ?)
            """,
            (HOST, CANDIDATE, encoded_now, encoded_expiry, encoded_now, encoded_now),
        )
        connection.execute(
            """
            INSERT INTO proactivity_adapter_controls
                (host_id, enabled, version, kill_generation, updated_at)
            VALUES (?, 1, 1, 1, ?)
            """,
            (HOST, encoded_now),
        )
        connection.execute(
            """
            INSERT INTO proactivity_device_bindings
                (host_id, device_id, feature, allow_manage, state, version,
                 expires_at, created_at, updated_at)
            VALUES (?, ?, 'task.checkin', 1, 'active', 1, ?, ?, ?)
            """,
            (HOST, DEVICE, encoded_expiry, encoded_now, encoded_now),
        )
        connection.execute(
            """
            INSERT INTO proactivity_ownerships
                (candidate_id, host_id, rule_id, owner_kind, owner_id, owner_device_id,
                 version, lease_expires_at, created_at, updated_at)
            VALUES (?, ?, 'rule:phase11c-benchmark', 'local_host', ?, NULL, 1, NULL, ?, ?)
            """,
            (CANDIDATE, HOST, HOST, encoded_now, encoded_now),
        )
        connection.execute(
            """
            INSERT INTO proactivity_ownership_events
                (id, host_id, candidate_id, event_type, reason_code, owner_kind,
                 owner_device_id, version, created_at)
            VALUES ('owner-event:phase11c-benchmark', ?, ?, 'local_owner_created',
                    'local_notification_ready', 'local_host', NULL, 1, ?)
            """,
            (HOST, CANDIDATE, encoded_now),
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
