"""Windows-capable PortAudio adapters with stable device identities."""

from __future__ import annotations

import asyncio
import importlib
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from .models import (
    MAX_AUDIO_BYTES,
    AudioChunk,
    AudioClip,
    AudioDevice,
    AudioDeviceDirection,
    AudioFrame,
    AudioOutputEvent,
    AudioOutputKind,
    CaptureRequest,
)
from .signal import stable_device_id


class AudioDependencyError(RuntimeError):
    """Optional local audio dependency is unavailable."""


class AudioDeviceError(RuntimeError):
    """Configured endpoint is unavailable or cannot be opened."""


class SoundDeviceAudio:
    """Capture and render signed 16-bit PCM through python-sounddevice."""

    def __init__(self, sounddevice_module: Any | None = None) -> None:
        self._sd = sounddevice_module
        self._active_output: Any | None = None
        self._stop_output = asyncio.Event()

    def _module(self) -> Any:
        if self._sd is None:
            try:
                self._sd = importlib.import_module("sounddevice")
            except ImportError as exc:
                raise AudioDependencyError(
                    "python-sounddevice is not installed; install the voice extra"
                ) from exc
        return self._sd

    async def list_devices(self) -> Sequence[AudioDevice]:
        return await asyncio.to_thread(self._list_devices_sync)

    def _list_devices_sync(self) -> tuple[AudioDevice, ...]:
        sd = self._module()
        try:
            raw_devices = sd.query_devices()
            host_apis = sd.query_hostapis()
            default_pair = tuple(sd.default.device)
        except Exception as exc:
            raise AudioDeviceError("audio device enumeration failed") from exc
        devices: list[AudioDevice] = []
        for index, raw in enumerate(raw_devices):
            host_index = int(raw["hostapi"])
            host_name = str(host_apis[host_index]["name"])
            name = str(raw["name"])
            sample_rate = round(float(raw["default_samplerate"]))
            for direction, channel_key, default_index in (
                (AudioDeviceDirection.INPUT, "max_input_channels", default_pair[0]),
                (AudioDeviceDirection.OUTPUT, "max_output_channels", default_pair[1]),
            ):
                channels = int(raw[channel_key])
                if channels < 1:
                    continue
                devices.append(
                    AudioDevice(
                        id=stable_device_id(
                            host_api=host_name,
                            name=name,
                            direction=direction,
                            max_channels=channels,
                            default_sample_rate_hz=sample_rate,
                        ),
                        name=name,
                        direction=direction,
                        host_api=host_name,
                        backend_index=index,
                        max_channels=channels,
                        default_sample_rate_hz=sample_rate,
                        is_default=index == default_index,
                    )
                )
        return tuple(devices)

    async def _resolve_index(
        self,
        device_id: str | None,
        direction: AudioDeviceDirection,
    ) -> int | None:
        if device_id is None:
            return None
        devices = await self.list_devices()
        matches = [
            device for device in devices if device.id == device_id and device.direction is direction
        ]
        if len(matches) != 1:
            raise AudioDeviceError(f"selected {direction.value} audio device is unavailable")
        return matches[0].backend_index

    async def check_input_settings(self, request: CaptureRequest) -> None:
        sd = self._module()
        device_index = await self._resolve_index(request.device_id, AudioDeviceDirection.INPUT)
        try:
            await asyncio.to_thread(
                sd.check_input_settings,
                device=device_index,
                channels=request.channels,
                dtype="int16",
                samplerate=request.sample_rate_hz,
            )
        except Exception as exc:
            raise AudioDeviceError(
                "selected microphone does not support the voice audio format"
            ) from exc

    def stream(
        self,
        *,
        session_id: str,
        request: CaptureRequest,
        stop: asyncio.Event,
    ) -> AsyncIterator[AudioFrame]:
        return self._stream(session_id=session_id, request=request, stop=stop)

    async def _stream(
        self,
        *,
        session_id: str,
        request: CaptureRequest,
        stop: asyncio.Event,
    ) -> AsyncIterator[AudioFrame]:
        sd = self._module()
        device_index = await self._resolve_index(request.device_id, AudioDeviceDirection.INPUT)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[bytes, bool]] = asyncio.Queue(maxsize=32)
        dropped = 0

        def enqueue(data: bytes, overflowed: bool) -> None:
            nonlocal dropped
            if queue.full():
                dropped += 1
                return
            queue.put_nowait((data, overflowed or dropped > 0))
            dropped = 0

        def callback(
            indata: Any,
            _frames: int,
            _time_info: Mapping[str, float],
            status: object,
        ) -> None:
            overflowed = bool(getattr(status, "input_overflow", False))
            loop.call_soon_threadsafe(enqueue, bytes(indata), overflowed)

        try:
            stream = sd.RawInputStream(
                samplerate=request.sample_rate_hz,
                blocksize=request.frame_samples,
                device=device_index,
                channels=request.channels,
                dtype="int16",
                callback=callback,
            )
            stream.start()
        except Exception as exc:
            raise AudioDeviceError("microphone could not be opened") from exc
        started = time.monotonic_ns()
        deadline = started + (request.max_duration_ms * 1_000_000)
        sequence = 0
        try:
            while not stop.is_set() and time.monotonic_ns() < deadline:
                remaining = max(0.001, (deadline - time.monotonic_ns()) / 1_000_000_000)
                try:
                    data, overflowed = await asyncio.wait_for(queue.get(), min(0.1, remaining))
                except TimeoutError:
                    continue
                sequence += 1
                yield AudioFrame(
                    session_id=session_id,
                    sequence=sequence,
                    captured_at=datetime.now(UTC),
                    monotonic_ns=time.monotonic_ns(),
                    sample_rate_hz=request.sample_rate_hz,
                    channels=request.channels,
                    pcm_s16le=data,
                    overflowed=overflowed,
                )
        finally:
            try:
                await asyncio.to_thread(stream.abort)
            finally:
                await asyncio.to_thread(stream.close)

    async def capture(
        self,
        *,
        session_id: str,
        request: CaptureRequest,
        stop: asyncio.Event,
    ) -> AudioClip:
        captured_at = datetime.now(UTC)
        blocks: list[bytes] = []
        dropped_frames = 0
        size = 0
        async for frame in self.stream(session_id=session_id, request=request, stop=stop):
            if frame.overflowed:
                dropped_frames += 1
            size += len(frame.pcm_s16le)
            if size > MAX_AUDIO_BYTES:
                raise AudioDeviceError("captured audio exceeds size limit")
            blocks.append(frame.pcm_s16le)
        if not blocks:
            raise AudioDeviceError("microphone returned no audio")
        return AudioClip(
            session_id=session_id,
            captured_at=captured_at,
            sample_rate_hz=request.sample_rate_hz,
            channels=request.channels,
            pcm_s16le=b"".join(blocks),
            dropped_frames=dropped_frames,
        )

    async def play(
        self,
        chunk: AudioChunk,
        *,
        device_id: str | None,
        cancel: asyncio.Event,
    ) -> tuple[AudioOutputEvent, ...]:
        sd = self._module()
        device_index = await self._resolve_index(device_id, AudioDeviceDirection.OUTPUT)
        started_event = AudioOutputEvent(
            session_id=chunk.session_id,
            sequence=(chunk.sequence * 2) - 1,
            kind=AudioOutputKind.STARTED,
            phrase=chunk.phrase,
            sample_count=chunk.sample_count,
        )
        self._stop_output.clear()
        try:
            stream = sd.RawOutputStream(
                samplerate=chunk.sample_rate_hz,
                blocksize=0,
                device=device_index,
                channels=chunk.channels,
                dtype="int16",
            )
            self._active_output = stream
            stream.start()
            bytes_per_frame = 2 * chunk.channels
            block_bytes = max(bytes_per_frame, chunk.sample_rate_hz // 20 * bytes_per_frame)
            for offset in range(0, len(chunk.pcm_s16le), block_bytes):
                if cancel.is_set() or self._stop_output.is_set():
                    await asyncio.to_thread(stream.abort)
                    return (
                        started_event,
                        AudioOutputEvent(
                            session_id=chunk.session_id,
                            sequence=chunk.sequence * 2,
                            kind=AudioOutputKind.STOPPED,
                            phrase=chunk.phrase,
                        ),
                    )
                await asyncio.to_thread(
                    stream.write, chunk.pcm_s16le[offset : offset + block_bytes]
                )
            await asyncio.to_thread(stream.stop)
            return (
                started_event,
                AudioOutputEvent(
                    session_id=chunk.session_id,
                    sequence=chunk.sequence * 2,
                    kind=AudioOutputKind.FINISHED,
                    phrase=chunk.phrase,
                    sample_count=chunk.sample_count,
                ),
            )
        except Exception:
            return (
                AudioOutputEvent(
                    session_id=chunk.session_id,
                    sequence=(chunk.sequence * 2) - 1,
                    kind=AudioOutputKind.FAILED,
                    phrase=chunk.phrase,
                    detail="audio output failed",
                ),
            )
        finally:
            active = self._active_output
            self._active_output = None
            if active is not None:
                with suppress(Exception):
                    await asyncio.to_thread(active.close)

    async def stop(self) -> None:
        self._stop_output.set()
        active = self._active_output
        if active is not None:
            with suppress(Exception):
                await asyncio.to_thread(active.abort)
