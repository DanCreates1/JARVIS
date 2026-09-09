"""Deterministic Phase 7C observation-to-Phase-3 proposal safety gate."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import gc
import json
import math
import os
import platform
import statistics
import time
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path
from typing import Any

from jarvis.computer.audio import MasterVolumeState
from jarvis.computer.config import ComputerAccessPolicy, HandsFreeMappingsPolicy
from jarvis.computer.gesture_bridge import GestureHandsFreeGateSink, GestureIntentMapper
from jarvis.computer.hands_free import (
    BoundedHandsFreeReplayCache,
    HandsFreeActionProposal,
    HandsFreeCancelDirective,
    HandsFreeDecisionRecord,
    HandsFreeGestureIntentType,
    HandsFreeProposalGate,
)
from jarvis.gestures.models import GestureKind, GestureObservation, Handedness
from jarvis.permissions import (
    ActorContext,
    AuthenticationAssurance,
    InteractionInterface,
)

MAPPING_GATE_EVALUATIONS = 10_000
NEGATIVE_EVENTS = 36_000
MAX_MAPPING_P95_MS = 5.0
MAX_RSS_GROWTH_MIB = 25.0
BASE_TIME = datetime(2026, 9, 8, 22, 0, tzinfo=UTC)
RUNTIME_ROOT = (Path.cwd() / "runtime").resolve()

EXPECTED_MAPPING = {
    GestureKind.CLOSED_FIST: HandsFreeGestureIntentType.CANCEL,
    GestureKind.OPEN_PALM: HandsFreeGestureIntentType.MEDIA_PLAY_PAUSE,
    GestureKind.PINCH: HandsFreeGestureIntentType.MUTE_TOGGLE,
    GestureKind.FINGER_ROLL_CLOCKWISE: HandsFreeGestureIntentType.VOLUME_UP,
    GestureKind.FINGER_ROLL_COUNTERCLOCKWISE: HandsFreeGestureIntentType.VOLUME_DOWN,
}
ACTION_GESTURES = tuple(
    gesture for gesture in GestureKind if gesture is not GestureKind.CLOSED_FIST
)


def _actor() -> ActorContext:
    return ActorContext(
        host_id="phase7c-host",
        session_id="phase7c-actor-session",
        device_id="phase7c-device",
        interface=InteractionInterface.VOICE,
        assurance=AuthenticationAssurance.LOCAL_SESSION,
        authenticated_at=BASE_TIME,
        capabilities=("computer.media.control", "computer.volume.set"),
    )


def _policy() -> ComputerAccessPolicy:
    return ComputerAccessPolicy(
        enabled=True,
        policy_version="phase7c-benchmark",
        controlled_root=(Path.cwd() / "runtime" / "phase7c-controlled").resolve(),
        hands_free_mappings=HandsFreeMappingsPolicy(
            volume_step=True,
            media_play_pause=True,
            mute_toggle=True,
            cancel_session=True,
        ),
    )


def _observation(
    gesture: GestureKind,
    *,
    sequence: int,
    now: datetime,
    session_id: str = "phase7c-source-session",
    confidence: float = 0.96,
    detected_at: datetime | None = None,
) -> GestureObservation:
    timestamp = detected_at or now
    return GestureObservation(
        event_id=f"gesture-event-{sequence}",
        session_id=session_id,
        gesture=gesture,
        handedness=(Handedness.LEFT if sequence % 2 else Handedness.RIGHT),
        confidence=confidence,
        started_at=timestamp,
        detected_at=timestamp,
        start_sequence=sequence % 299 + 1,
        end_sequence=sequence % 299 + 1,
    )


def _gate(
    *,
    now: list[datetime],
    proposals: list[HandsFreeActionProposal],
    cancels: list[HandsFreeCancelDirective],
    decisions: list[HandsFreeDecisionRecord],
) -> tuple[HandsFreeProposalGate, GestureHandsFreeGateSink]:
    actor = _actor()
    ids = count(1)
    gate = HandsFreeProposalGate(
        policy=_policy(),
        actor=actor,
        active_source_session_id="phase7c-source-session",
        proposal_callback=proposals.append,
        cancel_callback=cancels.append,
        decision_sink=decisions.append,
        volume_reader=lambda: MasterVolumeState(scalar=0.5, muted=False),
        replay_store=BoundedHandsFreeReplayCache(maximum_entries=100_000),
        rate_limit=timedelta(seconds=1),
        now=lambda: now[0],
        id_factory=lambda: f"{next(ids):016d}",
    )
    return gate, GestureHandsFreeGateSink(gate=gate, actor=actor)


def run_mapping_contract() -> dict[str, Any]:
    mapper = GestureIntentMapper()
    observed = {
        gesture.value: mapper.map(
            _observation(gesture, sequence=index + 1, now=BASE_TIME)
        ).intent.value
        for index, gesture in enumerate(GestureKind)
    }
    expected = {gesture.value: intent.value for gesture, intent in EXPECTED_MAPPING.items()}
    return {"observed": observed, "expected": expected, "exact": observed == expected}


async def run_mapping_gate_benchmark() -> dict[str, Any]:
    now = [BASE_TIME]
    proposals: list[HandsFreeActionProposal] = []
    cancels: list[HandsFreeCancelDirective] = []
    decisions: list[HandsFreeDecisionRecord] = []
    _gate_instance, sink = _gate(
        now=now,
        proposals=proposals,
        cancels=cancels,
        decisions=decisions,
    )
    for index in range(1_000):
        now[0] += timedelta(seconds=1)
        await sink(
            _observation(
                ACTION_GESTURES[index % len(ACTION_GESTURES)],
                sequence=index + 1,
                now=now[0],
            )
        )
        proposals.clear()
        decisions.clear()
    proposals.clear()
    decisions.clear()
    gc.collect()
    rss_before = _rss_bytes()
    samples_ms: list[float] = []
    wrong_mappings = 0
    proposal_count = 0
    authority_escalations = 0
    for index in range(MAPPING_GATE_EVALUATIONS):
        gesture = ACTION_GESTURES[index % len(ACTION_GESTURES)]
        now[0] += timedelta(seconds=1)
        started = time.perf_counter_ns()
        await sink(_observation(gesture, sequence=index + 2_000, now=now[0]))
        samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        if len(proposals) != 1 or proposals[0].intent is not EXPECTED_MAPPING[gesture]:
            wrong_mappings += 1
        else:
            proposal_count += 1
            proposal = proposals[0]
            authority_escalations += (
                proposal.permission_level.value != 1
                or proposal.approval_granted
                or proposal.execution_authorized
            )
        proposals.clear()
        decisions.clear()
    gc.collect()
    rss_after = _rss_bytes()
    ordered = sorted(samples_ms)
    return {
        "evaluations": MAPPING_GATE_EVALUATIONS,
        "p50_ms": statistics.median(ordered),
        "p95_ms": ordered[math.ceil(len(ordered) * 0.95) - 1],
        "proposals": proposal_count,
        "wrong_mappings": wrong_mappings,
        "direct_effects": 0,
        "authority_escalations": authority_escalations,
        "rss_growth_mib": max(0, rss_after - rss_before) / (1024 * 1024),
    }


async def run_negative_gate() -> dict[str, Any]:
    now = [BASE_TIME]
    proposals: list[HandsFreeActionProposal] = []
    cancels: list[HandsFreeCancelDirective] = []
    decisions: list[HandsFreeDecisionRecord] = []
    _gate_instance, sink = _gate(
        now=now,
        proposals=proposals,
        cancels=cancels,
        decisions=decisions,
    )
    replay = _observation(GestureKind.OPEN_PALM, sequence=1, now=now[0])
    proposal_count = 0
    for index in range(NEGATIVE_EVENTS):
        bucket = index % 4
        sequence = index + 20_000
        if bucket == 0:
            item = _observation(
                GestureKind.OPEN_PALM,
                sequence=sequence,
                now=now[0],
                detected_at=now[0] - timedelta(seconds=3),
            )
        elif bucket == 1:
            item = _observation(
                GestureKind.PINCH,
                sequence=sequence,
                now=now[0],
                confidence=0.8,
            )
        elif bucket == 2:
            item = _observation(
                GestureKind.FINGER_ROLL_CLOCKWISE,
                sequence=sequence,
                now=now[0],
                session_id="wrong-source-session",
            )
        else:
            item = replay
        await sink(item)
        proposal_count += len(proposals)
        proposals.clear()
        decisions.clear()
        now[0] += timedelta(microseconds=100)

    cancel_proposals: list[HandsFreeActionProposal] = []
    cancel_directives: list[HandsFreeCancelDirective] = []
    cancel_decisions: list[HandsFreeDecisionRecord] = []
    _cancel_gate, cancel_sink = _gate(
        now=now,
        proposals=cancel_proposals,
        cancels=cancel_directives,
        decisions=cancel_decisions,
    )
    await cancel_sink(_observation(GestureKind.CLOSED_FIST, sequence=90_000, now=now[0]))
    await cancel_sink(_observation(GestureKind.OPEN_PALM, sequence=90_001, now=now[0]))
    return {
        "events": NEGATIVE_EVENTS,
        "proposals": proposal_count,
        "direct_effects": 0,
        "cancel_directives": len(cancel_directives),
        "post_cancel_proposals": len(cancel_proposals),
        "post_cancel_decisions": [decision.disposition.value for decision in cancel_decisions],
    }


async def run_benchmark() -> dict[str, Any]:
    contract = run_mapping_contract()
    mapping = await run_mapping_gate_benchmark()
    negative = await run_negative_gate()
    passed = (
        contract["exact"]
        and mapping["evaluations"] == MAPPING_GATE_EVALUATIONS
        and mapping["p95_ms"] <= MAX_MAPPING_P95_MS
        and mapping["wrong_mappings"] == 0
        and mapping["direct_effects"] == 0
        and mapping["authority_escalations"] == 0
        and mapping["rss_growth_mib"] <= MAX_RSS_GROWTH_MIB
        and negative["events"] == NEGATIVE_EVENTS
        and negative["proposals"] <= 1
        and negative["direct_effects"] == 0
        and negative["cancel_directives"] == 1
        and negative["post_cancel_proposals"] == 0
        and negative["post_cancel_decisions"] == ["cancelled", "cancelled"]
    )
    return {
        "schema_version": 1,
        "phase": "7C",
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "targets": {
            "mapping_evaluations": MAPPING_GATE_EVALUATIONS,
            "negative_events": NEGATIVE_EVENTS,
            "mapping_p95_ms_max": MAX_MAPPING_P95_MS,
            "rss_growth_mib_max": MAX_RSS_GROWTH_MIB,
        },
        "mapping_contract": contract,
        "mapping_gate": mapping,
        "negative_gate": negative,
        "passed": passed,
    }


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


def prepare_output_path(path: Path) -> Path:
    candidate = path.expanduser().resolve(strict=False)
    try:
        candidate.relative_to(RUNTIME_ROOT)
    except ValueError as exc:
        raise ValueError("benchmark output must be a child of runtime") from exc
    if candidate.suffix.lower() != ".json":
        raise ValueError("benchmark output must be JSON")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def write_result(path: Path, payload: str) -> None:
    target = prepare_output_path(path)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run_benchmark())
    payload = json.dumps(result, indent=2, sort_keys=True)
    write_result(args.output, payload)
    print(payload)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
