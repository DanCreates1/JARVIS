"""Pinned private-runtime model acquisition for the local OpenCV hand detector."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

OPENCV_ZOO_REVISION = "47534e27c9851bb1128ccc0102f1145e27f23f98"
MODEL_MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class VisionModel:
    name: str
    filename: str
    url: str
    sha256: str


PALM_MODEL = VisionModel(
    name="OpenCV Zoo MP palm detector",
    filename="palm_detection_mediapipe_2023feb.onnx",
    url=(
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
        f"{OPENCV_ZOO_REVISION}/models/palm_detection_mediapipe/"
        "palm_detection_mediapipe_2023feb.onnx"
    ),
    sha256="78ff51c38496b7fc8b8ebdb6cc8c1abb02fa6c38427c6848254cdaba57fcce7c",
)

HAND_MODEL = VisionModel(
    name="OpenCV Zoo MP hand-pose estimator",
    filename="handpose_estimation_mediapipe_2023feb.onnx",
    url=(
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
        f"{OPENCV_ZOO_REVISION}/models/handpose_estimation_mediapipe/"
        "handpose_estimation_mediapipe_2023feb.onnx"
    ),
    sha256="db0898ae717b76b075d9bf563af315b29562e11f8df5027a1ef07b02bef6d81c",
)

VISION_MODELS = (PALM_MODEL, HAND_MODEL)


class VisionModelError(RuntimeError):
    """A content-free local model acquisition or integrity failure."""


def model_paths(model_dir: Path) -> tuple[Path, Path]:
    return model_dir / PALM_MODEL.filename, model_dir / HAND_MODEL.filename


def verify_model(path: Path, model: VisionModel) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return False
    return digest.hexdigest() == model.sha256


def install_vision_models(
    model_dir: Path,
    *,
    client: httpx.Client | None = None,
) -> tuple[Path, Path]:
    """Download pinned Apache-2.0 ONNX files; never download during detection."""
    model_dir.mkdir(parents=True, exist_ok=True)
    owned_client = client is None
    http = client or httpx.Client(timeout=httpx.Timeout(30.0), follow_redirects=False)
    try:
        for model in VISION_MODELS:
            destination = model_dir / model.filename
            if verify_model(destination, model):
                continue
            _download_one(http, model, destination)
        paths = model_paths(model_dir)
        if not all(
            verify_model(path, model) for path, model in zip(paths, VISION_MODELS, strict=True)
        ):
            raise VisionModelError("vision model integrity verification failed")
        return paths
    finally:
        if owned_client:
            http.close()


def _download_one(client: httpx.Client, model: VisionModel, destination: Path) -> None:
    temporary_name: str | None = None
    try:
        with client.stream("GET", model.url) as response:
            response.raise_for_status()
            declared = response.headers.get("content-length")
            if declared is not None and int(declared) > MODEL_MAX_BYTES:
                raise VisionModelError("vision model exceeds download size limit")
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{model.filename}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as handle:
                temporary_name = handle.name
                digest = hashlib.sha256()
                total = 0
                for chunk in response.iter_bytes(64 * 1024):
                    total += len(chunk)
                    if total > MODEL_MAX_BYTES:
                        raise VisionModelError("vision model exceeds download size limit")
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        if digest.hexdigest() != model.sha256:
            raise VisionModelError("vision model checksum mismatch")
        os.replace(temporary_name, destination)
        temporary_name = None
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise VisionModelError("vision model acquisition failed") from exc
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
