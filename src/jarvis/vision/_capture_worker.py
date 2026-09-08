"""Isolated native camera/screen worker; protocol data travels only over private pipes."""

from __future__ import annotations

import importlib
import json
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

from .models import CaptureRequest, CaptureSource, PixelFormat

_MAX_COMMAND_BYTES = 64 * 1_024


class _WorkerSource:
    def __init__(self, request: CaptureRequest) -> None:
        self.request = request
        self._camera: Any | None = None
        self._cv2: ModuleType | None = None
        self._image_grab: ModuleType | None = None

    def open(self) -> None:
        if self.request.source is CaptureSource.CAMERA:
            try:
                self._cv2 = importlib.import_module("cv2")
            except ImportError as exc:
                raise RuntimeError("dependency_unavailable") from exc
            index = int(self.request.source_id.removeprefix("camera:"))
            backend = getattr(self._cv2, "CAP_DSHOW", 0)
            try:
                camera = self._cv2.VideoCapture(index, backend)
                camera.set(
                    self._cv2.CAP_PROP_FRAME_WIDTH,
                    self.request.region.x + self.request.region.width,
                )
                camera.set(
                    self._cv2.CAP_PROP_FRAME_HEIGHT,
                    self.request.region.y + self.request.region.height,
                )
                camera.set(self._cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception as exc:
                raise RuntimeError("source_unavailable") from exc
            if not bool(camera.isOpened()):
                camera.release()
                raise RuntimeError("source_unavailable")
            self._camera = camera
            return
        try:
            self._image_grab = importlib.import_module("PIL.ImageGrab")
        except ImportError as exc:
            raise RuntimeError("dependency_unavailable") from exc

    def capture(self) -> tuple[bytes, datetime, int]:
        if self.request.source is CaptureSource.CAMERA:
            if self._camera is None or self._cv2 is None:
                raise RuntimeError("source_lost")
            try:
                ok, image = self._camera.read()
            except Exception as exc:
                raise RuntimeError("source_lost") from exc
            if not ok or image is None:
                raise RuntimeError("source_lost")
            region = self.request.region
            if (
                int(image.shape[1]) < region.x + region.width
                or int(image.shape[0]) < region.y + region.height
            ):
                raise RuntimeError("malformed_frame")
            cropped = image[
                region.y : region.y + region.height,
                region.x : region.x + region.width,
            ]
            try:
                rgb = self._cv2.cvtColor(cropped, self._cv2.COLOR_BGR2RGB)
                pixels = bytes(rgb.tobytes())
            except Exception as exc:
                raise RuntimeError("malformed_frame") from exc
        else:
            if self._image_grab is None:
                raise RuntimeError("source_lost")
            region = self.request.region
            try:
                image = self._image_grab.grab(
                    bbox=(
                        region.x,
                        region.y,
                        region.x + region.width,
                        region.y + region.height,
                    ),
                    include_layered_windows=False,
                    all_screens=True,
                ).convert("RGB")
                if image.size != (region.width, region.height):
                    raise RuntimeError("malformed_frame")
                pixels = image.tobytes()
                image.close()
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError("source_lost") from exc
        return pixels, datetime.now(UTC), time.monotonic_ns()

    def close(self) -> None:
        camera = self._camera
        self._camera = None
        if camera is not None:
            camera.release()


def _write_header(payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _read_command() -> dict[str, Any] | None:
    raw = sys.stdin.buffer.readline(_MAX_COMMAND_BYTES + 1)
    if not raw:
        return None
    if len(raw) > _MAX_COMMAND_BYTES or not raw.endswith(b"\n"):
        raise RuntimeError("invalid_protocol")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("invalid_protocol")
    return value


def main() -> int:
    source: _WorkerSource | None = None
    try:
        initial = _read_command()
        if initial is None or initial.get("op") != "open" or initial.get("protocol") != 1:
            raise RuntimeError("invalid_protocol")
        request = CaptureRequest.model_validate(initial.get("request"))
        source = _WorkerSource(request)
        source.open()
        _write_header({"type": "ready", "protocol": 1})
        while True:
            command = _read_command()
            if command is None or command.get("op") == "close":
                return 0
            if command.get("op") != "capture":
                raise RuntimeError("invalid_protocol")
            session_id = str(command.get("session_id", ""))
            sequence = int(command.get("sequence", 0))
            pixels, captured_at, monotonic_ns = source.capture()
            _write_header(
                {
                    "type": "frame",
                    "session_id": session_id,
                    "sequence": sequence,
                    "source": request.source.value,
                    "source_id": request.source_id,
                    "purpose": request.purpose.value,
                    "captured_at": captured_at.isoformat(),
                    "monotonic_ns": monotonic_ns,
                    "width": request.region.width,
                    "height": request.region.height,
                    "pixel_format": PixelFormat.RGB24.value,
                    "byte_count": len(pixels),
                }
            )
            sys.stdout.buffer.write(pixels)
            sys.stdout.buffer.flush()
    except Exception as exc:
        code = str(exc)
        if code not in {
            "dependency_unavailable",
            "source_unavailable",
            "source_lost",
            "malformed_frame",
            "invalid_protocol",
        }:
            code = "source_lost"
        with suppress(Exception):
            _write_header({"type": "error", "code": code})
        return 1
    finally:
        if source is not None:
            source.close()


if __name__ == "__main__":
    raise SystemExit(main())
