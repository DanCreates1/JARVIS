"""Deterministic Phase 9C placement, chaos, update, rollback, and offline benchmark."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import hashlib
import json
import os
import platform
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from jarvis.memory import SQLiteConversationStore
from jarvis.remote import (
    DeploymentError,
    DeploymentHealthMonitor,
    DeploymentRole,
    HealthReason,
    OwnershipTransitionReceipt,
    TopologyProfile,
    analyze_database,
    build_deployment_manifest,
    build_local_only_manifest,
    build_remote_manifest,
    create_cutover_receipt,
    create_deployment_state,
    decide_availability,
    load_release_state,
    promote_release,
    rollback_release,
    stage_release,
    verify_runtime_deployment,
)

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
RUNTIME_ROOT: Final = REPOSITORY_ROOT / "runtime"
PLACEMENT_CYCLES: Final = 100
CHAOS_CYCLES: Final = 100
P95_LIMIT_MS: Final = 10.0
RSS_GROWTH_LIMIT_MIB: Final = 50.0
PRIVATE_MARKER: Final = "phase9c-private-marker-never-telemetry"


def _database(path: Path) -> Path:
    async def initialize() -> None:
        store = SQLiteConversationStore(path)
        await store.initialize()
        conversation = await store.create_conversation(metadata={"marker": PRIVATE_MARKER})
        assert conversation.id
        await store.close()

    asyncio.run(initialize())
    return path


def _fixtures(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    artifact = root / "jarvis-0.1.0-py3-none-any.whl"
    artifact.write_bytes(b"phase9c-pinned-release")

    local_db = _database(root / "local.db")
    local_topology = build_local_only_manifest(
        host_id="host:benchmark",
        node_id="node:local",
        capabilities=("core.chat", "core.identity", "transport.events"),
        epoch=1,
    )
    local_deployment = build_deployment_manifest(
        topology=local_topology,
        role=DeploymentRole.LOCAL_CORE,
        node_id="node:local",
        release_artifact=artifact,
        python_version=platform.python_version(),
        database_path=local_db,
    )
    local_state = create_deployment_state(
        root / "local-state.json",
        deployment=local_deployment,
        topology=local_topology,
        release_artifact=artifact,
        database=local_db,
        ownership_receipt=None,
    )

    source = _database(root / "source.db")
    target = root / "server.db"
    shutil.copyfile(source, target)
    remote_topology = build_remote_manifest(
        profile=TopologyProfile.SPLIT,
        host_id="host:benchmark",
        server_node_id="node:server",
        laptop_node_id="node:laptop",
        server_capabilities=("core.chat", "core.identity", "transport.events"),
        laptop_capabilities=("node.computer", "node.voice", "transport.events"),
        laptop_offline_capabilities=("node.voice",),
        epoch=2,
    )
    receipt = create_cutover_receipt(
        source,
        target,
        root / "cutover.json",
        topology=remote_topology,
        source_owner_node_id="node:laptop",
        accepted_state_sha256=analyze_database(source).content_sha256,
    )
    remote_deployment = build_deployment_manifest(
        topology=remote_topology,
        role=DeploymentRole.SERVER_CORE,
        node_id="node:server",
        release_artifact=artifact,
        python_version=platform.python_version(),
        database_path=target,
        ownership_receipt=receipt,
    )
    remote_state = create_deployment_state(
        root / "remote-state.json",
        deployment=remote_deployment,
        topology=remote_topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )
    local = {
        "deployment": local_deployment,
        "state": local_state,
        "topology": local_topology,
        "artifact": artifact,
        "database": local_db,
        "receipt": None,
    }
    remote = {
        "deployment": remote_deployment,
        "state": remote_state,
        "topology": remote_topology,
        "artifact": artifact,
        "database": target,
        "receipt": receipt,
    }
    return local, remote


def _verify(fixture: dict[str, Any], **changes: Any) -> Any:
    values = dict(fixture)
    values.update(changes)
    return verify_runtime_deployment(
        deployment=values["deployment"],
        expected_deployment_sha256=values["deployment"].digest,
        state=values["state"],
        expected_state_sha256=values["state"].digest,
        topology=values["topology"],
        release_artifact=values["artifact"],
        database=values["database"],
        ownership_receipt=values["receipt"],
    )


def _placement(fixture: dict[str, Any]) -> dict[str, float | int]:
    latencies: list[float] = []
    failures = 0
    for _ in range(10):
        _verify(fixture)
    for _ in range(PLACEMENT_CYCLES):
        started = time.perf_counter_ns()
        try:
            _verify(fixture)
        except DeploymentError:
            failures += 1
        latencies.append((time.perf_counter_ns() - started) / 1_000_000)
    return {
        "samples": PLACEMENT_CYCLES,
        "failures": failures,
        "p50_ms": _percentile(latencies, 0.50),
        "p95_ms": _percentile(latencies, 0.95),
    }


def _rejection_chaos(remote: dict[str, Any]) -> dict[str, dict[str, int]]:
    deployment = remote["deployment"]
    state = remote["state"]
    topology = remote["topology"]
    receipt: OwnershipTransitionReceipt = remote["receipt"]
    cases: dict[str, dict[str, Any]] = {
        "bad_release": {"deployment": deployment.model_copy(update={"release_sha256": "0" * 64})},
        "stale_topology": {"topology": topology.model_copy(update={"epoch": topology.epoch + 1})},
        "corrupt_receipt": {
            "receipt": receipt.model_copy(update={"active_owner_node_id": "node:attacker"})
        },
        "corrupt_state": {"state": state.model_copy(update={"release_sha256": "0" * 64})},
        "wrong_database": {"database": Path(str(remote["database"]) + ".missing")},
    }
    results: dict[str, dict[str, int]] = {}
    for name, changes in cases.items():
        false_accepts = 0
        for _ in range(CHAOS_CYCLES):
            try:
                _verify(remote, **changes)
            except DeploymentError:
                continue
            false_accepts += 1
        results[name] = {"attempts": CHAOS_CYCLES, "false_accepts": false_accepts}
    return results


def _availability_chaos(remote: dict[str, Any]) -> dict[str, dict[str, int]]:
    core_activation = _verify(remote)
    laptop_activation = core_activation.model_copy(
        update={
            "role": DeploymentRole.LAPTOP_DEVICE,
            "node_id": "node:laptop",
            "offline_capabilities": ("node.voice",),
        }
    )
    cases: dict[str, Callable[[], bool]] = {
        "packet_loss": lambda: (
            decide_availability(laptop_activation, capability="core.chat", connected=False).allowed
        ),
        "partition_shared_write": lambda: (
            decide_availability(
                laptop_activation,
                capability="core.chat",
                connected=False,
                mutates_shared_state=True,
            ).allowed
        ),
        "partition_device_effect": lambda: (
            decide_availability(
                laptop_activation,
                capability="node.computer",
                connected=False,
                causes_device_effect=True,
            ).allowed
        ),
        "core_partition": lambda: (
            decide_availability(core_activation, capability="core.chat", connected=False).allowed
        ),
    }
    results: dict[str, dict[str, int]] = {}
    for name, action in cases.items():
        false_accepts = 0
        for _ in range(CHAOS_CYCLES):
            if action():
                false_accepts += 1
        results[name] = {"attempts": CHAOS_CYCLES, "false_accepts": false_accepts}
    allowed = sum(
        1
        for _ in range(CHAOS_CYCLES)
        if decide_availability(laptop_activation, capability="node.voice", connected=False).allowed
    )
    results["declared_offline"] = {
        "attempts": CHAOS_CYCLES,
        "false_accepts": CHAOS_CYCLES - allowed,
    }
    return results


def _health_chaos() -> dict[str, dict[str, int]]:
    reasons = {
        "latency": HealthReason.OVERLOADED,
        "tls_failure": HealthReason.TLS_UNAVAILABLE,
        "stale_protocol": HealthReason.PROTOCOL_STALE,
        "overload": HealthReason.OVERLOADED,
        "disk_pressure": HealthReason.DISK_PRESSURE,
        "disk_full": HealthReason.DISK_FULL,
    }
    results: dict[str, dict[str, int]] = {}
    for name, reason in reasons.items():
        false_ready = 0
        for _ in range(CHAOS_CYCLES):
            monitor = DeploymentHealthMonitor(max_events=16)
            monitor.observe(HealthReason.READY, healthy=True)
            if monitor.observe(reason, healthy=False).ready:
                false_ready += 1
        results[name] = {"attempts": CHAOS_CYCLES, "false_accepts": false_ready}

    failed_restarts = 0
    for _ in range(CHAOS_CYCLES):
        crashed = DeploymentHealthMonitor(max_events=16)
        if crashed.snapshot().ready:
            failed_restarts += 1
        if not crashed.observe(HealthReason.READY, healthy=True).ready:
            failed_restarts += 1
    results["core_crash_restart"] = {
        "attempts": CHAOS_CYCLES,
        "false_accepts": failed_restarts,
    }
    return results


def _release_chaos(root: Path) -> dict[str, float | int]:
    release_root = root / "releases"
    release_root.mkdir()
    first = root / "first.whl"
    second = root / "second.whl"
    first.write_bytes(b"first-known-good")
    second.write_bytes(b"second-candidate")
    first_sha = hashlib.sha256(first.read_bytes()).hexdigest()
    second_sha = hashlib.sha256(second.read_bytes()).hexdigest()
    stage_release(first, release_root, expected_sha256=first_sha)
    stage_release(second, release_root, expected_sha256=second_sha)
    false_accepts = 0
    rollback_mismatches = 0
    rollback_latencies: list[float] = []
    for index in range(CHAOS_CYCLES):
        state_path = root / f"release-state-{index}.json"
        promote_release(
            state_path,
            candidate_sha256=first_sha,
            expected_current_sha256=None,
            probe=lambda digest: digest == first_sha,
        )
        promote_release(
            state_path,
            candidate_sha256=second_sha,
            expected_current_sha256=first_sha,
            probe=lambda digest: digest == second_sha,
        )
        try:
            promote_release(
                state_path,
                candidate_sha256="0" * 64,
                expected_current_sha256=second_sha,
                probe=lambda _digest: False,
            )
        except DeploymentError:
            pass
        else:
            false_accepts += 1
        started = time.perf_counter_ns()
        rolled_back = rollback_release(
            state_path,
            expected_current_sha256=second_sha,
            probe=lambda digest: digest == first_sha,
        )
        rollback_latencies.append((time.perf_counter_ns() - started) / 1_000_000)
        if (
            rolled_back.current_release_sha256 != first_sha
            or load_release_state(state_path).current_release_sha256 != first_sha
        ):
            rollback_mismatches += 1
    return {
        "attempts": CHAOS_CYCLES,
        "bad_release_false_accepts": false_accepts,
        "rollback_mismatches": rollback_mismatches,
        "rollback_p95_ms": _percentile(rollback_latencies, 0.95),
    }


def _run() -> dict[str, Any]:
    RUNTIME_ROOT.mkdir(exist_ok=True)
    rss_before = _rss_bytes()
    with tempfile.TemporaryDirectory(prefix="phase9c-", dir=RUNTIME_ROOT) as raw_root:
        root = Path(raw_root)
        local, remote = _fixtures(root)
        local_result = _placement(local)
        split_result = _placement(remote)
        chaos = {
            **_rejection_chaos(remote),
            **_availability_chaos(remote),
            **_health_chaos(),
        }
        release = _release_chaos(root)
        telemetry = DeploymentHealthMonitor(max_events=16).observe(
            HealthReason.DISK_PRESSURE, healthy=True, latency_ms=1
        )
        telemetry_private = PRIVATE_MARKER in telemetry.model_dump_json()
    rss_growth_mib = max(0, _rss_bytes() - rss_before) / (1_024 * 1_024)
    false_accepts = sum(item["false_accepts"] for item in chaos.values())
    passed = (
        local_result["failures"] == 0
        and split_result["failures"] == 0
        and local_result["p95_ms"] <= P95_LIMIT_MS
        and split_result["p95_ms"] <= P95_LIMIT_MS
        and false_accepts == 0
        and release["bad_release_false_accepts"] == 0
        and release["rollback_mismatches"] == 0
        and not telemetry_private
        and rss_growth_mib <= RSS_GROWTH_LIMIT_MIB
    )
    return {
        "schema": "jarvis.phase9c.resilience-benchmark.v1",
        "placement": {"local_only": local_result, "split": split_result},
        "chaos": chaos,
        "release": release,
        "telemetry_private_marker_present": telemetry_private,
        "rss_growth_mib": rss_growth_mib,
        "thresholds": {
            "placement_cycles": PLACEMENT_CYCLES,
            "chaos_attempts_per_class": CHAOS_CYCLES,
            "placement_p95_ms_max": P95_LIMIT_MS,
            "rss_growth_mib_max": RSS_GROWTH_LIMIT_MIB,
            "false_accepts": 0,
            "rollback_mismatches": 0,
        },
        "passed": passed,
    }


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * quantile) - 1))
    return ordered[index]


def _rss_bytes() -> int:
    if os.name != "nt":
        import resource

        return int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1_024  # type: ignore[attr-defined]
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


def _prepare_output(path: Path) -> Path:
    candidate = path.expanduser().resolve(strict=False)
    try:
        candidate.relative_to(RUNTIME_ROOT)
    except ValueError as exc:
        raise ValueError("benchmark output must remain under repository runtime") from exc
    if candidate.exists() or candidate.is_symlink() or candidate.suffix != ".json":
        raise ValueError("benchmark output must be a new JSON file")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = _run()
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if arguments.output is not None:
        output = _prepare_output(arguments.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as destination:
            destination.write(rendered + "\n")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
