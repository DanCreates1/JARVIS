"""Reproducible local Phase 2 corpus, WER, latency, trigger, and barge-in harness."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import importlib.metadata
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
import wave
from array import array
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from jarvis.bootstrap import build_runtime
from jarvis.config import Settings
from jarvis.core.models import ModelRole, RuntimeStatus
from jarvis.voice.audio_io import SoundDeviceAudio
from jarvis.voice.bootstrap import build_voice_runtime
from jarvis.voice.models import (
    AudioChunk,
    AudioClip,
    AudioFrame,
    CaptureRequest,
    DeviceSelection,
    SpeechSegment,
    TranscriptEvent,
    TranscriptKind,
    VoiceControl,
    VoiceEventType,
    VoiceFailureCode,
)
from jarvis.voice.session import VoiceSessionController
from jarvis.voice.settings_store import VoiceSettingsFile
from jarvis.voice.signal import DoubleClapDetector, resample_mono_pcm_s16le, signal_features
from jarvis.voice.speech import (
    FasterWhisperSTTProvider,
    OpenWakeWordProvider,
    SapiTTSProvider,
    SileroVADProvider,
)

COMMANDS = (
    "What time is it?",
    "Summarize my last message.",
    "Explain why the sky looks blue.",
    "Start a private local conversation.",
    "Please read this response aloud.",
    "Cancel the current answer.",
    "Show the available audio devices.",
    "Keep this request on my computer.",
    "Tell me a short science fact.",
    "How much memory is available?",
)
ACCENT_REFERENCE = (
    "Please call Stella. Ask her to bring these things with her from the store: Six spoons of "
    "fresh snow peas, five thick slabs of blue cheese, and maybe a snack for her brother Bob. "
    "We also need a small plastic snake and a big toy frog for the kids. She can scoop these "
    "things into three red bags, and we will go meet her Wednesday at the train station."
)
ACCENT_FILES = {
    "arabic99.mp3": "https://osf.io/download/698a91e973d8582918e24e2b/",
    "korean48.mp3": "https://osf.io/download/698b51508582406755e24e2a/",
    "mandarin107.mp3": "https://osf.io/download/698b5451e179eb7e44c72a9d/",
    "german26.mp3": "https://osf.io/download/698b4b440cbfd21038dfcea2/",
    "thai12.mp3": "https://osf.io/download/698d74184ed52ae49cdfcb5f/",
    "urdu18.mp3": "https://osf.io/download/698d76824ed52ae49cdfcd5a/",
    "turkish28.mp3": "https://osf.io/download/698d758551db31ca2ce25389/",
    "russian12.mp3": "https://osf.io/download/698b93fd3414fc2c3cc72ac7/",
    "spanish79.mp3": "https://osf.io/download/698d70c54ed52ae49cdfc84a/",
    "portuguese10.mp3": "https://osf.io/download/698b91ec59e5cbdd890c88c1/",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "prepare",
            "stt",
            "triggers",
            "barge",
            "device",
            "kill",
            "pipeline",
            "soak",
            "verify",
        ),
    )
    parser.add_argument("--runtime-dir", type=Path, default=Path("runtime/phase2-benchmark"))
    parser.add_argument("--seconds", type=int, default=1_800)
    parser.add_argument("--enforce", action="store_true")
    return parser.parse_args()


async def prepare(runtime_dir: Path) -> None:
    corpus_dir = runtime_dir / "corpus"
    quiet_dir = corpus_dir / "quiet"
    noisy_dir = corpus_dir / "noisy"
    accent_dir = corpus_dir / "accented"
    for directory in (quiet_dir, noisy_dir, accent_dir):
        directory.mkdir(parents=True, exist_ok=True)
    tts = SapiTTSProvider()
    cases: list[dict[str, str]] = []
    for index, reference in enumerate(COMMANDS, start=1):
        chunks = [
            chunk
            async for chunk in tts.synthesize(
                session_id=f"corpus-{index}", text=reference, cancel=asyncio.Event()
            )
        ]
        if len(chunks) != 1:
            raise RuntimeError("benchmark command unexpectedly produced multiple TTS chunks")
        quiet_path = quiet_dir / f"command-{index:02d}.wav"
        noisy_path = noisy_dir / f"command-{index:02d}.wav"
        write_wav(quiet_path, chunks[0])
        write_wav(noisy_path, add_noise(chunks[0], seed=index, snr_db=10))
        cases.extend(
            (
                {"category": "quiet", "path": str(quiet_path), "reference": reference},
                {"category": "noisy", "path": str(noisy_path), "reference": reference},
            )
        )
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for name, url in ACCENT_FILES.items():
            path = accent_dir / name
            if not path.exists():
                response = await client.get(url)
                response.raise_for_status()
                if len(response.content) > 3_000_000:
                    raise RuntimeError(f"accent file exceeds size cap: {name}")
                path.write_bytes(response.content)
            cases.append({"category": "accented", "path": str(path), "reference": ACCENT_REFERENCE})
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "sample_count": len(cases),
        "accent_source": "George Mason Speech Accent Archive / OSF",
        "accent_license": "CC-BY-NC-SA-4.0",
        "accent_source_url": "https://accent.gmu.edu/download/",
        "synthetic_source": (
            "Windows SAPI installed voice; noisy variants use deterministic 10 dB SNR noise"
        ),
        "cases": cases,
    }
    (runtime_dir / "corpus-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(
        json.dumps({"prepared": len(cases), "manifest": str(runtime_dir / "corpus-manifest.json")})
    )


async def benchmark_stt(runtime_dir: Path, *, enforce: bool) -> None:
    manifest = json.loads((runtime_dir / "corpus-manifest.json").read_text(encoding="utf-8"))
    settings = Settings()
    vad = SileroVADProvider()
    stt = FasterWhisperSTTProvider(
        model_name=settings.voice_stt_model,
        model_dir=settings.voice_model_dir,
        language=settings.voice_stt_language,
        cpu_threads=settings.voice_stt_cpu_threads,
        local_files_only=True,
    )
    gpu_before = nvidia_gpu_snapshot()
    loaded_ollama_models = await ollama_loaded_models(str(settings.ollama_base_url))
    start_rss = working_set_bytes()
    cold_started = time.perf_counter()
    await asyncio.gather(vad.health_check(), stt.health_check())
    cold_start_ms = (time.perf_counter() - cold_started) * 1_000
    results: list[dict[str, Any]] = []
    peak_rss = max(start_rss, working_set_bytes())
    process_start = time.process_time()
    wall_start = time.perf_counter()
    for index, case in enumerate(manifest["cases"], start=1):
        pcm, sample_rate_hz = decode_audio(Path(case["path"]))
        clip = AudioClip(
            session_id=f"benchmark-{index}",
            captured_at=datetime.now(UTC),
            sample_rate_hz=sample_rate_hz,
            pcm_s16le=pcm,
        )
        started = time.perf_counter()
        error: str | None = None
        hypothesis = ""
        try:
            segments = await vad.speech_segments(clip)
            events = [
                event
                async for event in stt.transcribe(
                    clip,
                    speech_segments=segments,
                    cancel=asyncio.Event(),
                )
            ]
            hypothesis = events[-1].text
        except Exception as exc:
            error = type(exc).__name__
        latency_ms = (time.perf_counter() - started) * 1_000
        peak_rss = max(peak_rss, working_set_bytes())
        results.append(
            {
                "category": case["category"],
                "path": Path(case["path"]).name,
                "duration_ms": clip.duration_ms,
                "latency_ms": round(latency_ms, 2),
                "real_time_factor": round(latency_ms / max(1, clip.duration_ms), 4),
                "wer": round(word_error_rate(case["reference"], hypothesis), 4),
                "hypothesis": hypothesis,
                "error": error,
            }
        )
        print(f"{index:02d}/{len(manifest['cases'])} {case['category']} {latency_ms:.0f} ms")
    summaries = {
        category: summarize_category(results, category)
        for category in ("quiet", "noisy", "accented")
    }
    interactive_results = [item for item in results if item["category"] in {"quiet", "noisy"}]
    interactive_latencies = [float(item["latency_ms"]) for item in interactive_results]
    all_rtf = [float(item["real_time_factor"]) for item in results]
    elapsed = time.perf_counter() - wall_start
    cpu_ratio = (time.process_time() - process_start) / max(elapsed, 0.001)
    gpu_after = nvidia_gpu_snapshot()
    gpu_growth_mib = (
        max(0, gpu_after["memory_used_mib"] - gpu_before["memory_used_mib"])
        if gpu_before is not None and gpu_after is not None
        else None
    )
    thresholds = {
        "quiet_wer": summaries["quiet"]["wer_mean"] <= 0.20,
        "noisy_wer": summaries["noisy"]["wer_mean"] <= 0.35,
        "accented_wer": summaries["accented"]["wer_mean"] <= 0.35,
        "interactive_latency_p95_ms": percentile(interactive_latencies, 0.95) <= 1_000,
        "rtf_p95": percentile(all_rtf, 0.95) <= 1.0,
        "rss_growth": max(0, peak_rss - start_rss) <= 4 * 1_024 * 1_024 * 1_024,
        "gpu_growth": gpu_growth_mib is not None and gpu_growth_mib <= 512,
        "local_llm_loaded": settings.local_model in loaded_ollama_models,
        "no_errors": not any(item["error"] for item in results),
    }
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "sample_count": len(results),
        "cold_warm": "model load measured separately; all corpus samples use warmed adapters",
        "settings": {
            "sample_rate_hz": 16_000,
            "stt_model": settings.voice_stt_model,
            "compute": "cpu/int8",
            "cpu_threads": settings.voice_stt_cpu_threads,
        },
        "versions": versions(),
        "platform": platform.platform(),
        "cold_start_ms": round(cold_start_ms, 2),
        "interactive_latency_p50_ms": round(percentile(interactive_latencies, 0.50), 2),
        "interactive_latency_p95_ms": round(percentile(interactive_latencies, 0.95), 2),
        "rtf_p50": round(percentile(all_rtf, 0.50), 4),
        "rtf_p95": round(percentile(all_rtf, 0.95), 4),
        "start_rss_bytes": start_rss,
        "peak_rss_bytes": peak_rss,
        "peak_rss_growth_bytes": max(0, peak_rss - start_rss),
        "cpu_core_ratio": round(cpu_ratio, 3),
        "gpu_before": gpu_before,
        "gpu_after": gpu_after,
        "gpu_memory_growth_mib": gpu_growth_mib,
        "loaded_ollama_models": loaded_ollama_models,
        "summaries": summaries,
        "thresholds": thresholds,
        "results": results,
    }
    output = runtime_dir / "stt-benchmark.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "sample_count",
                    "cold_start_ms",
                    "interactive_latency_p50_ms",
                    "interactive_latency_p95_ms",
                    "rtf_p50",
                    "rtf_p95",
                )
            },
            indent=2,
        )
    )
    print(json.dumps({"summaries": summaries, "thresholds": thresholds}, indent=2))
    if enforce and not all(thresholds.values()):
        raise SystemExit(1)


async def benchmark_triggers(runtime_dir: Path, *, enforce: bool) -> None:
    settings = Settings()
    wake_path = settings.voice_wake_model_dir / "hey_jarvis_v0.1.onnx"
    wake = OpenWakeWordProvider(model_path=wake_path, wake_word="hey_jarvis")
    tts = SapiTTSProvider()
    positives = (
        "Hey Jarvis.",
        "Hey, Jarvis!",
        "Hey Jarvis, please help.",
        "Hey Jarvis, what time is it?",
        "Hey Jarvis, are you ready?",
    ) * 4
    wake_hits = 0
    for index, phrase in enumerate(positives, start=1):
        chunks = [
            chunk
            async for chunk in tts.synthesize(
                session_id=f"wake-{index}", text=phrase, cancel=asyncio.Event()
            )
        ]
        audio = to_16k(chunks[0])
        if await detect_wake(wake, audio, f"wake-{index}"):
            wake_hits += 1
        await wake.reset()
    false_categories = ("music", "tv", "typing", "room")
    false_minutes_per_category = 15
    wake_false = 0
    clap_false = 0
    for category in false_categories:
        detector = DoubleClapDetector()
        for index, block in enumerate(
            noise_blocks(category, minutes=false_minutes_per_category), start=1
        ):
            frame = AudioFrame(
                session_id=f"false-{category}",
                sequence=index,
                captured_at=datetime.now(UTC),
                monotonic_ns=index * 80_000_000,
                sample_rate_hz=16_000,
                pcm_s16le=block,
            )
            if await wake.detect(frame) is not None:
                wake_false += 1
            if detector.process(frame) is not None:
                clap_false += 1
        await wake.reset()
    clap_hits = 0
    for trial in range(20):
        detector = DoubleClapDetector()
        background = array("h", [0] * 1_280)
        impulse = array("h", background)
        for index in range(80):
            impulse[index] = (20_000 + (trial * 300)) * (-1 if index % 2 else 1)
        first = AudioFrame(
            session_id="clap-positive",
            sequence=1,
            captured_at=datetime.now(UTC),
            monotonic_ns=1_000_000_000,
            sample_rate_hz=16_000,
            pcm_s16le=impulse.tobytes(),
        )
        second = first.model_copy(update={"sequence": 2, "monotonic_ns": 1_300_000_000})
        detector.process(first)
        if detector.process(second) is not None:
            clap_hits += 1
    false_hours = false_minutes_per_category * len(false_categories) / 60
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "positive_samples": 20,
        "false_corpus_hours": false_hours,
        "false_categories": false_categories,
        "wake_true_accept_rate": wake_hits / 20,
        "wake_false_accepts_per_hour": wake_false / false_hours,
        "clap_true_accept_rate": clap_hits / 20,
        "clap_false_accepts_per_hour": clap_false / false_hours,
        "always_listening_enabled": False,
        "versions": versions(),
    }
    report["thresholds"] = {
        "wake_true_accept": report["wake_true_accept_rate"] >= 0.90,
        "wake_false_accept": report["wake_false_accepts_per_hour"] <= 1.0,
        "clap_true_accept": report["clap_true_accept_rate"] >= 0.90,
        "clap_false_accept": report["clap_false_accepts_per_hour"] <= 1.0,
    }
    (runtime_dir / "trigger-benchmark.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if enforce and not all(report["thresholds"].values()):
        raise SystemExit(1)


async def benchmark_barge(runtime_dir: Path, *, enforce: bool) -> None:
    settings = Settings()
    selection = VoiceSettingsFile(settings.voice_settings_path).load_devices()
    output = SoundDeviceAudio()
    latencies: list[float] = []
    for index in range(30):
        cancel = asyncio.Event()
        chunk = AudioChunk(
            session_id="barge-benchmark",
            sequence=index + 1,
            sample_rate_hz=16_000,
            pcm_s16le=array("h", [0] * 32_000).tobytes(),
            phrase="silent stop benchmark",
        )
        task = asyncio.create_task(
            output.play(chunk, device_id=selection.output_device_id, cancel=cancel)
        )
        await asyncio.sleep(0.05)
        started = time.perf_counter()
        cancel.set()
        await output.stop()
        events = await task
        latencies.append((time.perf_counter() - started) * 1_000)
        if events[-1].kind.value not in {"stopped", "finished"}:
            raise RuntimeError("barge output benchmark failed")
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "samples": len(latencies),
        "audible_content": False,
        "latency_p50_ms": round(percentile(latencies, 0.50), 2),
        "latency_p95_ms": round(percentile(latencies, 0.95), 2),
    }
    report["threshold_pass"] = report["latency_p95_ms"] <= 250
    (runtime_dir / "barge-benchmark.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    if enforce and not report["threshold_pass"]:
        raise SystemExit(1)


async def benchmark_device(runtime_dir: Path, *, enforce: bool) -> None:
    settings = Settings()
    store = VoiceSettingsFile(settings.voice_settings_path)
    if not store.load_control().enabled:
        raise RuntimeError("voice software kill switch is active; run `jarvis voice enable`")
    selection = store.load_devices()
    if selection.input_device_id is None or selection.output_device_id is None:
        raise RuntimeError("persist both voice device selections before hardware smoke")
    audio = SoundDeviceAudio()
    request = CaptureRequest(
        device_id=selection.input_device_id,
        sample_rate_hz=settings.voice_sample_rate_hz,
        frame_samples=settings.voice_frame_samples,
        max_duration_ms=1_000,
    )
    await audio.check_input_settings(request)
    clip = await audio.capture(
        session_id="phase2-device-smoke",
        request=request,
        stop=asyncio.Event(),
    )
    rms, peak, _crossings = signal_features(clip.pcm_s16le)
    rendered = await anext(
        SapiTTSProvider().synthesize(
            session_id="phase2-device-smoke",
            text="ready",
            cancel=asyncio.Event(),
        )
    )
    silent_render = rendered.model_copy(
        update={"pcm_s16le": b"\0" * len(rendered.pcm_s16le), "phrase": "silent hardware smoke"}
    )
    output_events = await audio.play(
        silent_render,
        device_id=selection.output_device_id,
        cancel=asyncio.Event(),
    )
    await audio.stop()
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "input_device_id": selection.input_device_id,
        "output_device_id": selection.output_device_id,
        "capture_duration_ms": clip.duration_ms,
        "capture_dropped_frames": clip.dropped_frames,
        "capture_rms": round(rms, 6),
        "capture_peak": round(peak, 6),
        "output_sample_rate_hz": silent_render.sample_rate_hz,
        "output_channels": silent_render.channels,
        "output_kind": output_events[-1].kind.value,
        "audible_content": False,
        "raw_audio_retained": False,
        "software_kill_enabled_during_smoke": False,
    }
    report["threshold_pass"] = (
        clip.duration_ms >= 900 and clip.dropped_frames == 0 and report["output_kind"] == "finished"
    )
    (runtime_dir / "device-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if enforce and not report["threshold_pass"]:
        raise SystemExit(1)


async def benchmark_pipeline(runtime_dir: Path, *, enforce: bool) -> None:
    host_settings = Settings()
    isolated_settings = Settings(
        data_dir=runtime_dir / "pipeline-data",
        cloud_policy="local_only",
        _env_file=None,
    )
    vad = SileroVADProvider()
    stt = FasterWhisperSTTProvider(
        model_name=host_settings.voice_stt_model,
        model_dir=host_settings.voice_model_dir,
        language=host_settings.voice_stt_language,
        cpu_threads=host_settings.voice_stt_cpu_threads,
        local_files_only=True,
    )
    tts = SapiTTSProvider()
    pcm, sample_rate_hz = decode_audio(runtime_dir / "corpus" / "quiet" / "command-09.wav")
    clip = AudioClip(
        session_id="phase2-pipeline",
        captured_at=datetime.now(UTC),
        sample_rate_hz=sample_rate_hz,
        pcm_s16le=pcm,
    )
    started = time.perf_counter()
    core = await build_runtime(isolated_settings)
    try:
        segments = await vad.speech_segments(clip)
        transcript_events = [
            event
            async for event in stt.transcribe(
                clip,
                speech_segments=segments,
                cancel=asyncio.Event(),
            )
        ]
        result = await core.service.respond(
            transcript_events[-1].text,
            requested_model_role=ModelRole.LOCAL,
            metadata={"interface": "voice-benchmark", "audio_retained": False},
        )
        chunks = [
            chunk
            async for chunk in tts.synthesize(
                session_id="phase2-pipeline",
                text=result.reply or "Text fallback available.",
                cancel=asyncio.Event(),
            )
        ]
        routing = next(
            (event.routing for event in result.events if event.routing is not None), None
        )
    finally:
        await core.close()
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "elapsed_ms": round((time.perf_counter() - started) * 1_000, 2),
        "transcript_events": len(transcript_events),
        "transcript_characters": len(transcript_events[-1].text),
        "assistant_status": result.status.value,
        "assistant_provider": isolated_settings.local_provider,
        "assistant_model_role": routing.chosen_role.value if routing else None,
        "tts_chunks": len(chunks),
        "tts_pcm_bytes": sum(len(chunk.pcm_s16le) for chunk in chunks),
        "raw_audio_retained": False,
        "isolated_runtime_data": str(isolated_settings.data_dir),
    }
    report["threshold_pass"] = (
        result.status is RuntimeStatus.COMPLETED
        and bool(transcript_events[-1].text)
        and bool(chunks)
        and report["assistant_model_role"] == ModelRole.LOCAL.value
    )
    (runtime_dir / "pipeline-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if enforce and not report["threshold_pass"]:
        raise SystemExit(1)


async def benchmark_kill(runtime_dir: Path, *, enforce: bool) -> None:
    settings = Settings()
    components = await build_voice_runtime(settings)
    if not components.settings_store.load_control().enabled:
        await components.close()
        raise RuntimeError("voice software kill switch is active; run `jarvis voice enable`")
    started = time.perf_counter()
    async with components:
        turn = asyncio.create_task(
            components.controller.run_push_to_talk(stop_capture=asyncio.Event())
        )
        await asyncio.sleep(0.25)
        components.settings_store.save_control(
            VoiceControl(enabled=False, updated_at=datetime.now(UTC))
        )
        result = await asyncio.wait_for(turn, timeout=2)
    elapsed_ms = (time.perf_counter() - started) * 1_000
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "elapsed_ms": round(elapsed_ms, 2),
        "failure_code": result.failure.code.value if result.failure else None,
        "final_state": result.final_state.value,
        "kill_event": any(event.type is VoiceEventType.KILL_SWITCH for event in result.events),
        "software_kill_active_after": not components.settings_store.load_control().enabled,
        "raw_audio_retained": False,
    }
    report["threshold_pass"] = (
        result.failure is not None
        and result.failure.code is VoiceFailureCode.CANCELLED
        and report["kill_event"]
        and report["software_kill_active_after"]
        and elapsed_ms <= 1_000
    )
    (runtime_dir / "kill-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if enforce and not report["threshold_pass"]:
        raise SystemExit(1)


async def soak(runtime_dir: Path, *, seconds: int, enforce: bool) -> None:
    if seconds < 1:
        raise ValueError("soak seconds must be positive")
    detector = DoubleClapDetector()
    settings_store = VoiceSettingsFile(runtime_dir / "soak-voice-settings.json")
    settings_store.save_control(VoiceControl(enabled=True, updated_at=datetime.now(UTC)))
    settings_store.save_devices(DeviceSelection())
    controller = VoiceSessionController(
        assistant=_SoakAssistant(),
        audio_input=_SoakInput(),
        vad=_SoakVAD(),
        stt=_SoakSTT(),
        tts=_SoakTTS(),
        audio_output=_SoakOutput(),
        settings_store=settings_store,
        capture_request=CaptureRequest(max_duration_ms=1_000),
        monitor_barge_in=False,
    )
    start_rss = working_set_bytes()
    peak_rss = start_rss
    started = time.perf_counter()
    frames = 0
    state_turns = 0
    state_failures = 0
    deadline = started + seconds
    next_state_turn = started
    generator = noise_blocks("room", minutes=max(1, math.ceil(seconds / 60) + 2))
    while time.perf_counter() < deadline:
        block = next(generator)
        frames += 1
        detector.process(
            AudioFrame(
                session_id="phase2-soak",
                sequence=frames,
                captured_at=datetime.now(UTC),
                monotonic_ns=time.monotonic_ns(),
                sample_rate_hz=16_000,
                pcm_s16le=block,
            )
        )
        if time.perf_counter() >= next_state_turn:
            result = await controller.run_push_to_talk(stop_capture=asyncio.Event())
            state_turns += 1
            sequences = [event.sequence for event in result.events]
            if (
                result.failure is not None
                or result.final_state.value != "idle"
                or controller.state.value != "idle"
            ):
                state_failures += 1
            if sequences != list(range(1, len(sequences) + 1)):
                state_failures += 1
            next_state_turn += 1
        peak_rss = max(peak_rss, working_set_bytes())
        await asyncio.sleep(0.08)
    elapsed = time.perf_counter() - started
    growth = peak_rss - start_rss
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "requested_seconds": seconds,
        "elapsed_seconds": round(elapsed, 2),
        "frames": frames,
        "state_turns": state_turns,
        "state_failures": state_failures,
        "final_state": controller.state.value,
        "start_rss_bytes": start_rss,
        "peak_rss_bytes": peak_rss,
        "peak_growth_bytes": growth,
        "deadlock": False,
        "raw_audio_retained": False,
        "threshold_pass": (
            elapsed >= seconds
            and growth <= 256 * 1024 * 1024
            and state_turns >= seconds
            and state_failures == 0
            and controller.state.value == "idle"
        ),
    }
    (runtime_dir / "soak-benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if enforce and not report["threshold_pass"]:
        raise SystemExit(1)


class _SoakAssistant:
    async def respond(self, _user_input: str, **_kwargs: Any):
        from jarvis.core.models import RuntimeResult

        return RuntimeResult(status=RuntimeStatus.COMPLETED, reply="Ready.")


class _SoakInput:
    async def capture(
        self,
        *,
        session_id: str,
        request: CaptureRequest,
        stop: asyncio.Event,
    ) -> AudioClip:
        del stop
        return AudioClip(
            session_id=session_id,
            captured_at=datetime.now(UTC),
            sample_rate_hz=request.sample_rate_hz,
            pcm_s16le=array("h", [2_000, -2_000] * 2_560).tobytes(),
        )

    async def stream(self, **_kwargs: Any):
        if False:
            yield None

    async def list_devices(self):
        return ()


class _SoakVAD:
    async def speech_segments(self, clip: AudioClip):
        return (SpeechSegment(start_ms=0, end_ms=clip.duration_ms),)

    async def is_speech(self, _frame: AudioFrame) -> bool:
        return False

    async def reset(self) -> None:
        return None


class _SoakSTT:
    def transcribe(
        self,
        clip: AudioClip,
        *,
        speech_segments: Any,
        cancel: asyncio.Event,
    ):
        del speech_segments, cancel
        return self._transcribe(clip)

    async def _transcribe(self, clip: AudioClip):
        yield TranscriptEvent(
            session_id=clip.session_id,
            sequence=1,
            kind=TranscriptKind.FINAL,
            text="soak test",
            start_ms=0,
            end_ms=clip.duration_ms,
        )


class _SoakTTS:
    def synthesize(self, *, session_id: str, text: str, cancel: asyncio.Event):
        del cancel
        return self._synthesize(session_id, text)

    async def _synthesize(self, session_id: str, text: str):
        yield AudioChunk(
            session_id=session_id,
            sequence=1,
            sample_rate_hz=16_000,
            pcm_s16le=array("h", [0] * 160).tobytes(),
            phrase=text,
        )


class _SoakOutput:
    async def play(self, chunk: AudioChunk, **_kwargs: Any):
        from jarvis.voice.models import AudioOutputEvent, AudioOutputKind

        return (
            AudioOutputEvent(
                session_id=chunk.session_id,
                sequence=2,
                kind=AudioOutputKind.FINISHED,
                phrase=chunk.phrase,
            ),
        )

    async def stop(self) -> None:
        return None


def verify_reports(runtime_dir: Path) -> None:
    artifact_checks = {
        "stt-benchmark.json": lambda report: (
            report["sample_count"] >= 30 and all(report["thresholds"].values())
        ),
        "trigger-benchmark.json": lambda report: (
            report["positive_samples"] >= 20
            and report["false_corpus_hours"] >= 1
            and all(report["thresholds"].values())
        ),
        "barge-benchmark.json": lambda report: report["samples"] >= 30 and report["threshold_pass"],
        "device-smoke.json": lambda report: (
            report["capture_duration_ms"] >= 900 and report["threshold_pass"]
        ),
        "kill-smoke.json": lambda report: report["threshold_pass"],
        "pipeline-smoke.json": lambda report: (
            report["assistant_model_role"] == "local" and report["threshold_pass"]
        ),
        "soak-benchmark.json": lambda report: (
            report["requested_seconds"] >= 1_800
            and report["state_turns"] >= 1_800
            and report["threshold_pass"]
        ),
    }
    results: dict[str, bool] = {}
    for name, check in artifact_checks.items():
        path = runtime_dir / name
        if not path.is_file():
            results[name] = False
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        results[name] = bool(check(report))
    print(json.dumps({"artifacts": results, "threshold_pass": all(results.values())}, indent=2))
    if not all(results.values()):
        raise SystemExit(1)


def write_wav(path: Path, chunk: AudioChunk) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(chunk.channels)
        stream.setsampwidth(2)
        stream.setframerate(chunk.sample_rate_hz)
        stream.writeframes(chunk.pcm_s16le)


def add_noise(chunk: AudioChunk, *, seed: int, snr_db: float) -> AudioChunk:
    rng = random.Random(seed)
    samples = array("h", chunk.pcm_s16le)
    signal_rms = math.sqrt(sum(sample * sample for sample in samples) / max(1, len(samples)))
    noise_rms = signal_rms / (10 ** (snr_db / 20))
    mixed = array("h")
    for sample in samples:
        value = round(sample + rng.gauss(0, noise_rms))
        mixed.append(max(-32_768, min(32_767, value)))
    return chunk.model_copy(update={"pcm_s16le": mixed.tobytes()})


def decode_audio(path: Path) -> tuple[bytes, int]:
    if path.suffix.casefold() == ".wav":
        with wave.open(str(path), "rb") as stream:
            channels = stream.getnchannels()
            sample_width = stream.getsampwidth()
            sample_rate = stream.getframerate()
            pcm = stream.readframes(stream.getnframes())
        if channels != 1 or sample_width != 2:
            raise RuntimeError(f"unsupported benchmark WAV: {path.name}")
        if sample_rate != 16_000:
            pcm = resample_mono_pcm_s16le(pcm, source_rate_hz=sample_rate, target_rate_hz=16_000)
        return pcm, 16_000
    import av

    frames: list[bytes] = []
    with av.open(str(path)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16_000)
        for decoded in container.decode(audio=0):
            frames.extend(
                resampled.to_ndarray().tobytes() for resampled in resampler.resample(decoded)
            )
    if not frames:
        raise RuntimeError(f"audio decoder returned no frames: {path.name}")
    return b"".join(frames), 16_000


def to_16k(chunk: AudioChunk) -> bytes:
    if chunk.channels != 1:
        raise RuntimeError("wake benchmark requires mono TTS")
    return resample_mono_pcm_s16le(
        chunk.pcm_s16le,
        source_rate_hz=chunk.sample_rate_hz,
        target_rate_hz=16_000,
    )


async def detect_wake(provider: OpenWakeWordProvider, pcm: bytes, session_id: str) -> bool:
    block_bytes = 1_280 * 2
    for index, offset in enumerate(range(0, len(pcm), block_bytes), start=1):
        block = pcm[offset : offset + block_bytes]
        if len(block) < block_bytes:
            block += b"\0" * (block_bytes - len(block))
        event = await provider.detect(
            AudioFrame(
                session_id=session_id,
                sequence=index,
                captured_at=datetime.now(UTC),
                monotonic_ns=index * 80_000_000,
                sample_rate_hz=16_000,
                pcm_s16le=block,
            )
        )
        if event is not None:
            return True
    return False


def noise_blocks(category: str, *, minutes: int):
    rng = random.Random({"music": 11, "tv": 22, "typing": 33, "room": 44}[category])
    count = math.ceil(minutes * 60 / 0.08)
    for frame_index in range(count):
        samples = array("h")
        for sample_index in range(1_280):
            absolute = (frame_index * 1_280) + sample_index
            if category == "music":
                value = 3_000 * math.sin(2 * math.pi * 220 * absolute / 16_000)
                value += 2_000 * math.sin(2 * math.pi * 330 * absolute / 16_000)
            elif category == "tv":
                value = 2_000 * math.sin(2 * math.pi * 130 * absolute / 16_000)
                value += rng.gauss(0, 500)
            elif category == "typing":
                value = rng.gauss(0, 150)
                if sample_index < 5 and frame_index % 4 == 0:
                    value += (8_000 - (sample_index * 1_200)) * (-1 if sample_index % 2 else 1)
            else:
                value = rng.gauss(0, 350)
            samples.append(max(-32_768, min(32_767, round(value))))
        yield samples.tobytes()


def normalize_words(text: str) -> list[str]:
    return [
        "".join(character for character in word.casefold() if character.isalnum())
        for word in text.split()
        if any(character.isalnum() for character in word)
    ]


def word_error_rate(reference: str, hypothesis: str) -> float:
    expected = normalize_words(reference)
    actual = normalize_words(hypothesis)
    distances = list(range(len(actual) + 1))
    for expected_index, expected_word in enumerate(expected, start=1):
        current = [expected_index]
        for actual_index, actual_word in enumerate(actual, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    distances[actual_index] + 1,
                    distances[actual_index - 1] + (expected_word != actual_word),
                )
            )
        distances = current
    return distances[-1] / max(1, len(expected))


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def summarize_category(results: list[dict[str, Any]], category: str) -> dict[str, float | int]:
    selected = [item for item in results if item["category"] == category]
    return {
        "samples": len(selected),
        "wer_mean": round(statistics.fmean(float(item["wer"]) for item in selected), 4),
        "latency_p50_ms": round(
            percentile([float(item["latency_ms"]) for item in selected], 0.50), 2
        ),
        "latency_p95_ms": round(
            percentile([float(item["latency_ms"]) for item in selected], 0.95), 2
        ),
        "rtf_p95": round(
            percentile([float(item["real_time_factor"]) for item in selected], 0.95), 4
        ),
        "errors": sum(item["error"] is not None for item in selected),
    }


def working_set_bytes() -> int:
    if os.name != "nt":
        return 0

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
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    )
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return 0
    return int(counters.PeakWorkingSetSize)


def versions() -> dict[str, str]:
    packages = ("faster-whisper", "ctranslate2", "silero-vad", "sounddevice", "openwakeword")
    return {name: importlib.metadata.version(name) for name in packages}


def nvidia_gpu_snapshot() -> dict[str, int] | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        values = [int(value.strip()) for value in completed.stdout.splitlines()[0].split(",")]
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
    return {
        "memory_used_mib": values[0],
        "memory_total_mib": values[1],
        "utilization_percent": values[2],
        "temperature_c": values[3],
    }


async def ollama_loaded_models(base_url: str) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{base_url.rstrip('/')}/api/ps")
            response.raise_for_status()
            if len(response.content) > 100_000:
                return []
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    models = payload.get("models", []) if isinstance(payload, dict) else []
    return [
        str(item.get("name") or item.get("model"))
        for item in models
        if isinstance(item, dict) and (item.get("name") or item.get("model"))
    ]


async def main() -> None:
    args = parse_args()
    args.runtime_dir.mkdir(parents=True, exist_ok=True)
    if args.command == "prepare":
        await prepare(args.runtime_dir)
    elif args.command == "stt":
        await benchmark_stt(args.runtime_dir, enforce=args.enforce)
    elif args.command == "triggers":
        await benchmark_triggers(args.runtime_dir, enforce=args.enforce)
    elif args.command == "barge":
        await benchmark_barge(args.runtime_dir, enforce=args.enforce)
    elif args.command == "device":
        await benchmark_device(args.runtime_dir, enforce=args.enforce)
    elif args.command == "kill":
        await benchmark_kill(args.runtime_dir, enforce=args.enforce)
    elif args.command == "pipeline":
        await benchmark_pipeline(args.runtime_dir, enforce=args.enforce)
    elif args.command == "soak":
        await soak(args.runtime_dir, seconds=args.seconds, enforce=args.enforce)
    else:
        verify_reports(args.runtime_dir)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
