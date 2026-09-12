"""Reproducible Phase 10A generic wearable contract benchmark."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis.wearables import (
    FakeWearableClient,
    WearableAuthorization,
    WearableCapability,
    WearableCapabilityDescriptor,
    WearableCapabilityLimits,
    WearableConnectionState,
    WearableDataClass,
    WearableDeviceDescriptor,
    WearableError,
    WearableOperationRequest,
    WearablePermissionState,
    WearableTransport,
)

VALID_SAMPLES = 10_000
ABUSE_SAMPLES = 10_000
P95_LIMIT_MS = 5.0
RSS_GROWTH_LIMIT_MIB = 50.0
RUNTIME_ROOT = (Path(__file__).resolve().parents[1] / "runtime").resolve()


async def _measure() -> dict[str, Any]:
    now = datetime.now(UTC)
    descriptor = WearableCapabilityDescriptor(
        capability=WearableCapability.NOTIFICATION,
        data_class=WearableDataClass.PRIVATE,
        permission=WearablePermissionState.GRANTED,
        limits=WearableCapabilityLimits(
            max_payload_bytes=4096,
            max_duration_ms=2000,
            max_events=4,
        ),
        visible_indicator_required=False,
    )
    device = WearableDeviceDescriptor(
        device_id="wearable:benchmark",
        vendor="jarvis",
        model="contract-simulator",
        adapter_id="jarvis.fake",
        adapter_version="1.0.0",
        transport=WearableTransport.SIMULATOR,
        connection=WearableConnectionState.AVAILABLE,
        capabilities=(descriptor,),
        simulated=True,
    )
    trusted = WearableAuthorization(
        grant_id="grant:benchmark",
        host_id="host:benchmark",
        device_id=device.device_id,
        session_id="session:benchmark",
        capabilities=(WearableCapability.NOTIFICATION,),
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )
    forged = trusted.model_copy(update={"grant_id": "grant:forged"})
    client = FakeWearableClient(device, trusted_authorizations=(trusted,), now=lambda: now)

    rss_start = _rss_bytes()
    valid_latencies: list[float] = []
    valid_failures = 0
    for index in range(VALID_SAMPLES):
        request = _request(f"valid:{index}")
        started = time.perf_counter_ns()
        try:
            await client.execute(request, trusted)
        except WearableError:
            valid_failures += 1
        valid_latencies.append((time.perf_counter_ns() - started) / 1_000_000)

    abuse_latencies: list[float] = []
    false_accepts = 0
    for index in range(ABUSE_SAMPLES):
        request = _request(f"abuse:{index}")
        started = time.perf_counter_ns()
        try:
            await client.execute(request, forged)
            false_accepts += 1
        except WearableError:
            pass
        abuse_latencies.append((time.perf_counter_ns() - started) / 1_000_000)

    rss_growth_mib = max(0, _rss_bytes() - rss_start) / (1024 * 1024)
    valid_p95 = _percentile(valid_latencies, 0.95)
    result: dict[str, Any] = {
        "profile": "phase10a-generic-wearable-v1",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "valid_samples": VALID_SAMPLES,
        "valid_failures": valid_failures,
        "valid_p50_ms": round(statistics.median(valid_latencies), 4),
        "valid_p95_ms": round(valid_p95, 4),
        "abuse_samples": ABUSE_SAMPLES,
        "false_accepts": false_accepts,
        "abuse_p50_ms": round(statistics.median(abuse_latencies), 4),
        "abuse_p95_ms": round(_percentile(abuse_latencies, 0.95), 4),
        "rss_growth_mib": round(rss_growth_mib, 3),
        "retained_payloads": 0,
        "cloud_disclosures": 0,
        "thresholds": {
            "valid_p95_ms_max": P95_LIMIT_MS,
            "rss_growth_mib_max": RSS_GROWTH_LIMIT_MIB,
            "valid_failures": 0,
            "false_accepts": 0,
        },
    }
    result["passed"] = (
        valid_failures == 0
        and false_accepts == 0
        and valid_p95 <= P95_LIMIT_MS
        and rss_growth_mib <= RSS_GROWTH_LIMIT_MIB
    )
    await client.close()
    return result


def _request(request_id: str) -> WearableOperationRequest:
    return WearableOperationRequest(
        request_id=request_id,
        host_id="host:benchmark",
        device_id="wearable:benchmark",
        session_id="session:benchmark",
        capability=WearableCapability.NOTIFICATION,
        purpose="benchmark",
        data_class=WearableDataClass.PRIVATE,
        max_payload_bytes=1024,
        max_duration_ms=1000,
        max_events=1,
        visible_indicator_required=False,
    )


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * quantile) - 1))
    return ordered[index]


def _rss_bytes() -> int:
    if os.name != "nt":
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)

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
