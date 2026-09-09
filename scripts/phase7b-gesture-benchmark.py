"""Deterministic Phase 7B gesture-core accuracy, false-trigger, and latency gate."""

from __future__ import annotations

import argparse
import ctypes
import gc
import json
import math
import os
import platform
import statistics
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis.gestures.models import (
    GestureCalibrationProfile,
    GestureKind,
    GestureObservation,
    Handedness,
    HandObservation,
    LandmarkFrame,
    NormalizedLandmark,
)
from jarvis.gestures.recognizer import TemporalGestureRecognizer

CORPUS_SEQUENCES = 1_000
POSITIVE_SEQUENCES_PER_GESTURE = 100
NEGATIVE_SOAK_FRAMES = 36_000
CLASSIFIER_FRAMES = 10_000
MIN_MACRO_PRECISION = 0.95
MIN_MACRO_RECALL = 0.95
MIN_GESTURE_PRECISION = 0.90
MIN_GESTURE_RECALL = 0.90
MAX_FALSE_ACTIVATIONS_PER_HOUR = 0.1
MAX_CLASSIFIER_P95_MS = 5.0
MAX_RSS_GROWTH_MIB = 50.0
BASE_TIME = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)
RUNTIME_ROOT = (Path.cwd() / "runtime").resolve()


def _hand(
    pose: str,
    *,
    handedness: Handedness,
    confidence: float = 0.95,
    angle: float = 0.0,
    scale: float = 1.0,
    mirrored: bool = False,
) -> HandObservation:
    points = [(0.5, 0.65, 0.0) for _ in range(21)]
    points[0] = (0.5, 0.8, 0.0)
    points[5] = (0.34, 0.56, 0.0)
    points[9] = (0.45, 0.52, 0.0)
    points[13] = (0.56, 0.54, 0.0)
    points[17] = (0.67, 0.59, 0.0)
    points[4] = (0.2, 0.38, 0.0)
    pips = (6, 10, 14, 18)
    tips = (8, 12, 16, 20)
    if pose in {"open", "pinch"}:
        for offset, (pip, tip) in enumerate(zip(pips, tips, strict=True)):
            x = 0.34 + offset * 0.11
            points[pip] = (x, 0.38 + offset * 0.01, 0.0)
            points[tip] = (x, 0.14 + offset * 0.015, 0.0)
        if pose == "pinch":
            index = points[8]
            points[4] = (index[0] + 0.01, index[1] + 0.01, 0.0)
    elif pose == "fist":
        for offset, (pip, tip) in enumerate(zip(pips, tips, strict=True)):
            x = 0.39 + offset * 0.07
            points[pip] = (x, 0.57, 0.0)
            points[tip] = (x, 0.72, 0.0)
    elif pose == "roll":
        points[6] = (0.501, 0.799, 0.0)
        center_x = (points[0][0] + points[5][0] + points[9][0] + points[17][0]) / 4
        center_y = (points[0][1] + points[5][1] + points[9][1] + points[17][1]) / 4
        points[8] = (
            center_x + 0.19 * math.cos(angle),
            center_y + 0.19 * math.sin(angle),
            0.0,
        )
        for offset, (pip, tip) in enumerate(zip(pips[1:], tips[1:], strict=True)):
            x = 0.45 + offset * 0.08
            points[pip] = (x, 0.58, 0.0)
            points[tip] = (x, 0.73, 0.0)
    elif pose != "ambiguous":
        raise ValueError("unknown synthetic pose")
    transformed = []
    for x, y, z in points:
        x = 0.5 + (x - 0.5) * scale
        y = 0.5 + (y - 0.5) * scale
        if mirrored:
            x = 1 - x
        transformed.append(NormalizedLandmark(x=x, y=y, z=z * scale))
    return HandObservation(
        handedness=handedness,
        handedness_confidence=confidence,
        tracking_confidence=confidence,
        landmarks=tuple(transformed),
    )


def _frame(
    *,
    session_id: str,
    sequence: int,
    tick: int,
    hands: tuple[HandObservation, ...],
) -> LandmarkFrame:
    return LandmarkFrame(
        session_id=session_id,
        sequence=sequence,
        captured_at=BASE_TIME + timedelta(milliseconds=tick * 100),
        monotonic_ns=tick * 100_000_000,
        hands=hands,
    )


def _recognize_sequence(
    *,
    session_id: str,
    observations: list[tuple[HandObservation, ...]],
    mirrored: bool,
) -> GestureKind | None:
    now = [BASE_TIME]
    recognizer = TemporalGestureRecognizer(
        GestureCalibrationProfile(
            mirrored_input=mirrored,
            cooldown_ms=250,
            max_observation_age_ms=1_000,
            roll_min_radians=1.2,
        ),
        now=lambda: now[0],
        id_factory=lambda: "benchmark1",
    )
    events: list[GestureObservation] = []
    for sequence, hands in enumerate(observations, start=1):
        item = _frame(session_id=session_id, sequence=sequence, tick=sequence, hands=hands)
        now[0] = item.captured_at + timedelta(milliseconds=1)
        event = recognizer.consume(item)
        if event is not None:
            events.append(event)
    if len(events) > 1:
        return None
    return events[0].gesture if events else None


def run_corpus() -> dict[str, Any]:
    true_positive: dict[GestureKind, int] = defaultdict(int)
    false_positive: dict[GestureKind, int] = defaultdict(int)
    false_negative: dict[GestureKind, int] = defaultdict(int)
    gestures = (
        (GestureKind.CLOSED_FIST, "fist", None),
        (GestureKind.OPEN_PALM, "open", None),
        (GestureKind.PINCH, "pinch", None),
        (GestureKind.FINGER_ROLL_CLOCKWISE, "roll", 1),
        (GestureKind.FINGER_ROLL_COUNTERCLOCKWISE, "roll", -1),
    )
    sequence_count = 0
    for expected, pose, roll_direction in gestures:
        for sample in range(POSITIVE_SEQUENCES_PER_GESTURE):
            mirrored = sample % 2 == 1
            handedness = Handedness.LEFT if sample % 4 < 2 else Handedness.RIGHT
            scale = (0.75, 0.9, 1.0, 1.15)[sample % 4]
            if roll_direction is None:
                observations = [
                    (
                        _hand(
                            pose,
                            handedness=handedness,
                            scale=scale,
                            mirrored=mirrored,
                        ),
                    )
                ] * 3
            else:
                angles = [roll_direction * value for value in (0.0, 0.35, 0.7, 1.05, 1.4, 1.75)]
                observations = [
                    (
                        _hand(
                            pose,
                            handedness=handedness,
                            angle=angle,
                            scale=scale,
                            mirrored=mirrored,
                        ),
                    )
                    for angle in angles
                ]
            if sample % 5 == 0:
                observations = [(), *observations]
            predicted = _recognize_sequence(
                session_id=f"positive-{sequence_count}",
                observations=observations,
                mirrored=mirrored,
            )
            _score(expected, predicted, true_positive, false_positive, false_negative)
            sequence_count += 1
    negative_kinds = ("no_hand", "ambiguous", "low_confidence", "conflict", "similar_roll")
    for sample in range(CORPUS_SEQUENCES - sequence_count):
        kind = negative_kinds[sample % len(negative_kinds)]
        handedness = Handedness.LEFT if sample % 2 else Handedness.RIGHT
        if kind == "no_hand":
            observations = [()] * 6
        elif kind == "ambiguous":
            observations = [(_hand("ambiguous", handedness=handedness),)] * 6
        elif kind == "low_confidence":
            observations = [(_hand("open", handedness=handedness, confidence=0.7),)] * 6
        elif kind == "conflict":
            observations = [
                (
                    _hand("open", handedness=Handedness.LEFT),
                    _hand("fist", handedness=Handedness.RIGHT),
                )
            ] * 6
        else:
            observations = [
                (_hand("roll", handedness=handedness, angle=angle),)
                for angle in (0.0, 0.5, 0.1, 0.6, 0.2, 0.7)
            ]
        predicted = _recognize_sequence(
            session_id=f"negative-{sample}", observations=observations, mirrored=False
        )
        if predicted is not None:
            false_positive[predicted] += 1
        sequence_count += 1
    per_gesture = {}
    for gesture in GestureKind:
        tp = true_positive[gesture]
        fp = false_positive[gesture]
        fn = false_negative[gesture]
        per_gesture[gesture.value] = {
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
        }
    macro_precision = statistics.fmean(item["precision"] for item in per_gesture.values())
    macro_recall = statistics.fmean(item["recall"] for item in per_gesture.values())
    return {
        "sequences": sequence_count,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "per_gesture": per_gesture,
    }


def _score(
    expected: GestureKind,
    predicted: GestureKind | None,
    true_positive: dict[GestureKind, int],
    false_positive: dict[GestureKind, int],
    false_negative: dict[GestureKind, int],
) -> None:
    if predicted is expected:
        true_positive[expected] += 1
        return
    false_negative[expected] += 1
    if predicted is not None:
        false_positive[predicted] += 1


def run_negative_soak() -> dict[str, Any]:
    now = [BASE_TIME]
    recognizer = TemporalGestureRecognizer(
        GestureCalibrationProfile(
            mirrored_input=False,
            cooldown_ms=250,
            max_observation_age_ms=1_000,
            roll_min_radians=1.2,
        ),
        now=lambda: now[0],
    )
    false_activations = 0
    for index in range(NEGATIVE_SOAK_FRAMES):
        sequence = index % 300 + 1
        session_id = f"negative-soak-{index // 300}"
        kind = index % 5
        if kind == 0:
            hands: tuple[HandObservation, ...] = ()
        elif kind == 1:
            hands = (_hand("ambiguous", handedness=Handedness.RIGHT),)
        elif kind == 2:
            hands = (_hand("open", handedness=Handedness.LEFT, confidence=0.7),)
        elif kind == 3:
            hands = (
                _hand("open", handedness=Handedness.LEFT),
                _hand("fist", handedness=Handedness.RIGHT),
            )
        else:
            angle = (0.0, 0.35, 0.05, 0.4)[index % 4]
            hands = (_hand("roll", handedness=Handedness.RIGHT, angle=angle),)
        item = _frame(session_id=session_id, sequence=sequence, tick=index + 1, hands=hands)
        now[0] = item.captured_at + timedelta(milliseconds=1)
        if recognizer.consume(item) is not None:
            false_activations += 1
    return {
        "frames": NEGATIVE_SOAK_FRAMES,
        "simulated_hours": NEGATIVE_SOAK_FRAMES / 10 / 3_600,
        "false_activations": false_activations,
        "false_activations_per_hour": false_activations / (NEGATIVE_SOAK_FRAMES / 10 / 3_600),
        "action_proposals": 0,
        "action_executions": 0,
    }


def run_classifier_benchmark() -> dict[str, Any]:
    now = [BASE_TIME]
    recognizer = TemporalGestureRecognizer(
        GestureCalibrationProfile(max_observation_age_ms=1_000), now=lambda: now[0]
    )
    for index in range(1_000):
        sequence = index % 300 + 1
        item = _frame(
            session_id=f"warm-{index // 300}",
            sequence=sequence,
            tick=index + 1,
            hands=(_hand("ambiguous", handedness=Handedness.RIGHT),),
        )
        now[0] = item.captured_at + timedelta(milliseconds=1)
        recognizer.consume(item)
    gc.collect()
    rss_before = _rss_bytes()
    samples_ms = []
    emissions = 0
    for index in range(CLASSIFIER_FRAMES):
        sequence = index % 300 + 1
        item = _frame(
            session_id=f"benchmark-{index // 300}",
            sequence=sequence,
            tick=index + 2_000,
            hands=(_hand("ambiguous", handedness=Handedness.RIGHT),),
        )
        now[0] = item.captured_at + timedelta(milliseconds=1)
        started = time.perf_counter_ns()
        event = recognizer.consume(item)
        samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        emissions += event is not None
    gc.collect()
    rss_after = _rss_bytes()
    ordered = sorted(samples_ms)
    return {
        "frames": CLASSIFIER_FRAMES,
        "p50_ms": statistics.median(ordered),
        "p95_ms": ordered[math.ceil(len(ordered) * 0.95) - 1],
        "invalid_emissions": emissions,
        "rss_growth_mib": max(0, rss_after - rss_before) / (1024 * 1024),
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


def run() -> dict[str, Any]:
    corpus = run_corpus()
    soak = run_negative_soak()
    classifier = run_classifier_benchmark()
    per_gesture_pass = all(
        item["precision"] >= MIN_GESTURE_PRECISION and item["recall"] >= MIN_GESTURE_RECALL
        for item in corpus["per_gesture"].values()
    )
    passed = (
        corpus["sequences"] >= CORPUS_SEQUENCES
        and corpus["macro_precision"] >= MIN_MACRO_PRECISION
        and corpus["macro_recall"] >= MIN_MACRO_RECALL
        and per_gesture_pass
        and soak["frames"] >= NEGATIVE_SOAK_FRAMES
        and soak["false_activations_per_hour"] <= MAX_FALSE_ACTIVATIONS_PER_HOUR
        and soak["action_proposals"] == 0
        and soak["action_executions"] == 0
        and classifier["frames"] >= CLASSIFIER_FRAMES
        and classifier["p95_ms"] <= MAX_CLASSIFIER_P95_MS
        and classifier["invalid_emissions"] == 0
        and classifier["rss_growth_mib"] <= MAX_RSS_GROWTH_MIB
    )
    return {
        "schema_version": 1,
        "scope": "synthetic-local-gesture-core-only",
        "privacy": "no pixels, recordings, raw landmark dumps, cloud, mappings, or actions",
        "runtime": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "thresholds": {
            "corpus_sequences": CORPUS_SEQUENCES,
            "macro_precision_min": MIN_MACRO_PRECISION,
            "macro_recall_min": MIN_MACRO_RECALL,
            "per_gesture_precision_min": MIN_GESTURE_PRECISION,
            "per_gesture_recall_min": MIN_GESTURE_RECALL,
            "negative_soak_frames": NEGATIVE_SOAK_FRAMES,
            "false_activations_per_hour_max": MAX_FALSE_ACTIVATIONS_PER_HOUR,
            "classifier_frames": CLASSIFIER_FRAMES,
            "classifier_p95_ms_max": MAX_CLASSIFIER_P95_MS,
            "rss_growth_mib_max": MAX_RSS_GROWTH_MIB,
        },
        "corpus": corpus,
        "negative_soak": soak,
        "classifier": classifier,
        "passed": passed,
    }


def prepare_output_path(path: Path) -> Path:
    candidate = path.resolve()
    try:
        candidate.relative_to(RUNTIME_ROOT)
    except ValueError as exc:
        raise ValueError("benchmark output must be a child of runtime") from exc
    if candidate == RUNTIME_ROOT or candidate.suffix.casefold() != ".json":
        raise ValueError("benchmark output must be a JSON file below runtime")
    if candidate.exists():
        raise FileExistsError("benchmark output path must be new")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def write_result(path: Path, rendered: str) -> None:
    output = prepare_output_path(path)
    with output.open("x", encoding="utf-8", errors="strict", newline="\n") as handle:
        handle.write(rendered + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main() -> int:
    arguments = parse_args()
    result = run()
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if arguments.output is not None:
        write_result(arguments.output, rendered)
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
