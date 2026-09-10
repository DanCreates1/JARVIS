"""Local OpenCV DNN hand-landmark adapter with no MediaPipe Tasks runtime."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any

from jarvis.vision.models import CapturePurpose, EphemeralFrame

from .model_store import HAND_MODEL, PALM_MODEL, model_paths, verify_model
from .models import (
    Handedness,
    HandObservation,
    LandmarkError,
    LandmarkFailureCode,
    LandmarkFrame,
    NormalizedLandmark,
)

PALM_INPUT_SIZE = 192
HAND_INPUT_SIZE = 224
MAX_DETECTED_HANDS = 2


class OpenCVDNNHandLandmarkDetector:
    """Infer 21 local landmarks from an owning ephemeral RGB24 frame."""

    def __init__(
        self,
        model_dir: Path,
        *,
        palm_score_threshold: float = 0.5,
        landmark_score_threshold: float = 0.8,
        nms_iou_threshold: float = 0.3,
    ) -> None:
        if not 0.5 <= palm_score_threshold <= 1:
            raise ValueError("palm score threshold must be from 0.5 through 1")
        if not 0.5 <= landmark_score_threshold <= 1:
            raise ValueError("landmark score threshold must be from 0.5 through 1")
        if not 0 < nms_iou_threshold < 1:
            raise ValueError("NMS threshold must be between 0 and 1")
        palm_path, hand_path = model_paths(model_dir)
        if not verify_model(palm_path, PALM_MODEL) or not verify_model(hand_path, HAND_MODEL):
            raise LandmarkError(
                LandmarkFailureCode.MODEL_UNAVAILABLE,
                "local vision models are missing or fail integrity verification",
            )
        try:
            import cv2 as cv
            import numpy as np
        except ImportError as exc:
            raise LandmarkError(
                LandmarkFailureCode.DEPENDENCY_UNAVAILABLE,
                "OpenCV vision dependency is unavailable",
            ) from exc
        try:
            self._palm_net: Any = cv.dnn.readNet(str(palm_path))
            self._hand_net: Any = cv.dnn.readNet(str(hand_path))
            self._palm_output_names = self._palm_net.getUnconnectedOutLayersNames()
            self._hand_output_names = self._hand_net.getUnconnectedOutLayersNames()
        except Exception as exc:
            raise LandmarkError(
                LandmarkFailureCode.MODEL_INVALID,
                "local vision model could not be initialized",
            ) from exc
        self._cv = cv
        self._np = np
        self._anchors = _generate_palm_anchors(np)
        self._palm_score_threshold = palm_score_threshold
        self._landmark_score_threshold = landmark_score_threshold
        self._nms_iou_threshold = nms_iou_threshold
        self._lock = asyncio.Lock()
        self._closed = False

    async def detect(self, frame: EphemeralFrame) -> LandmarkFrame:
        if not isinstance(frame, EphemeralFrame):
            raise TypeError("detector requires an EphemeralFrame")
        if self._closed:
            raise LandmarkError(LandmarkFailureCode.CANCELLED, "landmark detector is closed")
        if frame.released:
            raise LandmarkError(
                LandmarkFailureCode.MALFORMED_RESULT,
                "owning capture frame has already been released",
            )
        if frame.metadata.purpose not in {
            CapturePurpose.GESTURE_INPUT,
            CapturePurpose.GESTURE_CALIBRATION,
        }:
            raise LandmarkError(
                LandmarkFailureCode.MALFORMED_RESULT,
                "capture purpose does not permit landmark processing",
            )
        async with self._lock:
            if self._closed:
                raise LandmarkError(LandmarkFailureCode.CANCELLED, "landmark detector is closed")
            try:
                hands = await asyncio.to_thread(self._infer, frame)
            except LandmarkError:
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise LandmarkError(
                    LandmarkFailureCode.MALFORMED_RESULT,
                    "local landmark inference failed",
                ) from exc
        metadata = frame.metadata
        return LandmarkFrame(
            session_id=metadata.session_id,
            sequence=metadata.sequence,
            captured_at=metadata.captured_at,
            monotonic_ns=metadata.monotonic_ns,
            hands=tuple(hands),
        )

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            self._palm_net = None
            self._hand_net = None

    def _infer(self, frame: EphemeralFrame) -> list[HandObservation]:
        np = self._np
        metadata = frame.metadata
        image = np.frombuffer(frame.pixels, dtype=np.uint8).reshape(
            metadata.height,
            metadata.width,
            3,
        )
        palms = self._infer_palms(image)
        hands: list[HandObservation] = []
        for palm in palms[:MAX_DETECTED_HANDS]:
            hand = self._infer_hand(image, palm)
            if hand is not None:
                hands.append(hand)
        return hands

    def _infer_palms(self, image: Any) -> list[Any]:
        cv = self._cv
        np = self._np
        height, width = image.shape[:2]
        scale = min(PALM_INPUT_SIZE / width, PALM_INPUT_SIZE / height)
        resized_width = max(1, round(width * scale))
        resized_height = max(1, round(height * scale))
        resized = cv.resize(image, (resized_width, resized_height), interpolation=cv.INTER_AREA)
        left = (PALM_INPUT_SIZE - resized_width) // 2
        top = (PALM_INPUT_SIZE - resized_height) // 2
        canvas = np.zeros((PALM_INPUT_SIZE, PALM_INPUT_SIZE, 3), dtype=np.uint8)
        canvas[top : top + resized_height, left : left + resized_width] = resized
        blob = canvas.astype(np.float32) / 255.0
        self._palm_net.setInput(blob[np.newaxis, ...])
        outputs = self._palm_net.forward(self._palm_output_names)
        if len(outputs) != 2 or outputs[0].shape != (1, 2016, 18):
            raise LandmarkError(
                LandmarkFailureCode.MODEL_INVALID,
                "palm model returned an unexpected output shape",
            )
        raw = outputs[0][0]
        logits = np.clip(outputs[1][0, :, 0].astype(np.float64), -80, 80)
        scores = 1.0 / (1.0 + np.exp(-logits))
        selected = np.flatnonzero(scores >= self._palm_score_threshold)
        candidates: list[Any] = []
        for index in selected.tolist():
            anchor = self._anchors[index]
            center = (raw[index, 0:2] / PALM_INPUT_SIZE + anchor) * PALM_INPUT_SIZE
            size = raw[index, 2:4] / PALM_INPUT_SIZE * PALM_INPUT_SIZE
            xy1 = (center - size / 2 - (left, top)) / scale
            xy2 = (center + size / 2 - (left, top)) / scale
            landmarks = raw[index, 4:].reshape(7, 2)
            landmarks = (
                (landmarks / PALM_INPUT_SIZE + anchor) * PALM_INPUT_SIZE - (left, top)
            ) / scale
            box = np.concatenate((xy1, xy2))
            if not np.all(np.isfinite(box)) or box[2] <= box[0] or box[3] <= box[1]:
                continue
            candidates.append((float(scores[index]), box, landmarks))
        return _nms(candidates, self._nms_iou_threshold, MAX_DETECTED_HANDS)

    def _infer_hand(self, image: Any, palm: Any) -> HandObservation | None:
        cv = self._cv
        np = self._np
        _palm_score, _box, palm_landmarks = palm
        wrist = palm_landmarks[0]
        middle_base = palm_landmarks[2]
        radians = math.pi / 2 - math.atan2(
            -(middle_base[1] - wrist[1]),
            middle_base[0] - wrist[0],
        )
        radians -= 2 * math.pi * math.floor((radians + math.pi) / (2 * math.pi))
        angle = math.degrees(radians)
        center = (np.min(palm_landmarks, axis=0) + np.max(palm_landmarks, axis=0)) / 2
        rotation = cv.getRotationMatrix2D(tuple(center), angle, 1.0)
        height, width = image.shape[:2]
        rotated = cv.warpAffine(image, rotation, (width, height), flags=cv.INTER_LINEAR)
        homogeneous = np.c_[palm_landmarks, np.ones(len(palm_landmarks))]
        rotated_points = homogeneous @ rotation.T
        palm_min = np.min(rotated_points, axis=0)
        palm_max = np.max(rotated_points, axis=0)
        palm_size = palm_max - palm_min
        crop_center = (palm_min + palm_max) / 2 + np.array((0.0, -0.4)) * palm_size
        side = float(max(palm_size) * 3.0)
        if not math.isfinite(side) or side < 2 or side > max(width, height) * 6:
            return None
        crop, origin = _square_crop(rotated, crop_center, side, cv, np)
        if crop.size == 0:
            return None
        blob = cv.resize(crop, (HAND_INPUT_SIZE, HAND_INPUT_SIZE), interpolation=cv.INTER_AREA)
        blob = blob.astype(np.float32) / 255.0
        self._hand_net.setInput(blob[np.newaxis, ...])
        outputs = self._hand_net.forward(self._hand_output_names)
        if len(outputs) != 4 or outputs[0].shape != (1, 63):
            raise LandmarkError(
                LandmarkFailureCode.MODEL_INVALID,
                "hand model returned an unexpected output shape",
            )
        presence = float(outputs[1][0, 0])
        handedness_score = float(outputs[2][0, 0])
        if not math.isfinite(presence) or presence < self._landmark_score_threshold:
            return None
        if not math.isfinite(handedness_score) or not 0 <= handedness_score <= 1:
            return None
        raw_landmarks = outputs[0][0].reshape(21, 3).astype(np.float64)
        if not np.all(np.isfinite(raw_landmarks)):
            return None
        rotated_xy = raw_landmarks[:, :2] * (side / HAND_INPUT_SIZE) + origin
        inverse = cv.invertAffineTransform(rotation)
        image_xy = np.c_[rotated_xy, np.ones(21)] @ inverse.T
        normalized: list[NormalizedLandmark] = []
        for point, raw_point in zip(image_xy, raw_landmarks, strict=True):
            x = float(point[0] / width)
            y = float(point[1] / height)
            z = float(raw_point[2] * (side / HAND_INPUT_SIZE) / max(width, height))
            if not (-0.5 <= x <= 1.5 and -0.5 <= y <= 1.5 and -2 <= z <= 2):
                return None
            normalized.append(
                NormalizedLandmark(
                    x=min(1.0, max(0.0, x)),
                    y=min(1.0, max(0.0, y)),
                    z=z,
                )
            )
        handedness = Handedness.RIGHT if handedness_score >= 0.5 else Handedness.LEFT
        handedness_confidence = max(handedness_score, 1.0 - handedness_score)
        tracking_confidence = min(1.0, max(0.0, presence))
        return HandObservation(
            handedness=handedness,
            handedness_confidence=handedness_confidence,
            tracking_confidence=tracking_confidence,
            landmarks=tuple(normalized),
        )


def _generate_palm_anchors(np: Any) -> Any:
    anchors = [
        ((column + 0.5) / 24, (row + 0.5) / 24)
        for row in range(24)
        for column in range(24)
        for _ in range(2)
    ]
    anchors.extend(
        ((column + 0.5) / 12, (row + 0.5) / 12)
        for row in range(12)
        for column in range(12)
        for _ in range(6)
    )
    return np.asarray(anchors, dtype=np.float32)


def _nms(candidates: list[Any], threshold: float, limit: int) -> list[Any]:
    ordered = sorted(candidates, key=lambda item: item[0], reverse=True)
    kept: list[Any] = []
    for candidate in ordered:
        if all(_box_iou(candidate[1], prior[1]) <= threshold for prior in kept):
            kept.append(candidate)
            if len(kept) >= limit:
                break
    return kept


def _box_iou(left: Any, right: Any) -> float:
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return 0.0 if union <= 0 else intersection / union


def _square_crop(image: Any, center: Any, side: float, cv: Any, np: Any) -> tuple[Any, Any]:
    size = max(2, math.ceil(side))
    left = math.floor(float(center[0]) - size / 2)
    top = math.floor(float(center[1]) - size / 2)
    right = left + size
    bottom = top + size
    image_height, image_width = image.shape[:2]
    pad_left = max(0, -left)
    pad_top = max(0, -top)
    pad_right = max(0, right - image_width)
    pad_bottom = max(0, bottom - image_height)
    padded = cv.copyMakeBorder(
        image,
        pad_top,
        pad_bottom,
        pad_left,
        pad_right,
        cv.BORDER_CONSTANT,
        value=(0, 0, 0),
    )
    crop = padded[
        top + pad_top : bottom + pad_top,
        left + pad_left : right + pad_left,
    ]
    return crop, np.array((left, top), dtype=np.float64)
