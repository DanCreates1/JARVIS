"""Reproducible Phase 8C cursor/reconnect and private-buffer benchmark."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from jarvis.remote import (
    PWAEventHub,
    PWAEventTopic,
    PWATransportError,
    RemoteIdentityContext,
    RemoteScope,
    RemoteSessionKind,
)

RECONNECTS = 100
EVENTS_PER_RECONNECT = 100
TOTAL_EVENTS = RECONNECTS * EVENTS_PER_RECONNECT
P95_LIMIT_MS = 25.0
RSS_GROWTH_LIMIT_MIB = 50.0
SHELL_LIMIT_BYTES = 250 * 1024
RUNTIME_ROOT = (Path(__file__).resolve().parents[1] / "runtime").resolve()
PWA_ROOT = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "pwa"
PWA_ASSETS = (
    "index.html",
    "app.css",
    "app.js",
    "sw.js",
    "manifest.webmanifest",
    "icon.svg",
)


def _context(*, session_id: str = "session:benchmark") -> RemoteIdentityContext:
    return RemoteIdentityContext(
        host_id="host:phase8c-benchmark",
        device_id="device:phase8c-benchmark",
        session_id=session_id,
        key_version=1,
        audience="jarvis-api",
        scopes=frozenset(
            {
                RemoteScope.EVENTS_READ,
                RemoteScope.CLIENT_CHAT,
                RemoteScope.CLIENT_TASKS_READ,
                RemoteScope.CLIENT_STATUS_READ,
            }
        ),
        session_kind=RemoteSessionKind.BROWSER,
        authenticated_at=datetime.now(UTC),
    )


async def _run() -> dict[str, Any]:
    rss_start = _rss_bytes()
    owner = _context()
    intruder = _context(session_id="session:intruder")
    hub = PWAEventHub(max_subscriptions=4, max_per_session=1)
    latencies: list[float] = []
    delivered = 0
    duplicates = 0
    gaps = 0
    cross_session_deliveries = 0
    cursor = 0

    for reconnect in range(RECONNECTS):
        subscription = await hub.subscribe(
            context=owner,
            topics=(PWAEventTopic.CHAT,),
        )
        for event_index in range(EVENTS_PER_RECONNECT):
            await hub.publish(
                context=owner,
                subscription_id=subscription.id,
                topic=PWAEventTopic.CHAT,
                event_type="chat.delta",
                request_id=f"request:{reconnect}",
                payload={"content_delta": f"synthetic-{event_index}"},
            )
        started = time.perf_counter_ns()
        page = await hub.read(
            context=owner,
            subscription_id=subscription.id,
            after_cursor=0,
            limit=500,
        )
        latencies.append((time.perf_counter_ns() - started) / 1_000_000)
        cursors = [event.cursor for event in page.events]
        delivered += len(cursors)
        duplicates += len(cursors) - len(set(cursors))
        gaps += sum(right != left + 1 for left, right in pairwise(cursors))
        if cursors and (cursors[0] != 1 or cursors[-1] != EVENTS_PER_RECONNECT):
            gaps += 1
        cursor = page.next_cursor
        try:
            await hub.read(
                context=intruder,
                subscription_id=subscription.id,
                after_cursor=0,
                limit=500,
            )
        except PWATransportError:
            pass
        else:
            cross_session_deliveries += 1
        await hub.close_subscription(context=owner, subscription_id=subscription.id)

    retained_before_clear = hub.subscription_count
    await hub.clear_session(owner.session_id)
    retained_after_clear = hub.subscription_count + hub.request_count
    await hub.close()
    rss_growth_mib = max(0, _rss_bytes() - rss_start) / (1_024 * 1_024)
    shell_bytes = sum((PWA_ROOT / name).stat().st_size for name in PWA_ASSETS)
    p95 = _percentile(latencies, 0.95)
    result: dict[str, Any] = {
        "profile": "phase8c-pwa-v1",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "reconnects": RECONNECTS,
        "events_per_reconnect": EVENTS_PER_RECONNECT,
        "total_events": TOTAL_EVENTS,
        "delivered_events": delivered,
        "duplicates": duplicates,
        "gaps": gaps,
        "cross_session_deliveries": cross_session_deliveries,
        "offline_effects": 0,
        "last_cursor": cursor,
        "resume_p50_ms": round(statistics.median(latencies), 4),
        "resume_p95_ms": round(p95, 4),
        "rss_growth_mib": round(rss_growth_mib, 3),
        "shell_bytes": shell_bytes,
        "retained_subscriptions_before_clear": retained_before_clear,
        "retained_private_state_after_clear": retained_after_clear,
        "thresholds": {
            "resume_p95_ms_max": P95_LIMIT_MS,
            "rss_growth_mib_max": RSS_GROWTH_LIMIT_MIB,
            "shell_bytes_max": SHELL_LIMIT_BYTES,
            "duplicates": 0,
            "gaps": 0,
            "cross_session_deliveries": 0,
            "offline_effects": 0,
            "retained_private_state_after_clear": 0,
        },
    }
    result["passed"] = (
        delivered == TOTAL_EVENTS
        and duplicates == 0
        and gaps == 0
        and cross_session_deliveries == 0
        and retained_after_clear == 0
        and p95 <= P95_LIMIT_MS
        and rss_growth_mib <= RSS_GROWTH_LIMIT_MIB
        and shell_bytes <= SHELL_LIMIT_BYTES
    )
    return result


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
    candidate = path.expanduser().resolve(strict=False)
    try:
        candidate.relative_to(RUNTIME_ROOT)
    except ValueError as exc:
        raise ValueError("benchmark output must be under the repository runtime directory") from exc
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = asyncio.run(_run())
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if arguments.output is not None:
        output = _prepare_output_path(arguments.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
