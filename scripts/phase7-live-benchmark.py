"""Authorized aggregate-only Phase 7 detector-to-proposal live benchmark."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import math
import os
import platform
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path
from typing import Any

from jarvis.computer.audio import MasterVolumeState
from jarvis.computer.config import ComputerAccessPolicy, HandsFreeMappingsPolicy
from jarvis.computer.gesture_bridge import GestureHandsFreeGateSink
from jarvis.computer.hands_free import (
    BoundedHandsFreeReplayCache,
    HandsFreeActionProposal,
    HandsFreeCancelDirective,
    HandsFreeDecisionRecord,
    HandsFreeProposalGate,
)
from jarvis.config import Settings
from jarvis.gestures.models import (
    GestureCalibrationProfile,
    GestureKind,
    GestureObservation,
    LandmarkFrame,
)
from jarvis.gestures.opencv_detector import OpenCVDNNHandLandmarkDetector
from jarvis.gestures.pipeline import GestureFrameProcessor
from jarvis.gestures.recognizer import TemporalGestureRecognizer
from jarvis.permissions import (
    ActorContext,
    AuthenticationAssurance,
    InteractionInterface,
)
from jarvis.vision.bootstrap import build_vision_capture
from jarvis.vision.models import (
    CaptureControl,
    CapturePurpose,
    CaptureRegion,
    CaptureRequest,
    CaptureSource,
    EphemeralFrame,
)

ACKNOWLEDGEMENT = "camera:0-local-ephemeral-no-effects"
RUNTIME_ROOT = (Path.cwd() / "runtime").resolve()
SOAK_SECONDS = 30 * 60
TARGET_FPS = 10.0
MAX_DETECTOR_P95_MS = 100.0
MAX_PIPELINE_P50_MS = 75.0
MAX_PIPELINE_P95_MS = 150.0
MIN_PROCESSED_FPS = 9.0
MAX_TOTAL_CPU_PERCENT = 35.0
MAX_RSS_GROWTH_MIB = 50.0
MAX_FALSE_ACTIVATIONS_PER_HOUR = 0.1


class _MeasuredDetector:
    def __init__(self, detector: OpenCVDNNHandLandmarkDetector) -> None:
        self.detector = detector
        self.samples_ms: list[float] = []
        self.frames_with_hands = 0
        self.hands = 0

    async def detect(self, frame: EphemeralFrame) -> LandmarkFrame:
        started = time.perf_counter_ns()
        result = await self.detector.detect(frame)
        self.samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        if result.hands:
            self.frames_with_hands += 1
            self.hands += len(result.hands)
        return result

    async def close(self) -> None:
        # Detector is shared across bounded 30-second capture segments.
        return None


class _MeasuredSink:
    def __init__(self) -> None:
        self.events: Counter[str] = Counter()
        self.proposals: list[HandsFreeActionProposal] = []
        self.cancels: list[HandsFreeCancelDirective] = []
        self.decisions: list[HandsFreeDecisionRecord] = []
        self.policy_samples_ms: list[float] = []
        self.authority_violations = 0
        self._gate_sink: GestureHandsFreeGateSink | None = None

    async def __call__(self, event: GestureObservation) -> None:
        self.events[event.gesture.value] += 1
        if self._gate_sink is None:
            self._gate_sink = _build_gate_sink(event.session_id, self)
        started = time.perf_counter_ns()
        await self._gate_sink(event)
        self.policy_samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        for proposal in self.proposals:
            if (
                proposal.permission_level.value != 1
                or proposal.approval_granted
                or proposal.execution_authorized
            ):
                self.authority_violations += 1


def _build_gate_sink(source_session_id: str, metrics: _MeasuredSink) -> GestureHandsFreeGateSink:
    now = datetime.now(UTC)
    actor = ActorContext(
        host_id="phase7-live-host",
        session_id="phase7-live-actor",
        device_id="phase7-live-camera",
        interface=InteractionInterface.VOICE,
        assurance=AuthenticationAssurance.LOCAL_SESSION,
        authenticated_at=now,
        capabilities=("computer.media.control", "computer.volume.set"),
    )
    policy = ComputerAccessPolicy(
        enabled=True,
        policy_version="phase7-live-benchmark",
        controlled_root=RUNTIME_ROOT / "phase7-live-controlled",
        hands_free_mappings=HandsFreeMappingsPolicy(
            volume_step=True,
            media_play_pause=True,
            mute_toggle=True,
            cancel_session=True,
        ),
    )
    ids = count(1)
    gate = HandsFreeProposalGate(
        policy=policy,
        actor=actor,
        active_source_session_id=source_session_id,
        proposal_callback=metrics.proposals.append,
        cancel_callback=metrics.cancels.append,
        decision_sink=metrics.decisions.append,
        volume_reader=lambda: MasterVolumeState(scalar=0.5, muted=False),
        replay_store=BoundedHandsFreeReplayCache(maximum_entries=10_000),
        rate_limit=timedelta(seconds=1),
        id_factory=lambda: f"{next(ids):016d}",
    )
    return GestureHandsFreeGateSink(gate=gate, actor=actor)


def _quantile(samples: list[float], percentile: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(len(ordered) * percentile) - 1)]


def _working_set_bytes() -> int:
    if os.name != "nt":
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1_024)

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
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    process = kernel32.GetCurrentProcess()
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo  # type: ignore[attr-defined]
    get_memory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    get_memory.restype = ctypes.c_int
    ok = get_memory(process, ctypes.byref(counters), counters.cb)
    if not ok:
        raise OSError("GetProcessMemoryInfo failed")
    return int(counters.WorkingSetSize)


def _system_times() -> tuple[int, int, int] | None:
    if os.name != "nt":
        return None
    idle = ctypes.c_ulonglong()
    kernel = ctypes.c_ulonglong()
    user = ctypes.c_ulonglong()
    ok = ctypes.windll.kernel32.GetSystemTimes(  # type: ignore[attr-defined]
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    )
    if not ok:
        return None
    return idle.value, kernel.value, user.value


def _total_cpu_percent(
    before: tuple[int, int, int] | None, after: tuple[int, int, int] | None
) -> float | None:
    if before is None or after is None:
        return None
    idle = after[0] - before[0]
    total = (after[1] - before[1]) + (after[2] - before[2])
    if total <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * (total - idle) / total))


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    settings = Settings(
        data_dir=args.data_dir,
        vision_capture_enabled=True,
    )
    detector = OpenCVDNNHandLandmarkDetector(settings.vision_model_dir)
    measured_detector = _MeasuredDetector(detector)
    pipeline_samples_ms: list[float] = []
    events: Counter[str] = Counter()
    proposal_count = 0
    cancel_count = 0
    decision_count = 0
    authority_violations = 0
    segments = 0
    frames = 0
    bytes_delivered = 0
    rss_start = _working_set_bytes()
    rss_peak = rss_start
    cpu_start = _system_times()
    started = time.monotonic()
    deadline = started + args.duration_seconds
    settings_store = None
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining < 0.1:
                break
            segment_ms = min(30_000, max(100, math.floor(remaining * 1_000)))
            request = CaptureRequest(
                source=CaptureSource.CAMERA,
                source_id="camera:0",
                purpose=CapturePurpose.GESTURE_INPUT,
                region=CaptureRegion(x=0, y=0, width=640, height=480),
                requested_fps=TARGET_FPS,
                camera_exposure=args.exposure,
                max_frames=min(300, max(1, math.ceil(segment_ms * TARGET_FPS / 1_000))),
                max_duration_ms=segment_ms,
                consumer_timeout_ms=1_000,
            )
            components = build_vision_capture(settings)
            settings_store = components.settings_store
            settings_store.save_control(CaptureControl(enabled=True))
            segment_sink = _MeasuredSink()
            processor = GestureFrameProcessor(
                detector=measured_detector,
                recognizer=TemporalGestureRecognizer(
                    GestureCalibrationProfile(mirrored_input=args.mirrored_input)
                ),
                sink=segment_sink,
            )

            async def measured_processor(
                frame: EphemeralFrame,
                _processor: GestureFrameProcessor = processor,
            ) -> None:
                nonlocal rss_peak
                frame_started = time.perf_counter_ns()
                await _processor(frame)
                pipeline_samples_ms.append((time.perf_counter_ns() - frame_started) / 1_000_000)
                rss_peak = max(rss_peak, _working_set_bytes())

            try:
                summary = await components.controller.run(request, consumer=measured_processor)
            finally:
                await processor.close()
                await components.close()
            segments += 1
            frames += summary.frames_delivered
            bytes_delivered += summary.bytes_delivered
            events.update(segment_sink.events)
            proposal_count += len(segment_sink.proposals)
            cancel_count += len(segment_sink.cancels)
            decision_count += len(segment_sink.decisions)
            authority_violations += segment_sink.authority_violations
            if args.duration_seconds >= 60:
                elapsed = time.monotonic() - started
                print(
                    f"progress seconds={elapsed:.1f} frames={frames} "
                    f"events={sum(events.values())} proposals={proposal_count}",
                    flush=True,
                )
    finally:
        await detector.close()
        if settings_store is not None:
            settings_store.save_control(CaptureControl(enabled=False))
    finished = time.monotonic()
    cpu_end = _system_times()
    duration = finished - started
    detector_p50 = _quantile(measured_detector.samples_ms, 0.5)
    detector_p95 = _quantile(measured_detector.samples_ms, 0.95)
    pipeline_p50 = _quantile(pipeline_samples_ms, 0.5)
    pipeline_p95 = _quantile(pipeline_samples_ms, 0.95)
    total_events = sum(events.values())
    false_rate = total_events * 3_600 / duration if args.expected_no_hand else None
    expected_matches = events.get(args.expected_gesture, 0) if args.expected_gesture else None
    unexpected_events = total_events - expected_matches if expected_matches is not None else None
    cpu_percent = _total_cpu_percent(cpu_start, cpu_end)
    rss_growth_mib = max(0, rss_peak - rss_start) / (1_024 * 1_024)
    processed_fps = frames / duration
    soak_gate = args.duration_seconds >= SOAK_SECONDS
    passed = (
        frames > 0
        and detector_p95 is not None
        and detector_p95 <= MAX_DETECTOR_P95_MS
        and pipeline_p50 is not None
        and pipeline_p50 <= MAX_PIPELINE_P50_MS
        and pipeline_p95 is not None
        and pipeline_p95 <= MAX_PIPELINE_P95_MS
        and processed_fps >= MIN_PROCESSED_FPS
        and (cpu_percent is None or cpu_percent <= MAX_TOTAL_CPU_PERCENT)
        and rss_growth_mib <= MAX_RSS_GROWTH_MIB
        and authority_violations == 0
        and (
            not args.expected_no_hand
            or (false_rate is not None and false_rate <= MAX_FALSE_ACTIVATIONS_PER_HOUR)
        )
        and (
            args.expected_gesture is None
            or (
                expected_matches is not None
                and expected_matches >= 1
                and unexpected_events == 0
                and measured_detector.frames_with_hands >= 3
            )
        )
        and (not soak_gate or frames >= 1_800)
    )
    return {
        "schema_version": 1,
        "phase": "7-live",
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": passed,
        "soak_gate": soak_gate,
        "authorization": {
            "source_id": "camera:0",
            "local_only": True,
            "ephemeral": True,
            "executed_os_effects": 0,
            "acknowledgement": ACKNOWLEDGEMENT,
            "condition_label": args.condition_label,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "opencv": __import__("cv2").__version__,
            "camera": "USB2.0 HD UVC WebCam",
            "resolution": "640x480",
            "requested_fps": TARGET_FPS,
            "camera_exposure": args.exposure,
            "mirrored_input": args.mirrored_input,
        },
        "targets": {
            "soak_seconds_min": SOAK_SECONDS,
            "frames_min": 1_800,
            "detector_p95_ms_max": MAX_DETECTOR_P95_MS,
            "pipeline_p50_ms_max": MAX_PIPELINE_P50_MS,
            "pipeline_p95_ms_max": MAX_PIPELINE_P95_MS,
            "processed_fps_min": MIN_PROCESSED_FPS,
            "total_cpu_percent_max": MAX_TOTAL_CPU_PERCENT,
            "rss_growth_mib_max": MAX_RSS_GROWTH_MIB,
            "false_activations_per_hour_max": MAX_FALSE_ACTIVATIONS_PER_HOUR,
        },
        "observed": {
            "duration_seconds": duration,
            "segments": segments,
            "frames": frames,
            "bytes_delivered": bytes_delivered,
            "processed_fps": processed_fps,
            "detector_p50_ms": detector_p50,
            "detector_p95_ms": detector_p95,
            "pipeline_p50_ms": pipeline_p50,
            "pipeline_p95_ms": pipeline_p95,
            "total_cpu_percent": cpu_percent,
            "rss_growth_mib": rss_growth_mib,
            "frames_with_hands": measured_detector.frames_with_hands,
            "hands": measured_detector.hands,
            "gesture_events": dict(sorted(events.items())),
            "expected_gesture": args.expected_gesture,
            "expected_matches": expected_matches,
            "unexpected_events": unexpected_events,
            "false_activations_per_hour": false_rate,
            "proposals": proposal_count,
            "cancels": cancel_count,
            "policy_decisions": decision_count,
            "authority_violations": authority_violations,
            "executed_os_effects": 0,
        },
        "privacy": {
            "saved_frames": 0,
            "saved_landmarks": 0,
            "cloud_requests": 0,
            "output_is_aggregate_only": True,
        },
    }


def _runtime_path(value: str) -> Path:
    path = Path(value).resolve()
    if path != RUNTIME_ROOT and RUNTIME_ROOT not in path.parents:
        raise argparse.ArgumentTypeError("path must stay under ignored runtime/")
    return path


def prepare_output_path(path: Path) -> Path:
    output = path.resolve()
    if output == RUNTIME_ROOT or RUNTIME_ROOT not in output.parents:
        raise ValueError("output must be a child of ignored runtime/")
    if output.suffix.casefold() != ".json":
        raise ValueError("output must use a JSON extension")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def write_result(path: Path, payload: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acknowledge-camera", required=True)
    parser.add_argument("--duration-seconds", type=int, required=True, choices=range(3, 1_801))
    parser.add_argument("--expected-no-hand", action="store_true")
    parser.add_argument("--expected-gesture", choices=[item.value for item in GestureKind])
    parser.add_argument(
        "--condition-label",
        default="unlabeled",
        choices=[
            "unlabeled",
            "normal-near-right",
            "normal-far-left",
            "low-near-left",
            "low-far-right",
            "partial-occlusion",
            "alternate-background",
            "similar-movement",
            "no-hand",
            "soak",
        ],
    )
    parser.add_argument("--mirrored-input", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--exposure", type=int, default=-4, choices=range(-13, 1))
    parser.add_argument("--data-dir", type=_runtime_path, required=True)
    parser.add_argument("--output", type=_runtime_path, required=True)
    args = parser.parse_args()
    if args.acknowledge_camera != ACKNOWLEDGEMENT:
        parser.error(f"--acknowledge-camera must equal {ACKNOWLEDGEMENT!r}")
    if args.expected_no_hand and args.expected_gesture is not None:
        parser.error("--expected-no-hand and --expected-gesture are mutually exclusive")
    result = asyncio.run(_run(args))
    output = prepare_output_path(args.output)
    payload = json.dumps(result, indent=2, sort_keys=True)
    write_result(output, payload)
    print(payload)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
