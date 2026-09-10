"""Reproducible local Phase 8B browser authentication and CSRF benchmark."""

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
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jarvis.remote import (
    DeviceType,
    EnrollmentCompletion,
    RemoteAuthenticationError,
    RemoteIdentityService,
    RemoteScope,
    SessionRequest,
    SignedRequest,
    SQLiteRemoteIdentityStore,
    build_enrollment_proof,
    canonical_request,
    encode_base64url,
)

VALID_SAMPLES = 10_000
ABUSE_SAMPLES = 10_000
P95_LIMIT_MS = 10.0
RSS_GROWTH_LIMIT_MIB = 50.0
RUNTIME_ROOT = (Path(__file__).resolve().parents[1] / "runtime").resolve()
NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)


def _public_key(key: Ed25519PrivateKey) -> str:
    return encode_base64url(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def _signed(
    key: Ed25519PrivateKey,
    *,
    device_id: str,
    body: bytes,
) -> tuple[SignedRequest, str]:
    request = SignedRequest(
        method="POST",
        authority="benchmark.jarvis.test",
        path="/api/v1/browser/sessions",
        query="",
        body=body,
        device_id=device_id,
        key_version=1,
        audience="jarvis-api",
        timestamp=NOW,
        nonce="B" * 22,
        session_token=None,
    )
    return request, encode_base64url(key.sign(canonical_request(request)))


async def _run() -> dict[str, Any]:
    rss_start = _rss_bytes()
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jarvis-phase8b-", dir=RUNTIME_ROOT) as temp:
        database = Path(temp) / "browser-benchmark.db"
        store = SQLiteRemoteIdentityStore(database)
        await store.initialize()
        service = RemoteIdentityService(store, clock=lambda: NOW)
        key = Ed25519PrivateKey.generate()
        ticket = await service.create_enrollment(
            host_id="host:phase8b-benchmark",
            display_name="Synthetic browser benchmark",
            device_type=DeviceType.BROWSER,
            approved_scopes=(
                RemoteScope.BROWSER_SESSION,
                RemoteScope.IDENTITY_READ,
            ),
            risk_ceiling=1,
        )
        public_key = _public_key(key)
        device = await service.complete_enrollment(
            EnrollmentCompletion(
                enrollment_id=ticket.id,
                challenge=ticket.challenge,
                public_key=public_key,
                proof_signature=encode_base64url(
                    key.sign(
                        build_enrollment_proof(
                            enrollment_id=ticket.id,
                            challenge=ticket.challenge,
                            public_key=public_key,
                            protocol_version="1",
                        )
                    )
                ),
            )
        )
        payload = SessionRequest(
            requested_scopes=(RemoteScope.BROWSER_SESSION, RemoteScope.IDENTITY_READ)
        )
        body = payload.model_dump_json().encode()
        request, signature = _signed(key, device_id=device.id, body=body)
        credential = await service.create_browser_session(
            request=request,
            signature=signature,
            payload=payload,
        )

        valid_latencies: list[float] = []
        valid_failures = 0
        for _ in range(VALID_SAMPLES):
            started = time.perf_counter_ns()
            try:
                await service.authenticate_browser_session(
                    cookie_token=credential.cookie_token,
                    required_scope=RemoteScope.IDENTITY_READ,
                )
            except RemoteAuthenticationError:
                valid_failures += 1
            valid_latencies.append((time.perf_counter_ns() - started) / 1_000_000)

        false_accepts = 0
        abuse_latencies: list[float] = []
        for _ in range(ABUSE_SAMPLES):
            started = time.perf_counter_ns()
            try:
                await service.authenticate_browser_session(
                    cookie_token=credential.cookie_token,
                    csrf_token="Z" * 43,
                    require_csrf=True,
                )
                false_accepts += 1
            except RemoteAuthenticationError:
                pass
            abuse_latencies.append((time.perf_counter_ns() - started) / 1_000_000)

        await store.close()
        database_bytes = database.stat().st_size
        with closing(sqlite3.connect(database)) as connection:
            retained_denials = int(
                connection.execute(
                    """
                    SELECT count(*) FROM remote_audit_events
                    WHERE device_id = ? AND event_type = 'request.denied'
                    """,
                    (device.id,),
                ).fetchone()[0]
            )
    rss_growth_mib = max(0, _rss_bytes() - rss_start) / (1_024 * 1_024)
    valid_p95 = _percentile(valid_latencies, 0.95)
    result: dict[str, Any] = {
        "profile": "phase8b-browser-v1",
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
        "database_bytes": database_bytes,
        "retained_device_denial_events": retained_denials,
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
