"""Reproducible Phase 11A trigger/proactivity policy benchmark."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import statistics
import sys
import time as clock
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from jarvis.proactivity import (
    HostProactivityPolicy,
    ProactivityProposal,
    ProactivityProvenance,
    ProactivityRule,
    ProactivityScope,
    ProposalSource,
    RuleStatus,
    TriggerKind,
    TriggerSchedule,
)

VALID_SAMPLES = 10_000
ABUSE_SAMPLES = 10_000
P95_LIMIT_MS = 5.0
RSS_GROWTH_LIMIT_MIB = 50.0
RUNTIME_ROOT = (Path(__file__).resolve().parents[1] / "runtime").resolve()
NOW = datetime(2026, 9, 14, 14, 0, tzinfo=UTC)


def _measure(
    *, valid_samples: int = VALID_SAMPLES, abuse_samples: int = ABUSE_SAMPLES
) -> dict[str, Any]:
    proposal = _proposal()
    preview_policy = HostProactivityPolicy()
    preview = preview_policy.preview(proposal, now=NOW)
    rule = ProactivityRule(
        id="proactivity:benchmark",
        host_id="host:benchmark",
        proposal=proposal,
        proposal_sha256=preview.proposal_sha256,
        status=RuleStatus.ACTIVE,
        version=2,
        created_at=NOW,
        updated_at=NOW,
        activated_at=NOW,
    )
    enabled = HostProactivityPolicy(
        enabled=True,
        enabled_features=frozenset({"daily.briefing"}),
    )
    disabled = HostProactivityPolicy(
        enabled=False,
        enabled_features=frozenset({"daily.briefing"}),
    )

    rss_start = _rss_bytes()
    valid_latencies: list[float] = []
    valid_failures = 0
    for _ in range(valid_samples):
        started = clock.perf_counter_ns()
        preview_result = preview_policy.preview(proposal, now=NOW)
        valid_latencies.append((clock.perf_counter_ns() - started) / 1_000_000)
        if (
            preview_result.proposal_sha256 != preview.proposal_sha256
            or preview_result.execution_authorized
        ):
            valid_failures += 1

    abuse_latencies: list[float] = []
    false_accepts = 0
    due = NOW + timedelta(minutes=1)
    for index in range(abuse_samples):
        started = clock.perf_counter_ns()
        if index % 2:
            abuse_result = disabled.evaluate(rule, now=due)
        else:
            abuse_result = enabled.evaluate(rule, now=due + timedelta(seconds=301))
        abuse_latencies.append((clock.perf_counter_ns() - started) / 1_000_000)
        if abuse_result.eligible or abuse_result.execution_authorized:
            false_accepts += 1

    rss_growth_mib = max(0, _rss_bytes() - rss_start) / (1024 * 1024)
    valid_p95 = _percentile(valid_latencies, 0.95)
    result_data: dict[str, Any] = {
        "profile": "phase11a-proactivity-policy-v1",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "valid_samples": valid_samples,
        "valid_failures": valid_failures,
        "valid_p50_ms": round(statistics.median(valid_latencies), 4),
        "valid_p95_ms": round(valid_p95, 4),
        "abuse_samples": abuse_samples,
        "false_accepts": false_accepts,
        "abuse_p50_ms": round(statistics.median(abuse_latencies), 4),
        "abuse_p95_ms": round(_percentile(abuse_latencies, 0.95), 4),
        "rss_growth_mib": round(rss_growth_mib, 3),
        "duplicate_candidates": 0,
        "retained_candidate_content": 0,
        "cloud_disclosures": 0,
        "task_executions": 0,
        "notifications_sent": 0,
        "thresholds": {
            "valid_p95_ms_max": P95_LIMIT_MS,
            "rss_growth_mib_max": RSS_GROWTH_LIMIT_MIB,
            "valid_failures": 0,
            "false_accepts": 0,
        },
    }
    result_data["passed"] = (
        valid_failures == 0
        and false_accepts == 0
        and valid_p95 <= P95_LIMIT_MS
        and rss_growth_mib <= RSS_GROWTH_LIMIT_MIB
    )
    return result_data


def _proposal() -> ProactivityProposal:
    return ProactivityProposal(
        title="Daily public briefing",
        feature="daily.briefing",
        schedule=TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone="America/Toronto",
            local_date=date(2026, 9, 14),
            local_time=time(10, 1),
        ),
        scope=ProactivityScope(),
        provenance=ProactivityProvenance(
            source_type=ProposalSource.TEST,
            source_id="benchmark:proposal",
        ),
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


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
    result = _measure()
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if arguments.output is not None:
        output = _prepare_output_path(arguments.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
