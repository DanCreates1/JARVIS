from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from jarvis.voice.audio_io import AudioDeviceError, SoundDeviceAudio
from jarvis.voice.models import AudioChunk, AudioDeviceDirection, AudioOutputKind, CaptureRequest


class FakeInputStream:
    def __init__(
        self, *, callback: Callable[..., None], data: bytes | None, **_kwargs: object
    ) -> None:
        self.callback = callback
        self.data = data
        self.stopped = False
        self.aborted = False
        self.closed = False

    def start(self) -> None:
        if self.data is not None:
            self.callback(
                self.data,
                len(self.data) // 2,
                {},
                SimpleNamespace(input_overflow=False),
            )

    def stop(self) -> None:
        self.stopped = True

    def abort(self) -> None:
        self.aborted = True

    def close(self) -> None:
        self.closed = True


class FakeOutputStream:
    def __init__(self, *, fail_write: bool = False, **_kwargs: object) -> None:
        self.fail_write = fail_write
        self.writes: list[bytes] = []
        self.aborted = False
        self.closed = False

    def start(self) -> None:
        return None

    def write(self, data: bytes) -> None:
        if self.fail_write:
            raise RuntimeError("driver")
        self.writes.append(data)

    def stop(self) -> None:
        return None

    def abort(self) -> None:
        self.aborted = True

    def close(self) -> None:
        self.closed = True


class FakeSoundDevice:
    def __init__(
        self, *, input_data: bytes | None = b"\0\0" * 512, fail_write: bool = False
    ) -> None:
        self.input_data = input_data
        self.fail_write = fail_write
        self.default = SimpleNamespace(device=(0, 1))
        self.input_streams: list[FakeInputStream] = []
        self.output_streams: list[FakeOutputStream] = []

    def query_devices(self) -> list[dict[str, object]]:
        return [
            {
                "name": "Mic",
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
                "default_samplerate": 48_000,
            },
            {
                "name": "Speakers",
                "hostapi": 0,
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_samplerate": 48_000,
            },
        ]

    def query_hostapis(self) -> list[dict[str, object]]:
        return [{"name": "Windows WASAPI"}]

    def check_input_settings(self, **_kwargs: object) -> None:
        return None

    def RawInputStream(self, **kwargs: object) -> FakeInputStream:
        stream = FakeInputStream(data=self.input_data, **kwargs)
        self.input_streams.append(stream)
        return stream

    def RawOutputStream(self, **kwargs: object) -> FakeOutputStream:
        stream = FakeOutputStream(fail_write=self.fail_write, **kwargs)
        self.output_streams.append(stream)
        return stream


@pytest.mark.asyncio
async def test_sounddevice_inventory_uses_stable_directional_ids() -> None:
    adapter = SoundDeviceAudio(FakeSoundDevice())
    devices = await adapter.list_devices()
    assert [item.direction for item in devices] == [
        AudioDeviceDirection.INPUT,
        AudioDeviceDirection.OUTPUT,
    ]
    assert all(item.is_default for item in devices)
    assert devices[0].id != devices[1].id


@pytest.mark.asyncio
async def test_sounddevice_capture_is_bounded_and_reports_missing_device() -> None:
    module = FakeSoundDevice(input_data=b"\1\0" * 512)
    adapter = SoundDeviceAudio(module)
    request = CaptureRequest(max_duration_ms=100)
    clip = await adapter.capture(
        session_id="voice-test",
        request=request,
        stop=asyncio.Event(),
    )
    assert clip.sample_count == 512
    assert module.input_streams[0].aborted
    assert module.input_streams[0].closed
    with pytest.raises(AudioDeviceError, match="unavailable"):
        await adapter.check_input_settings(request.model_copy(update={"device_id": "missing"}))


@pytest.mark.asyncio
async def test_sounddevice_capture_with_no_frames_fails_clearly() -> None:
    adapter = SoundDeviceAudio(FakeSoundDevice(input_data=None))
    with pytest.raises(AudioDeviceError, match="no audio"):
        await adapter.capture(
            session_id="voice-test",
            request=CaptureRequest(max_duration_ms=100),
            stop=asyncio.Event(),
        )


@pytest.mark.asyncio
async def test_sounddevice_output_finishes_stops_and_normalizes_driver_failure() -> None:
    chunk = AudioChunk(
        session_id="voice-test",
        sequence=1,
        sample_rate_hz=16_000,
        pcm_s16le=b"\0\0" * 2_000,
        phrase="hello",
    )
    module = FakeSoundDevice()
    adapter = SoundDeviceAudio(module)
    events = await adapter.play(chunk, device_id=None, cancel=asyncio.Event())
    assert [event.kind for event in events] == [AudioOutputKind.STARTED, AudioOutputKind.FINISHED]
    assert module.output_streams[0].writes

    cancelled = asyncio.Event()
    cancelled.set()
    events = await adapter.play(chunk, device_id=None, cancel=cancelled)
    assert events[-1].kind is AudioOutputKind.STOPPED

    failed = SoundDeviceAudio(FakeSoundDevice(fail_write=True))
    events = await failed.play(chunk, device_id=None, cancel=asyncio.Event())
    assert events[0].kind is AudioOutputKind.FAILED
