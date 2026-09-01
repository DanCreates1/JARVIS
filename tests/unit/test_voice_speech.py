from __future__ import annotations

import asyncio
import base64
import io
import wave
from array import array
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis.voice.models import AudioClip, AudioFrame, SpeechSegment, TranscriptKind
from jarvis.voice.speech import (
    EnergyVADProvider,
    FasterWhisperSTTProvider,
    OpenWakeWordProvider,
    SapiTTSProvider,
    SileroVADProvider,
    VoiceDependencyError,
    VoiceOperationCancelled,
    VoiceProviderError,
)


class FakeArray:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def astype(self, _dtype: object) -> FakeArray:
        return FakeArray(list(self.values))

    def __itruediv__(self, divisor: float) -> FakeArray:
        self.values = [value / divisor for value in self.values]
        return self

    def __truediv__(self, divisor: float) -> FakeArray:
        return FakeArray([value / divisor for value in self.values])

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, item: slice | int) -> FakeArray | float:
        if isinstance(item, slice):
            return FakeArray(self.values[item])
        return self.values[item]


class FakeNumpy:
    int16 = "int16"
    float32 = "float32"

    @staticmethod
    def frombuffer(data: bytes, *, dtype: object) -> FakeArray:
        assert dtype == "int16"
        return FakeArray([float(value) for value in array("h", data)])


class FakeTensorResult:
    def __init__(self, value: float) -> None:
        self.value = value

    def item(self) -> float:
        return self.value


class FakeSileroModel:
    def __init__(self) -> None:
        self.resets = 0

    def __call__(self, _audio: object, _sample_rate: int) -> FakeTensorResult:
        return FakeTensorResult(0.8)

    def reset_states(self) -> None:
        self.resets += 1


class FakeSileroModule:
    def __init__(self, model: FakeSileroModel) -> None:
        self.model = model

    def load_silero_vad(self, *, onnx: bool) -> FakeSileroModel:
        assert onnx is False
        return self.model

    @staticmethod
    def get_speech_timestamps(*_args: object, **_kwargs: object) -> list[dict[str, int]]:
        return [{"start": 1_600, "end": 8_000}]


class FakeTorch:
    @staticmethod
    def from_numpy(value: object) -> object:
        return value


def make_clip(*, samples: int = 16_000, amplitude: int = 5_000) -> AudioClip:
    return AudioClip(
        session_id="voice-test",
        captured_at=datetime.now(UTC),
        sample_rate_hz=16_000,
        pcm_s16le=array("h", [amplitude, -amplitude] * (samples // 2)).tobytes(),
    )


def make_frame(*, samples: int = 512) -> AudioFrame:
    return AudioFrame(
        session_id="voice-test",
        sequence=1,
        captured_at=datetime.now(UTC),
        monotonic_ns=1,
        sample_rate_hz=16_000,
        pcm_s16le=array("h", [5_000, -5_000] * (samples // 2)).tobytes(),
    )


@pytest.mark.asyncio
async def test_energy_vad_detects_speech_and_rejects_quiet_short_audio() -> None:
    provider = EnergyVADProvider(rms_threshold=0.01)
    clip = make_clip()
    assert (await provider.speech_segments(clip))[0].end_ms == 1_000
    assert await provider.is_speech(make_frame())
    quiet = make_clip(amplitude=1)
    assert await provider.speech_segments(quiet) == ()
    await provider.reset()
    with pytest.raises(ValueError):
        EnergyVADProvider(rms_threshold=0)


@pytest.mark.asyncio
async def test_silero_adapter_normalizes_segments_stream_scores_and_reset() -> None:
    model = FakeSileroModel()
    silero = FakeSileroModule(model)

    def loader(name: str) -> object:
        return {"silero_vad": silero, "numpy": FakeNumpy, "torch": FakeTorch}[name]

    provider = SileroVADProvider(module_loader=loader)
    segments = await provider.speech_segments(make_clip())
    assert segments == (SpeechSegment(start_ms=100, end_ms=500),)
    assert await provider.is_speech(make_frame())
    assert not await provider.is_speech(make_frame(samples=100))
    await provider.health_check()
    await provider.reset()
    assert model.resets == 1


@pytest.mark.asyncio
async def test_silero_adapter_fails_cleanly_when_dependency_or_format_missing() -> None:
    provider = SileroVADProvider(
        module_loader=lambda _name: (_ for _ in ()).throw(ImportError("missing"))
    )
    with pytest.raises(VoiceDependencyError, match="Silero"):
        await provider.health_check()
    bad = make_clip().model_copy(update={"sample_rate_hz": 11_025})
    with pytest.raises(VoiceProviderError, match="requires mono"):
        await SileroVADProvider().speech_segments(bad)


@pytest.mark.asyncio
async def test_faster_whisper_emits_partial_and_final_events(monkeypatch, tmp_path: Path) -> None:
    class FakeModel:
        def transcribe(self, _audio: object, **kwargs: object) -> tuple[list[object], object]:
            assert kwargs["vad_filter"] is False
            return (
                [SimpleNamespace(text=" hello ", start=0.0, end=0.4)],
                SimpleNamespace(language="en", language_probability=0.9),
            )

    monkeypatch.setattr(
        "jarvis.voice.speech.importlib.import_module",
        lambda name: FakeNumpy if name == "numpy" else None,
    )
    provider = FasterWhisperSTTProvider(
        model_name="base.en",
        model_dir=tmp_path,
        model_factory=lambda *_args, **_kwargs: FakeModel(),
    )
    events = [
        event
        async for event in provider.transcribe(
            make_clip(),
            speech_segments=(SpeechSegment(start_ms=100, end_ms=700),),
            cancel=asyncio.Event(),
        )
    ]
    assert [event.kind for event in events] == [TranscriptKind.PARTIAL, TranscriptKind.FINAL]
    assert events[-1].text == "hello"
    assert events[0].start_ms == 100
    await provider.health_check()


@pytest.mark.asyncio
async def test_faster_whisper_cancellation_and_empty_output_fail_closed(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        "jarvis.voice.speech.importlib.import_module",
        lambda name: FakeNumpy if name == "numpy" else None,
    )

    class EmptyModel:
        def transcribe(self, *_args: object, **_kwargs: object) -> tuple[list[object], object]:
            return [], SimpleNamespace(language="en", language_probability=None)

    provider = FasterWhisperSTTProvider(
        model_name="base.en",
        model_dir=tmp_path,
        model_factory=lambda *_args, **_kwargs: EmptyModel(),
    )
    cancel = asyncio.Event()
    cancel.set()
    with pytest.raises(VoiceOperationCancelled):
        _ = [
            event
            async for event in provider.transcribe(make_clip(), speech_segments=(), cancel=cancel)
        ]
    with pytest.raises(VoiceProviderError, match="no transcript"):
        _ = [
            event
            async for event in provider.transcribe(
                make_clip(), speech_segments=(), cancel=asyncio.Event()
            )
        ]


def make_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22_050)
        stream.writeframes(array("h", [100, -100] * 100).tobytes())
    return output.getvalue()


@pytest.mark.asyncio
async def test_sapi_tts_chunks_and_decodes_memory_wav(monkeypatch) -> None:
    provider = SapiTTSProvider()
    phrases: list[str] = []

    async def synthesize_phrase(phrase: str, _cancel: asyncio.Event) -> bytes:
        phrases.append(phrase)
        return make_wav()

    monkeypatch.setattr(provider, "_synthesize_phrase", synthesize_phrase)
    chunks = [
        chunk
        async for chunk in provider.synthesize(
            session_id="voice-test",
            text="First. Second?",
            cancel=asyncio.Event(),
        )
    ]
    assert phrases == ["First.", "Second?"]
    assert [chunk.sample_rate_hz for chunk in chunks] == [22_050, 22_050]
    await provider.health_check()
    cancel = asyncio.Event()
    cancel.set()
    with pytest.raises(VoiceOperationCancelled):
        _ = [
            chunk
            async for chunk in provider.synthesize(
                session_id="voice-test", text="cancel", cancel=cancel
            )
        ]

    limited = SapiTTSProvider(max_phrases=1)
    monkeypatch.setattr(limited, "_synthesize_phrase", synthesize_phrase)
    with pytest.raises(VoiceProviderError, match="phrase limit"):
        _ = [
            chunk
            async for chunk in limited.synthesize(
                session_id="voice-test",
                text="First. Second.",
                cancel=asyncio.Event(),
            )
        ]
    duration_limited = SapiTTSProvider(max_total_duration_ms=1)
    monkeypatch.setattr(duration_limited, "_synthesize_phrase", synthesize_phrase)
    with pytest.raises(VoiceProviderError, match="duration limit"):
        _ = [
            chunk
            async for chunk in duration_limited.synthesize(
                session_id="voice-test",
                text="First.",
                cancel=asyncio.Event(),
            )
        ]
    with pytest.raises(ValueError, match="limits"):
        SapiTTSProvider(max_phrases=0)


class FakeProcess:
    def __init__(self, stdout: bytes, *, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        self.input: bytes | None = None

    async def communicate(self, input_data: bytes) -> tuple[bytes, bytes]:
        self.input = input_data
        await asyncio.sleep(0)
        return self.stdout, b"private error"

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode


@pytest.mark.asyncio
async def test_sapi_subprocess_uses_static_command_and_stdin_data(monkeypatch) -> None:
    process = FakeProcess(base64.b64encode(make_wav()))
    arguments: tuple[object, ...] = ()

    async def create(*args: object, **_kwargs: object) -> FakeProcess:
        nonlocal arguments
        arguments = args
        return process

    monkeypatch.setattr("jarvis.voice.speech.asyncio.create_subprocess_exec", create)
    phrase = "hello; Remove-Item C:\\never"
    result = await SapiTTSProvider()._synthesize_phrase(phrase, asyncio.Event())
    assert result == make_wav()
    assert process.input == phrase.encode("utf-8")
    assert phrase not in arguments
    assert "-EncodedCommand" in arguments


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stdout", "returncode", "match"),
    [
        (b"ignored", 1, "local TTS failed"),
        (b"not-base64", 0, "malformed audio"),
    ],
)
async def test_sapi_subprocess_normalizes_failure(monkeypatch, stdout, returncode, match) -> None:
    process = FakeProcess(stdout, returncode=returncode)

    async def create(*_args: object, **_kwargs: object) -> FakeProcess:
        return process

    monkeypatch.setattr("jarvis.voice.speech.asyncio.create_subprocess_exec", create)
    with pytest.raises(VoiceProviderError, match=match):
        await SapiTTSProvider()._synthesize_phrase("safe", asyncio.Event())


@pytest.mark.asyncio
async def test_sapi_subprocess_cancellation_terminates_process(monkeypatch) -> None:
    gate = asyncio.Event()

    class BlockingProcess(FakeProcess):
        async def communicate(self, input_data: bytes) -> tuple[bytes, bytes]:
            self.input = input_data
            await gate.wait()
            return self.stdout, b""

    process = BlockingProcess(base64.b64encode(make_wav()))

    async def create(*_args: object, **_kwargs: object) -> FakeProcess:
        return process

    monkeypatch.setattr("jarvis.voice.speech.asyncio.create_subprocess_exec", create)
    cancel = asyncio.Event()
    task = asyncio.create_task(SapiTTSProvider()._synthesize_phrase("safe", cancel))
    await asyncio.sleep(0)
    cancel.set()
    with pytest.raises(VoiceOperationCancelled):
        await task
    assert process.terminated


def test_sapi_rejects_malformed_wav() -> None:
    with pytest.raises(VoiceProviderError, match="malformed"):
        SapiTTSProvider._decode_wav("voice-test", 1, "bad", b"bad")

    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(1)
        stream.setframerate(16_000)
        stream.writeframes(b"\x80" * 100)
    with pytest.raises(VoiceProviderError, match="unsupported"):
        SapiTTSProvider._decode_wav("voice-test", 1, "bad", output.getvalue())


@pytest.mark.asyncio
async def test_openwakeword_adapter_requires_model_and_normalizes_score(
    monkeypatch, tmp_path: Path
) -> None:
    missing = OpenWakeWordProvider(model_path=tmp_path / "missing.onnx")
    with pytest.raises(VoiceDependencyError, match="model file"):
        await missing.detect(make_frame())

    model_path = tmp_path / "hey_jarvis.onnx"
    model_path.write_bytes(b"model")

    class FakeWakeModel:
        def predict(self, _audio: object) -> dict[str, float]:
            return {"hey_jarvis_v0.1": 0.8}

        def reset(self) -> None:
            return None

    monkeypatch.setattr(
        "jarvis.voice.speech.importlib.import_module",
        lambda name: FakeNumpy if name == "numpy" else None,
    )
    provider = OpenWakeWordProvider(
        model_path=model_path,
        model_factory=lambda **_kwargs: FakeWakeModel(),
    )
    event = await provider.detect(make_frame())
    assert event is not None
    assert event.confidence == 0.8
    await provider.health_check()
    await provider.reset()

    quiet_provider = OpenWakeWordProvider(
        model_path=model_path,
        threshold=0.9,
        model_factory=lambda **_kwargs: FakeWakeModel(),
    )
    assert await quiet_provider.detect(make_frame()) is None
