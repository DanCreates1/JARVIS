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

    def record_until_silence(
        self,
        stop_event: Event,
        interrupt_event: Event | None = None,
        speech_threshold: float = 0.018,
        silence_seconds: float = 0.65,
        pre_roll_seconds: float = 0.25,
        min_record_seconds: float = 1.4,
        max_record_seconds: float | None = None,
        start_timeout_seconds: float | None = None,
    ) -> Path | None:
        try:
            import sounddevice as sd
        except Exception as exc:
            raise AudioRecorderError("sounddevice is not installed or cannot load.") from exc

        block_size = int(self.sample_rate * 0.03)
        max_seconds = max_record_seconds or self.max_record_seconds
        pre_roll_blocks = max(1, int(pre_roll_seconds / 0.03))
        silence_blocks_needed = max(1, int(silence_seconds / 0.03))

        pre_roll: list[np.ndarray] = []
        captured: list[np.ndarray] = []
        recording = False
        silence_blocks = 0
        started_waiting = time.monotonic()
        recording_started = 0.0

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                blocksize=block_size,
            ) as stream:
                while not stop_event.is_set():
                    if interrupt_event is not None and interrupt_event.is_set() and not recording:
                        self.log.info("VAD wait interrupted")
                        return None

                    if (
                        not recording
                        and start_timeout_seconds is not None
                        and time.monotonic() - started_waiting > start_timeout_seconds
                    ):
                        return None

                    block, overflowed = stream.read(block_size)
                    if overflowed:
                        self.log.warning("Input stream overflow while recording")

                    mono = self._to_mono(block)
                    level = self._rms_level(mono)

                    if not recording:
                        pre_roll.append(mono)
                        pre_roll = pre_roll[-pre_roll_blocks:]
                        if level >= speech_threshold:
                            recording = True
                            recording_started = time.monotonic()
                            captured.extend(pre_roll)
                            silence_blocks = 0
                            self.log.info("Speech detected; recording started")
                        continue

                    captured.append(mono)
                    if level < speech_threshold:
                        silence_blocks += 1
                    else:
                        silence_blocks = 0

                    elapsed = time.monotonic() - recording_started
                    if silence_blocks >= silence_blocks_needed and elapsed >= min_record_seconds:
                        break
                    if elapsed >= max_seconds:
                        self.log.info("Stopped recording at max duration %.2fs", max_seconds)
                        break
        except Exception as exc:
            raise AudioRecorderError(f"Audio input failed: {exc}") from exc

        if not captured:
            return None
        frames = np.concatenate(captured, axis=0).astype(np.int16)
        duration = len(frames) / self.sample_rate
        self.log.info("VAD recording duration: %.2fs", duration)
        if duration < 0.35:
            self.log.info("Ignored short VAD recording: %.2fs", duration)
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

    def _to_mono(self, audio: np.ndarray) -> np.ndarray:
        if self.channels == 1:
            return audio.reshape(-1).astype(np.int16)
        return audio.mean(axis=1).astype(np.int16)

    def _rms_level(self, frames: np.ndarray) -> float:
        if frames.size == 0:
            return 0.0
        audio = frames.astype(np.float32) / 32768.0
        return float(np.sqrt(np.mean(audio * audio)))

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
