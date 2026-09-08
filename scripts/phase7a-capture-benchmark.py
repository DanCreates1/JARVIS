"""Fixed synthetic Phase 7A capture-boundary and privacy benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import statistics
import time
from contextlib import suppress
from pathlib import Path

from jarvis.vision.fakes import FakeCaptureIndicator, FakeCaptureSettings, FakeFrameSource
from jarvis.vision.models import (
    CaptureError,
    CapturePurpose,
    CaptureRegion,
    CaptureRequest,
    CaptureSource,
)
from jarvis.vision.session import CaptureController

MIN_RUNS = 200
MIN_SECURITY_SCENARIOS = 100
MAX_BOUNDARY_P95_MS = 25.0


def _request() -> CaptureRequest:
    return CaptureRequest(
        source=CaptureSource.CAMERA,
        source_id="camera:0",
        purpose=CapturePurpose.DIAGNOSTIC,
        region=CaptureRegion(x=0, y=0, width=2, height=2),
        requested_fps=15,
        max_frames=1,
        max_duration_ms=1_000,
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


async def _run_boundary_samples(count: int) -> tuple[list[float], int]:
    latencies: list[float] = []
    leaked_buffers = 0
    for _ in range(count):
        source = FakeFrameSource()
        controller = CaptureController(
            source=source,
            indicator=FakeCaptureIndicator(),
            settings_store=FakeCaptureSettings(),
            host_enabled=True,
            control_poll_seconds=0.01,
        )

        async def consume(frame) -> None:  # type: ignore[no-untyped-def]
            if len(frame.pixels) != 12:
                raise AssertionError("unexpected synthetic frame size")

        started = time.perf_counter_ns()
        result = await controller.run(_request(), consumer=consume)
        latencies.append((time.perf_counter_ns() - started) / 1_000_000)
        if result.frames_delivered != 1:
            raise AssertionError("synthetic session did not deliver exactly one frame")
        if source.last_frame is None or not source.last_frame.released:
            leaked_buffers += 1
    return latencies, leaked_buffers


async def _run_security_scenarios(count: int) -> tuple[int, int, int]:
    violations = 0
    total_opens = 0
    total_deliveries = 0
    for index in range(count):
        case = index % 5
        source = FakeFrameSource(
            frame_age_ms=500 if case == 3 else 0,
            source_id_override="camera:1" if case == 4 else None,
        )
        indicator = FakeCaptureIndicator(fail_show=case == 2)
        settings = FakeCaptureSettings(enabled=case != 1)
        controller = CaptureController(
            source=source,
            indicator=indicator,
            settings_store=settings,
            host_enabled=case != 0,
            control_poll_seconds=0.01,
        )
        deliveries = 0

        async def consume(_frame) -> None:  # type: ignore[no-untyped-def]
            nonlocal deliveries
            deliveries += 1

        with suppress(CaptureError):
            await controller.run(
                _request().model_copy(update={"max_frame_age_ms": 50}),
                consumer=consume,
            )
        total_opens += source.open_count
        total_deliveries += deliveries
        if case in {0, 1, 2} and source.open_count != 0:
            violations += 1
        if deliveries != 0:
            violations += 1
        if case in {3, 4} and (source.last_frame is None or not source.last_frame.released):
            violations += 1
    return violations, total_opens, total_deliveries


async def run_benchmark(runs: int, security_scenarios: int) -> dict[str, object]:
    if runs < MIN_RUNS or security_scenarios < MIN_SECURITY_SCENARIOS:
        raise ValueError(
            f"requires at least {MIN_RUNS} runs and {MIN_SECURITY_SCENARIOS} security scenarios"
        )
    latencies, leaked_buffers = await _run_boundary_samples(runs)
    violations, opens, deliveries = await _run_security_scenarios(security_scenarios)
    p50 = statistics.median(latencies)
    p95 = _percentile(latencies, 0.95)
    passed = p95 <= MAX_BOUNDARY_P95_MS and leaked_buffers == 0 and violations == 0
    return {
        "schema_version": 1,
        "phase": "7A",
        "capture_boundary": {
            "samples": runs,
            "p50_ms": round(p50, 6),
            "p95_ms": round(p95, 6),
            "target_p95_ms": MAX_BOUNDARY_P95_MS,
            "leaked_buffers": leaked_buffers,
        },
        "privacy_security": {
            "scenarios": security_scenarios,
            "violations": violations,
            "source_opens_in_explicit_stale_or_mismatch_cases": opens,
            "frames_delivered": deliveries,
        },
        "runtime": {
            "python": platform.python_version(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "adapter": "deterministic fake; no camera or screen pixels read",
        },
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=MIN_RUNS)
    parser.add_argument("--security-scenarios", type=int, default=MIN_SECURITY_SCENARIOS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run_benchmark(args.runs, args.security_scenarios))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    boundary = result["capture_boundary"]
    privacy = result["privacy_security"]
    print(
        "Phase 7A benchmark: "
        f"samples={boundary['samples']} p50={boundary['p50_ms']}ms "
        f"p95={boundary['p95_ms']}ms leaked={boundary['leaked_buffers']}; "
        f"security={privacy['scenarios']} violations={privacy['violations']}; "
        f"passed={result['passed']}"
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
