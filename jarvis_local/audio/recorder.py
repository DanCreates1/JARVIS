from __future__ import annotations

import logging
import tempfile
import time
import wave
from pathlib import Path
from threading import Event

import numpy as np


class AudioRecorderError(RuntimeError):
    pass


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        max_record_seconds: float = 30.0,
        idle_sleep_seconds: float = 0.05,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_record_seconds = max_record_seconds
        self.idle_sleep_seconds = idle_sleep_seconds
        self.log = logging.getLogger("jarvis.audio.recorder")
        self.temp_dir = Path(tempfile.gettempdir()) / "jarvis_local_audio"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def check_microphone(self) -> None:
        try:
            import sounddevice as sd

            device = sd.query_devices(kind="input")
            if not device:
                raise AudioRecorderError("No input microphone was found.")
            self.log.info("Using input device: %s", device.get("name", "default"))
        except Exception as exc:
            raise AudioRecorderError(f"No working microphone found: {exc}") from exc

    def wait_for_push_to_talk(
        self,
        key: str,
        stop_event: Event,
        timeout_seconds: float | None = None,
    ) -> Path | None:
        try:
            import keyboard
        except Exception as exc:
            raise AudioRecorderError(
                "The keyboard package could not read keys. Try running as administrator."
            ) from exc

        start_wait = time.monotonic()
        while not stop_event.is_set():
            if timeout_seconds is not None and time.monotonic() - start_wait > timeout_seconds:
                return None
            try:
                if keyboard.is_pressed(key):
                    return self._record_while_pressed(key, stop_event)
            except Exception as exc:
                raise AudioRecorderError(
                    f"Could not read push-to-talk key '{key}': {exc}"
                ) from exc
            time.sleep(self.idle_sleep_seconds)
        return None

    def _record_while_pressed(self, key: str, stop_event: Event) -> Path | None:
        import keyboard

        self.log.info("Recording started")
        frames = self._capture_until(
            stop_event=stop_event,
            should_continue=lambda: keyboard.is_pressed(key),
            max_seconds=self.max_record_seconds,
        )
        if frames.size == 0:
            return None
        duration = len(frames) / self.sample_rate
        if duration < 0.25:
            self.log.info("Ignored short recording: %.2fs", duration)
            return None
        return self._write_wav(frames)

    def record_for(self, seconds: float, stop_event: Event) -> Path | None:
        frames = self._capture_until(
            stop_event=stop_event,
            should_continue=lambda: True,
            max_seconds=seconds,
        )
        if frames.size == 0:
            return None
        return self._write_wav(frames)

    def _capture_until(
        self,
        stop_event: Event,
        should_continue,
        max_seconds: float,
    ) -> np.ndarray:
        try:
            import sounddevice as sd
        except Exception as exc:
            raise AudioRecorderError("sounddevice is not installed or cannot load.") from exc

        chunks: list[np.ndarray] = []

        def callback(indata, frames, time_info, status) -> None:
            if status:
                self.log.warning("Input stream status: %s", status)
            chunks.append(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                callback=callback,
            ):
                started = time.monotonic()
                while (
                    not stop_event.is_set()
                    and should_continue()
                    and time.monotonic() - started < max_seconds
                ):
                    time.sleep(0.02)
        except Exception as exc:
            raise AudioRecorderError(f"Audio input failed: {exc}") from exc

        if not chunks:
            return np.array([], dtype=np.int16)
        audio = np.concatenate(chunks, axis=0)
        if self.channels == 1:
            return audio.reshape(-1).astype(np.int16)
        return audio.mean(axis=1).astype(np.int16)

    def _write_wav(self, frames: np.ndarray) -> Path:
        path = self.temp_dir / f"input_{int(time.time() * 1000)}.wav"
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(frames.tobytes())
        self.log.info("Saved audio: %s", path)
        return path

    def detect_double_clap(
        self,
        audio_path: Path,
        threshold: float = 0.35,
        min_gap_seconds: float = 0.15,
        max_gap_seconds: float = 0.9,
    ) -> bool:
        try:
            with wave.open(str(audio_path), "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                samples = wav_file.readframes(wav_file.getnframes())
        except Exception as exc:
            raise AudioRecorderError(f"Could not read audio for clap detection: {exc}") from exc

        audio = np.frombuffer(samples, dtype=np.int16).astype(np.float32)
        if audio.size < sample_rate // 2:
            return False

        audio = np.abs(audio / 32768.0)
        window = max(1, int(sample_rate * 0.025))
        hop = max(1, int(sample_rate * 0.01))
        levels: list[float] = []
        times: list[float] = []
        for start in range(0, len(audio) - window, hop):
            chunk = audio[start : start + window]
            levels.append(float(np.sqrt(np.mean(chunk * chunk))))
            times.append(start / sample_rate)
        if not levels:
            return False

        levels_array = np.array(levels)
        noise_floor = float(np.percentile(levels_array, 70))
        clap_threshold = max(threshold, noise_floor * 5.0)

        peaks: list[float] = []
        last_peak_time = -10.0
        for index in range(1, len(levels_array) - 1):
            level = levels_array[index]
            if level < clap_threshold:
                continue
            if level < levels_array[index - 1] or level < levels_array[index + 1]:
                continue
            peak_time = times[index]
            if peak_time - last_peak_time < min_gap_seconds:
                continue
            peaks.append(peak_time)
            last_peak_time = peak_time

        for first, second in zip(peaks, peaks[1:]):
            gap = second - first
            if min_gap_seconds <= gap <= max_gap_seconds:
                self.log.info("Double-clap peak gap: %.2fs", gap)
                return True
        return False
