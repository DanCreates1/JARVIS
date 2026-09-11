"""Reproducible Phase 9A topology negotiation and downgrade benchmark."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis.remote import (
    ProtocolHello,
    RemoteIdentityContext,
    RemoteScope,
    TopologyManifest,
    TopologyNegotiationError,
    TopologyNegotiator,
    TopologyProfile,
    build_remote_manifest,
)

VALID_SAMPLES = 10_000
ABUSE_SAMPLES = 10_000
P95_LIMIT_MS = 10.0
RSS_GROWTH_LIMIT_MIB = 50.0
RUNTIME_ROOT = (Path(__file__).resolve().parents[1] / "runtime").resolve()


def _run() -> dict[str, Any]:
    now = datetime.now(UTC)
    host_id = "host:benchmark"
    server_id = "node:server"
    laptop_id = "device:laptop"
    laptop_capabilities = (
        "node.computer",
        "node.vision",
        "node.voice",
        "transport.events",
    )
    manifest = build_remote_manifest(
        profile=TopologyProfile.SPLIT,
        host_id=host_id,
        server_node_id=server_id,
        laptop_node_id=laptop_id,
        server_capabilities=("core.chat", "core.identity", "core.memory", "core.tasks"),
        laptop_capabilities=laptop_capabilities,
        laptop_offline_capabilities=("node.voice",),
        epoch=3,
    )
    negotiator = TopologyNegotiator(manifest, server_node_id=server_id, clock=lambda: now)
    context = RemoteIdentityContext(
        host_id=host_id,
        device_id=laptop_id,
        session_id="session:benchmark",
        key_version=1,
        audience="jarvis-api",
        scopes=frozenset({RemoteScope.TOPOLOGY_NEGOTIATE}),
        expires_at=now + timedelta(hours=1),
    )
    hello_values: dict[str, object] = {
        "host_id": host_id,
        "node_id": laptop_id,
        "session_id": context.session_id,
        "profile": manifest.profile,
        "topology_epoch": manifest.epoch,
        "topology_digest": manifest.digest,
        "supported_versions": ("1.0",),
        "minimum_version": "1.0",
        "offered_capabilities": (*laptop_capabilities, "node.unapproved"),
        "required_capabilities": ("node.voice",),
    }
    valid = ProtocolHello.model_validate(hello_values)
    abuse = (
        ProtocolHello.model_validate({**hello_values, "topology_digest": "0" * 64}),
        ProtocolHello.model_validate(
            {
                **hello_values,
                "supported_versions": ("1.0", "1.1"),
                "minimum_version": "1.1",
            }
        ),
        ProtocolHello.model_validate(
            {**hello_values, "required_capabilities": ("node.unapproved",)}
        ),
        ProtocolHello.model_validate({**hello_values, "host_id": "host:other"}),
    )

    rss_start = _rss_bytes()
    valid_latencies: list[float] = []
    valid_failures = 0
    for _ in range(VALID_SAMPLES):
        started = time.perf_counter_ns()
        try:
            negotiator.negotiate(context=context, hello=valid)
        except TopologyNegotiationError:
            valid_failures += 1
        valid_latencies.append((time.perf_counter_ns() - started) / 1_000_000)

    abuse_latencies: list[float] = []
    false_accepts = 0
    for index in range(ABUSE_SAMPLES):
        started = time.perf_counter_ns()
        try:
            negotiator.negotiate(context=context, hello=abuse[index % len(abuse)])
            false_accepts += 1
        except TopologyNegotiationError:
            pass
        abuse_latencies.append((time.perf_counter_ns() - started) / 1_000_000)

    rss_growth_mib = max(0, _rss_bytes() - rss_start) / (1_024 * 1_024)
    valid_p95 = _percentile(valid_latencies, 0.95)
    result: dict[str, Any] = {
        "profile": "phase9a-topology-protocol-v1",
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
        "manifest_digest_stable": manifest.digest
        == TopologyManifest.model_validate(manifest.model_dump(mode="json")).digest,
        "offline_fallback": list(negotiator.offline_fallback(laptop_id)),
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
        and result["manifest_digest_stable"] is True
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
    result = _run()
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if arguments.output is not None:
        output = _prepare_output_path(arguments.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
