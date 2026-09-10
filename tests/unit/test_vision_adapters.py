from __future__ import annotations

import asyncio
import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from jarvis.vision import _capture_worker
from jarvis.vision.adapters import (
    IsolatedWindowsFrameSource,
    _sanitized_environment,
    _worker_import_roots,
)
from jarvis.vision.indicator import TerminalCaptureIndicator
from jarvis.vision.models import (
    CaptureError,
    CaptureFailureCode,
    CapturePurpose,
    CaptureRegion,
    CaptureRequest,
    CaptureSource,
    IndicatorState,
)


def _request(
    source: CaptureSource = CaptureSource.CAMERA,
    *,
    camera_exposure: int | None = None,
) -> CaptureRequest:
    return CaptureRequest(
        source=source,
        source_id="camera:0" if source is CaptureSource.CAMERA else "screen:desktop",
        purpose=(
            CapturePurpose.DIAGNOSTIC
            if source is CaptureSource.CAMERA
            else CapturePurpose.SCREEN_ANALYSIS
        ),
        region=CaptureRegion(x=0, y=0, width=2, height=2),
        camera_exposure=camera_exposure,
    )


class _FakeStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, output: bytes) -> None:
        self.stdin = _FakeStdin()
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(output)
        self.returncode: int | None = None
        self.killed = False

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def _line(value: dict[str, object]) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode() + b"\n"


@pytest.mark.asyncio
async def test_isolated_source_protocol_returns_ephemeral_frame(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    metadata = {
        "type": "frame",
        "session_id": "capture-1",
        "sequence": 1,
        "source": "camera",
        "source_id": "camera:0",
        "purpose": "diagnostic",
        "captured_at": datetime.now(UTC).isoformat(),
        "monotonic_ns": 1,
        "width": 2,
        "height": 2,
        "pixel_format": "rgb24",
        "byte_count": 12,
    }
    process = _FakeProcess(_line({"type": "ready", "protocol": 1}) + _line(metadata) + b"x" * 12)
    call: dict[str, object] = {}

    async def create(*args, **kwargs):  # type: ignore[no-untyped-def]
        call["args"] = args
        call["kwargs"] = kwargs
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    source = IsolatedWindowsFrameSource(
        environment={
            "PATH": "safe-path",
            "JARVIS_NVIDIA_API_KEY": "secret",
            "OTHER_TOKEN": "secret",
        }
    )

    await source.open(_request())
    frame = await source.capture(session_id="capture-1", sequence=1)
    await source.close()

    assert bytes(frame.pixels) == b"x" * 12
    assert frame.metadata.byte_count == 12
    sent_open = json.loads(process.stdin.writes[0])
    assert sent_open["request"]["retention"] == "ephemeral"
    assert sent_open["request"]["cloud_allowed"] is False
    child_env = call["kwargs"]["env"]  # type: ignore[index]
    assert child_env["PATH"] == "safe-path"
    assert "JARVIS_NVIDIA_API_KEY" not in child_env
    assert "OTHER_TOKEN" not in child_env
    assert call["args"][1:3] == ("-I", "-c")  # type: ignore[index]
    worker_roots = json.loads(call["args"][4])  # type: ignore[index]
    assert worker_roots == _worker_import_roots()


@pytest.mark.asyncio
async def test_isolated_source_maps_worker_error_and_malformed_header(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    dependency_process = _FakeProcess(_line({"type": "error", "code": "dependency_unavailable"}))

    async def dependency_create(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return dependency_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", dependency_create)
    with pytest.raises(CaptureError) as captured:
        await IsolatedWindowsFrameSource().open(_request())
    assert captured.value.code is CaptureFailureCode.DEPENDENCY_UNAVAILABLE
    assert dependency_process.killed

    malformed_process = _FakeProcess(_line({"type": "ready", "protocol": 1}) + b"not-json\n")

    async def malformed_create(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return malformed_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", malformed_create)
    source = IsolatedWindowsFrameSource()
    await source.open(_request())
    with pytest.raises(CaptureError) as captured:
        await source.capture(session_id="capture-1", sequence=1)
    assert captured.value.code is CaptureFailureCode.MALFORMED_FRAME
    await source.close()


def test_worker_screen_adapter_uses_exact_region_and_rgb(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict[str, object]] = []

    class Image:
        size = (2, 2)

        def convert(self, mode):  # type: ignore[no-untyped-def]
            assert mode == "RGB"
            return self

        def tobytes(self) -> bytes:
            return bytes(range(12))

        def close(self) -> None:
            return None

    class ImageGrab:
        @staticmethod
        def grab(**kwargs):  # type: ignore[no-untyped-def]
            calls.append(kwargs)
            return Image()

    monkeypatch.setattr(_capture_worker.importlib, "import_module", lambda _name: ImageGrab)
    source = _capture_worker._WorkerSource(_request(CaptureSource.SCREEN))

    source.open()
    pixels, captured_at, monotonic_ns = source.capture()
    source.close()

    assert pixels == bytes(range(12))
    assert captured_at.tzinfo is not None
    assert monotonic_ns > 0
    assert calls == [
        {
            "bbox": (0, 0, 2, 2),
            "include_layered_windows": False,
            "all_screens": True,
        }
    ]


def test_worker_camera_adapter_crops_and_converts(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class Matrix:
        shape = (2, 2, 3)

        def __getitem__(self, _key):  # type: ignore[no-untyped-def]
            return self

        def tobytes(self) -> bytes:
            return b"r" * 12

    class Camera:
        def __init__(self) -> None:
            self.settings: list[tuple[int, int]] = []
            self.released = False

        def set(self, name: int, value: int) -> None:
            self.settings.append((name, value))

        def isOpened(self) -> bool:
            return True

        def read(self):  # type: ignore[no-untyped-def]
            return True, Matrix()

        def release(self) -> None:
            self.released = True

    camera = Camera()

    class CV2:
        CAP_DSHOW = 1
        CAP_PROP_FRAME_WIDTH = 2
        CAP_PROP_FRAME_HEIGHT = 3
        CAP_PROP_BUFFERSIZE = 4
        CAP_PROP_FPS = 5
        COLOR_BGR2RGB = 6
        CAP_PROP_FOURCC = 7
        CAP_PROP_AUTO_EXPOSURE = 9
        CAP_PROP_EXPOSURE = 10

        @staticmethod
        def VideoCapture(index: int, backend: int) -> Camera:
            assert (index, backend) == (0, 1)
            return camera

        @staticmethod
        def VideoWriter_fourcc(*letters: str) -> int:
            assert letters == ("M", "J", "P", "G")
            return 8

        @staticmethod
        def cvtColor(image, conversion):  # type: ignore[no-untyped-def]
            assert conversion == 6
            return image

    monkeypatch.setattr(_capture_worker.importlib, "import_module", lambda _name: CV2)
    source = _capture_worker._WorkerSource(_request(camera_exposure=-4))

    source.open()
    pixels, _, _ = source.capture()
    source.close()

    assert pixels == b"r" * 12
    assert camera.released
    assert camera.settings == [
        (7, 8),
        (2, 2),
        (3, 2),
        (5, 30.0),
        (9, 0.25),
        (10, -4),
        (4, 1),
    ]


def test_sanitized_environment_is_allowlist_not_name_filter() -> None:
    safe = _sanitized_environment(
        {
            "PATH": "path",
            "TEMP": "temp",
            "HARMLESS": "drop",
            "API_KEY": "drop",
            "PASSWORD": "drop",
        }
    )

    assert safe == {
        "PATH": "path",
        "TEMP": "temp",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }


@pytest.mark.asyncio
async def test_terminal_indicator_is_visible_and_session_bound() -> None:
    output: list[str] = []
    indicator = TerminalCaptureIndicator(output.append)
    state = IndicatorState(
        session_id="capture-1",
        source=CaptureSource.CAMERA,
        source_id="camera:0",
        purpose=CapturePurpose.DIAGNOSTIC,
        region=CaptureRegion(x=1, y=2, width=2, height=2),
        requested_fps=10,
        max_frames=1,
    )

    await indicator.show(state)
    with pytest.raises(RuntimeError, match="already active"):
        await indicator.show(state)
    with pytest.raises(RuntimeError, match="session mismatch"):
        await indicator.clear("capture-other")
    await indicator.clear("capture-1")

    assert output == [
        "[JARVIS CAPTURE ACTIVE] source=camera purpose=diagnostic region=1,2,2x2",
        "[JARVIS CAPTURE OFF]",
    ]


def test_worker_protocol_helpers_reject_invalid_input_and_write_header(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        _capture_worker.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(b"[]\n")),
    )
    with pytest.raises(RuntimeError, match="invalid_protocol"):
        _capture_worker._read_command()

    output = io.BytesIO()
    monkeypatch.setattr(_capture_worker.sys, "stdout", SimpleNamespace(buffer=output))
    _capture_worker._write_header({"type": "ready", "protocol": 1})
    assert json.loads(output.getvalue()) == {"type": "ready", "protocol": 1}


def test_worker_main_runs_bounded_protocol_and_closes_source(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    commands = iter(
        [
            {"op": "open", "protocol": 1, "request": request.model_dump(mode="json")},
            {"op": "capture", "session_id": "capture-1", "sequence": 1},
            {"op": "close"},
        ]
    )
    headers: list[dict[str, object]] = []
    output = io.BytesIO()
    closed: list[bool] = []

    class Source:
        def __init__(self, received: CaptureRequest) -> None:
            assert received == request

        def open(self) -> None:
            return None

        def capture(self) -> tuple[bytes, datetime, int]:
            return b"x" * 12, datetime.now(UTC), 123

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(_capture_worker, "_read_command", lambda: next(commands))
    monkeypatch.setattr(_capture_worker, "_write_header", headers.append)
    monkeypatch.setattr(_capture_worker, "_WorkerSource", Source)
    monkeypatch.setattr(_capture_worker.sys, "stdout", SimpleNamespace(buffer=output))

    assert _capture_worker.main() == 0
    assert headers[0] == {"type": "ready", "protocol": 1}
    assert headers[1]["type"] == "frame"
    assert headers[1]["session_id"] == "capture-1"
    assert headers[1]["byte_count"] == 12
    assert output.getvalue() == b"x" * 12
    assert closed == [True]


def test_worker_main_maps_unknown_failure_and_closes_source(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    commands = iter(
        [
            {"op": "open", "protocol": 1, "request": request.model_dump(mode="json")},
            {"op": "capture", "session_id": "capture-1", "sequence": 1},
        ]
    )
    headers: list[dict[str, object]] = []
    closed: list[bool] = []

    class Source:
        def __init__(self, _received: CaptureRequest) -> None:
            return None

        def open(self) -> None:
            return None

        def capture(self) -> tuple[bytes, datetime, int]:
            raise ValueError("private detail")

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(_capture_worker, "_read_command", lambda: next(commands))
    monkeypatch.setattr(_capture_worker, "_write_header", headers.append)
    monkeypatch.setattr(_capture_worker, "_WorkerSource", Source)

    assert _capture_worker.main() == 1
    assert headers[-1] == {"type": "error", "code": "source_lost"}
    assert closed == [True]
