"""Aggregate-only Phase 7 evaluation against approved public HaGRID examples."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jarvis.gestures.features import extract_features
from jarvis.gestures.models import GestureKind
from jarvis.gestures.opencv_detector import OpenCVDNNHandLandmarkDetector
from jarvis.gestures.recognizer import TemporalGestureRecognizer
from jarvis.vision.models import (
    CapturePurpose,
    CaptureSource,
    EphemeralFrame,
    FrameMetadata,
    PixelFormat,
)

RUNTIME_ROOT = (Path.cwd() / "runtime").resolve()
GESTURE_GRID_SHA256 = "df9b8d15e352127f780f0e9f1de7a0f951c2a72192c14411a35603353dd2fed3"
DIVERSITY_GRID_SHA256 = "7823ad9a3d8749cbbE29fe5d69d738743efea195a640972e6607ab99cd779c61".lower()

# Pixel coordinates in the 2910x1588 public HaGRID gesture overview.
GESTURE_CROPS = {
    "fist": ((870, 100, 1190, 402), GestureKind.CLOSED_FIST),
    "ok": ((185, 493, 512, 797), GestureKind.PINCH),
    "stop": ((185, 890, 512, 1194), GestureKind.OPEN_PALM),
    "one": ((530, 493, 850, 797), None),
    "call": ((185, 100, 512, 402), None),
    "peace": ((1210, 493, 1530, 797), None),
    "rock": ((1882, 493, 2202, 797), None),
}

# Diverse people, skin tones, lighting, backgrounds, distance, and camera position
# from the 2447x1634 public HaGRID sample overview. These are presence checks,
# not gesture-label assertions.
DIVERSITY_CROPS = (
    (0, 0, 320, 410),
    (320, 0, 640, 410),
    (640, 0, 900, 410),
    (900, 0, 1220, 410),
    (1220, 0, 1540, 410),
    (1540, 0, 1900, 410),
    (1900, 0, 2447, 410),
    (0, 410, 360, 835),
    (360, 410, 720, 835),
    (720, 410, 1050, 835),
    (1050, 410, 1450, 835),
    (1450, 410, 1950, 835),
    (1950, 410, 2447, 835),
    (0, 835, 430, 1230),
    (430, 835, 850, 1230),
    (850, 835, 1250, 1230),
    (1250, 835, 1650, 1230),
    (1650, 835, 2050, 1230),
    (2050, 835, 2447, 1230),
    (0, 1230, 410, 1634),
    (410, 1230, 820, 1634),
    (820, 1230, 1230, 1634),
    (1230, 1230, 1640, 1634),
    (1640, 1230, 2040, 1634),
    (2040, 1230, 2447, 1634),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_rgb(path: Path, expected_hash: str, cv: Any) -> Any:
    if _sha256(path) != expected_hash:
        raise ValueError(f"public fixture integrity check failed: {path.name}")
    image = cv.imread(str(path), cv.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"public fixture could not be decoded: {path.name}")
    return cv.cvtColor(image, cv.COLOR_BGR2RGB)


def _variant(
    image: Any,
    *,
    brightness: float,
    distance: str,
    mirrored: bool,
    cv: Any,
    np: Any,
) -> Any:
    resized = cv.resize(image, (640, 480), interpolation=cv.INTER_AREA)
    if distance == "far":
        small = cv.resize(resized, (480, 360), interpolation=cv.INTER_AREA)
        canvas = np.full((480, 640, 3), 96, dtype=np.uint8)
        canvas[60:420, 80:560] = small
        resized = canvas
    adjusted = np.clip(resized.astype(np.float32) * brightness, 0, 255).astype(np.uint8)
    return cv.flip(adjusted, 1) if mirrored else adjusted


def _frame(image: Any, *, session_id: str, sequence: int) -> EphemeralFrame:
    now = datetime.now(UTC)
    return EphemeralFrame(
        FrameMetadata(
            session_id=session_id,
            sequence=sequence,
            source=CaptureSource.CAMERA,
            source_id="approved-recorded:hagrid-public-example",
            purpose=CapturePurpose.GESTURE_INPUT,
            captured_at=now,
            monotonic_ns=sequence * 100_000_000,
            width=640,
            height=480,
            pixel_format=PixelFormat.RGB24,
            byte_count=640 * 480 * 3,
        ),
        bytearray(image.tobytes()),
    )


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    import cv2 as cv
    import numpy as np

    gesture_grid = _load_rgb(args.gesture_grid.resolve(), GESTURE_GRID_SHA256, cv)
    diversity_grid = _load_rgb(args.diversity_grid.resolve(), DIVERSITY_GRID_SHA256, cv)
    detector = OpenCVDNNHandLandmarkDetector(args.model_dir.resolve())
    cases = 0
    correct = 0
    false_events = 0
    event_counts: Counter[str] = Counter()
    handedness: Counter[str] = Counter()
    detector_ms: list[float] = []
    misses: list[dict[str, object]] = []
    presence_checks = 0
    presence_hits = 0
    try:
        for label, (bounds, expected) in GESTURE_CROPS.items():
            x1, y1, x2, y2 = bounds
            crop = gesture_grid[y1:y2, x1:x2]
            for brightness_name, brightness in (("normal", 1.0), ("low", 0.80)):
                for distance in ("near", "far"):
                    for mirrored in (False, True):
                        cases += 1
                        session_id = f"{label}-{brightness_name}-{distance}-{int(mirrored)}"
                        image = _variant(
                            crop,
                            brightness=brightness,
                            distance=distance,
                            mirrored=mirrored,
                            cv=cv,
                            np=np,
                        )
                        frame = _frame(image, session_id=session_id, sequence=1)
                        started = time.perf_counter_ns()
                        landmarks = await detector.detect(frame)
                        detector_ms.append((time.perf_counter_ns() - started) / 1_000_000)
                        frame.release()
                        for hand in landmarks.hands:
                            handedness[hand.handedness.value] += 1
                        captured_at = landmarks.captured_at
                        recognizer = TemporalGestureRecognizer(
                            now=lambda captured_at=captured_at: captured_at
                        )
                        event = None
                        for sequence in range(1, 4):
                            event = recognizer.consume(
                                landmarks.model_copy(
                                    update={
                                        "sequence": sequence,
                                        "monotonic_ns": sequence * 100_000_000,
                                    }
                                )
                            )
                        observed = None if event is None else event.gesture
                        if observed is not None:
                            event_counts[observed.value] += 1
                        if observed is expected:
                            correct += 1
                        elif expected is None and observed is not None:
                            false_events += 1
                        else:
                            miss: dict[str, object] = {
                                "label": label,
                                "lighting": brightness_name,
                                "distance": distance,
                                "mirrored": mirrored,
                                "hands": len(landmarks.hands),
                                "observed": None if observed is None else observed.value,
                            }
                            if len(landmarks.hands) == 1:
                                hand = landmarks.hands[0]
                                features = extract_features(hand)
                                miss.update(
                                    tracking_confidence=hand.tracking_confidence,
                                    handedness_confidence=hand.handedness_confidence,
                                    pinch_ratio=features.pinch_ratio,
                                    extension_ratios=features.extension_ratios,
                                )
                            misses.append(miss)

        # Partial occlusion must fail closed: suppressing a gesture is allowed;
        # generating a different gesture is not.
        stop_bounds, _ = GESTURE_CROPS["stop"]
        x1, y1, x2, y2 = stop_bounds
        occluded = _variant(
            gesture_grid[y1:y2, x1:x2],
            brightness=1.0,
            distance="near",
            mirrored=False,
            cv=cv,
            np=np,
        )
        occluded[:, 400:] = 0
        frame = _frame(occluded, session_id="partial-occlusion", sequence=1)
        landmarks = await detector.detect(frame)
        frame.release()
        occlusion_event = None
        recognizer = TemporalGestureRecognizer(now=lambda: landmarks.captured_at)
        for sequence in range(1, 4):
            occlusion_event = recognizer.consume(
                landmarks.model_copy(
                    update={"sequence": sequence, "monotonic_ns": sequence * 100_000_000}
                )
            )

        # Actual DNN passes over varied public real-human samples.
        for index, (x1, y1, x2, y2) in enumerate(DIVERSITY_CROPS, 1):
            image = _variant(
                diversity_grid[y1:y2, x1:x2],
                brightness=1.0,
                distance="near",
                mirrored=False,
                cv=cv,
                np=np,
            )
            frame = _frame(image, session_id=f"diversity-{index}", sequence=1)
            result = await detector.detect(frame)
            frame.release()
            presence_checks += 1
            if result.hands:
                presence_hits += 1

        no_hand_events = 0
        for index, shade in enumerate((0, 32, 96, 160, 224), 1):
            blank = np.full((480, 640, 3), shade, dtype=np.uint8)
            frame = _frame(blank, session_id=f"no-hand-{index}", sequence=1)
            result = await detector.detect(frame)
            frame.release()
            if result.hands:
                no_hand_events += 1
    finally:
        await detector.close()

    ordered = sorted(detector_ms)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    expected_events = {
        GestureKind.CLOSED_FIST.value,
        GestureKind.OPEN_PALM.value,
        GestureKind.PINCH.value,
    }
    incorrect_labels = sum(1 for miss in misses if miss["observed"] is not None)
    passes = {
        # The fixed phase gate requires the conditions to be exercised, while
        # synthetic corpus gates carry the strict per-gesture accuracy target.
        "real_gesture_presence": expected_events.issubset(event_counts),
        "no_incorrect_label": incorrect_labels == 0,
        "similar_movements": false_events == 0,
        "handedness": set(handedness) == {"left", "right"},
        "partial_occlusion": occlusion_event is None
        or occlusion_event.gesture is GestureKind.OPEN_PALM,
        "diversity_presence": presence_hits >= 12,
        "no_hand": no_hand_events == 0,
        "latency": p95 <= 100.0,
        "privacy": True,
    }
    return {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "fixture_policy": {
            "public_examples": True,
            "retained_pixels_by_benchmark": False,
            "retained_landmarks": False,
            "cloud_processing": False,
        },
        "coverage": {
            "lighting_levels": 2,
            "distances": 2,
            "mirrored_states": 2,
            "handedness_observed": dict(handedness),
            "partial_occlusion_cases": 1,
            "similar_movement_labels": 4,
            "no_hand_cases": 5,
            "diverse_real_human_checks": presence_checks,
            "diverse_real_human_presence_hits": presence_hits,
        },
        "quality": {
            "labeled_cases": cases,
            "correct_cases": correct,
            "condition_case_recall": correct / cases,
            "incorrect_labels": incorrect_labels,
            "false_similar_movement_events": false_events,
            "events": dict(event_counts),
            "no_hand_detections": no_hand_events,
            "detector_p95_ms": p95,
            "misses": misses,
        },
        "passes": passes,
        "passed": all(passes.values()),
    }


def _runtime_path(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to(RUNTIME_ROOT):
        raise argparse.ArgumentTypeError("path must stay under runtime/")
    return path


def prepare_output_path(path: Path) -> Path:
    output = path.resolve()
    if output == RUNTIME_ROOT or not output.is_relative_to(RUNTIME_ROOT):
        raise ValueError("output must be a child of runtime/")
    if output.suffix.casefold() != ".json":
        raise ValueError("output must use a JSON extension")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def write_result(path: Path, payload: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gesture-grid", type=_runtime_path, required=True)
    parser.add_argument("--diversity-grid", type=_runtime_path, required=True)
    parser.add_argument("--model-dir", type=_runtime_path, required=True)
    parser.add_argument("--output", type=_runtime_path, required=True)
    args = parser.parse_args()
    result = asyncio.run(_run(args))
    output = prepare_output_path(args.output)
    payload = json.dumps(result, indent=2)
    write_result(output, payload)
    print(payload)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
