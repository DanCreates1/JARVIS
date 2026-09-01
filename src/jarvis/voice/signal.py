"""Deterministic local signal utilities for endpointing, echo, and clap events."""

from __future__ import annotations

import math
import re
from array import array
from collections import deque
from hashlib import sha256
from itertools import pairwise
from uuid import uuid4

from .models import (
    AcousticEventType,
    AudioChunk,
    AudioDeviceDirection,
    AudioFrame,
    HandsFreeIntent,
    HandsFreeIntentType,
)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def stable_device_id(
    *,
    host_api: str,
    name: str,
    direction: AudioDeviceDirection,
    max_channels: int,
    default_sample_rate_hz: int,
) -> str:
    """Create a stable non-secret identity from endpoint properties."""
    normalized = "|".join(
        (
            host_api.strip().casefold(),
            name.strip().casefold(),
            direction.value,
            str(max_channels),
            str(default_sample_rate_hz),
        )
    )
    return f"audio-{sha256(normalized.encode('utf-8')).hexdigest()[:24]}"


def phrase_chunks(text: str, *, max_characters: int = 240) -> tuple[str, ...]:
    """Split response text at stable speech boundaries while enforcing a hard phrase cap."""
    if max_characters < 20:
        raise ValueError("max_characters must be at least 20")
    normalized = " ".join(text.split())
    if not normalized:
        return ()
    chunks: list[str] = []
    for sentence in _SENTENCE_BOUNDARY.split(normalized):
        remaining = sentence.strip()
        while len(remaining) > max_characters:
            split_at = remaining.rfind(" ", 0, max_characters + 1)
            if split_at < 1:
                split_at = max_characters
            chunks.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()
        if remaining:
            chunks.append(remaining)
    return tuple(chunks)


def pcm_samples(pcm_s16le: bytes) -> array[int]:
    samples = array("h")
    samples.frombytes(pcm_s16le)
    if samples.itemsize != 2:  # pragma: no cover - CPython supported targets use 16-bit h
        raise RuntimeError("platform signed-short width is unsupported")
    return samples


def resample_mono_pcm_s16le(
    pcm_s16le: bytes,
    *,
    source_rate_hz: int,
    target_rate_hz: int,
) -> bytes:
    """Linearly resample mono PCM for render-reference matching, not speech synthesis."""
    if source_rate_hz < 1 or target_rate_hz < 1:
        raise ValueError("sample rates must be positive")
    if source_rate_hz == target_rate_hz:
        return pcm_s16le
    source = pcm_samples(pcm_s16le)
    if len(source) < 2:
        return pcm_s16le
    output_count = max(1, round(len(source) * target_rate_hz / source_rate_hz))
    output = array("h")
    scale = source_rate_hz / target_rate_hz
    for output_index in range(output_count):
        position = min(len(source) - 1, output_index * scale)
        left_index = math.floor(position)
        right_index = min(len(source) - 1, left_index + 1)
        fraction = position - left_index
        value = round((source[left_index] * (1 - fraction)) + (source[right_index] * fraction))
        output.append(max(-32_768, min(32_767, value)))
    return output.tobytes()


def signal_features(pcm_s16le: bytes) -> tuple[float, float, float]:
    """Return normalized RMS, peak, and zero-crossing rate."""
    samples = pcm_samples(pcm_s16le)
    if not samples:
        return 0.0, 0.0, 0.0
    scale = 32_768.0
    peak = max(abs(sample) for sample in samples) / scale
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / scale
    crossings = sum(
        1 for left, right in pairwise(samples) if (left < 0 <= right) or (left >= 0 > right)
    )
    zero_crossing_rate = crossings / max(1, len(samples) - 1)
    return rms, peak, zero_crossing_rate


class DoubleClapDetector:
    """Adaptive two-impulse detector that only emits a typed Phase 3 intent."""

    def __init__(
        self,
        *,
        minimum_peak: float = 0.35,
        minimum_rms: float = 0.035,
        minimum_crest_factor: float = 2.0,
        minimum_zero_crossing_rate: float = 0.04,
        minimum_interval_ms: int = 120,
        maximum_interval_ms: int = 650,
        cooldown_ms: int = 2_000,
    ) -> None:
        if not (0 < minimum_peak <= 1 and 0 < minimum_rms <= 1):
            raise ValueError("clap energy thresholds must be in (0, 1]")
        if minimum_interval_ms < 1 or maximum_interval_ms <= minimum_interval_ms:
            raise ValueError("clap interval bounds are invalid")
        if cooldown_ms < maximum_interval_ms:
            raise ValueError("clap cooldown must cover the detection window")
        self.minimum_peak = minimum_peak
        self.minimum_rms = minimum_rms
        self.minimum_crest_factor = minimum_crest_factor
        self.minimum_zero_crossing_rate = minimum_zero_crossing_rate
        self.minimum_interval_ns = minimum_interval_ms * 1_000_000
        self.maximum_interval_ns = maximum_interval_ms * 1_000_000
        self.cooldown_ns = cooldown_ms * 1_000_000
        self.reset()

    def reset(self) -> None:
        self._noise_rms = 0.005
        self._first_clap_ns: int | None = None
        self._last_candidate_ns: int | None = None
        self._cooldown_until_ns = 0

    def process(self, frame: AudioFrame) -> HandsFreeIntent | None:
        rms, peak, zero_crossing_rate = signal_features(frame.pcm_s16le)
        crest = peak / max(rms, 1e-6)
        adaptive_peak = max(self.minimum_peak, self._noise_rms * 8)
        adaptive_rms = max(self.minimum_rms, self._noise_rms * 4)
        is_candidate = (
            peak >= adaptive_peak
            and rms >= adaptive_rms
            and crest >= self.minimum_crest_factor
            and zero_crossing_rate >= self.minimum_zero_crossing_rate
        )
        if not is_candidate:
            self._noise_rms = (self._noise_rms * 0.98) + (min(rms, 0.2) * 0.02)
            if (
                self._first_clap_ns is not None
                and frame.monotonic_ns - self._first_clap_ns > self.maximum_interval_ns
            ):
                self._first_clap_ns = None
            return None
        if frame.monotonic_ns < self._cooldown_until_ns:
            return None
        if (
            self._last_candidate_ns is not None
            and frame.monotonic_ns - self._last_candidate_ns < self.minimum_interval_ns
        ):
            return None
        self._last_candidate_ns = frame.monotonic_ns
        if self._first_clap_ns is None:
            self._first_clap_ns = frame.monotonic_ns
            return None
        interval = frame.monotonic_ns - self._first_clap_ns
        if not (self.minimum_interval_ns <= interval <= self.maximum_interval_ns):
            self._first_clap_ns = frame.monotonic_ns
            return None
        self._first_clap_ns = None
        self._cooldown_until_ns = frame.monotonic_ns + self.cooldown_ns
        confidence = min(1.0, (peak + min(1.0, crest / 8) + zero_crossing_rate) / 2)
        return HandsFreeIntent(
            session_id=frame.session_id,
            source=AcousticEventType.DOUBLE_CLAP,
            intent=HandsFreeIntentType.LAUNCH_APP_GROUP,
            confidence=confidence,
            event_id=f"acoustic-{uuid4().hex}",
        )


class RenderReferenceSuppressor:
    """Reject microphone frames strongly correlated with recently rendered output."""

    def __init__(self, *, correlation_threshold: float = 0.82, history_frames: int = 12) -> None:
        if not 0 < correlation_threshold <= 1:
            raise ValueError("correlation threshold must be in (0, 1]")
        if history_frames < 1:
            raise ValueError("history_frames must be positive")
        self.correlation_threshold = correlation_threshold
        self._rendered: deque[tuple[int, array[int]]] = deque(maxlen=history_frames)

    def remember(self, chunk: AudioChunk, *, frame_samples: int = 512) -> None:
        samples = pcm_samples(chunk.pcm_s16le)
        for offset in range(0, len(samples), frame_samples):
            block = samples[offset : offset + frame_samples]
            if block:
                self._rendered.append((chunk.sample_rate_hz, block))

    def is_render_echo(self, frame: AudioFrame) -> bool:
        microphone = pcm_samples(frame.pcm_s16le)
        if not microphone:
            return False
        for sample_rate_hz, rendered in reversed(self._rendered):
            if sample_rate_hz != frame.sample_rate_hz:
                continue
            size = min(len(microphone), len(rendered))
            if size < 80:
                continue
            correlation = _absolute_correlation(microphone[:size], rendered[:size])
            if correlation >= self.correlation_threshold:
                return True
        return False

    def clear(self) -> None:
        self._rendered.clear()


def _absolute_correlation(left: array[int], right: array[int]) -> float:
    left_energy = math.sqrt(sum(value * value for value in left))
    right_energy = math.sqrt(sum(value * value for value in right))
    if left_energy == 0 or right_energy == 0:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    return abs(dot / (left_energy * right_energy))
