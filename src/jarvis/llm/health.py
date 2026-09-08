"""Process-lifetime provider health used for adaptive, privacy-safe routing."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from time import monotonic

from jarvis.core.models import ProviderUsage

from .base import ProviderError, ProviderQuotaError, ProviderUnavailableError


@dataclass(frozen=True, slots=True)
class LatencyBudgets:
    simple_local_ms: float = 3_000
    normal_voice_ms: float = 2_500
    fast_cloud_ms: float = 2_500
    deep_reasoning_ms: float = 7_000

    def __post_init__(self) -> None:
        if (
            min(
                self.simple_local_ms,
                self.normal_voice_ms,
                self.fast_cloud_ms,
                self.deep_reasoning_ms,
            )
            <= 0
        ):
            raise ValueError("latency budgets must be positive")


@dataclass(frozen=True, slots=True)
class ProviderHealthSnapshot:
    sample_count: int
    success_count: int
    failure_count: int
    ttft_p50_ms: float | None
    ttft_p95_ms: float | None
    total_p50_ms: float | None
    total_p95_ms: float | None
    error_rate: float
    recent_429_count: int
    recent_5xx_count: int
    quota_limited: bool
    degraded: bool


@dataclass(frozen=True, slots=True)
class _Observation:
    success: bool
    ttft_ms: float | None
    total_ms: float | None
    status_code: int | None


class ProviderHealthTracker:
    """Track bounded rolling latency/error state without prompt or response content."""

    def __init__(
        self,
        *,
        window_size: int = 50,
        minimum_latency_samples: int = 5,
        severe_latency_multiplier: float = 2.0,
        degradation_seconds: float = 120,
    ) -> None:
        if not 5 <= window_size <= 1_000:
            raise ValueError("provider health window must be between 5 and 1000")
        if not 3 <= minimum_latency_samples <= window_size:
            raise ValueError("minimum latency samples must fit the health window")
        if severe_latency_multiplier < 1:
            raise ValueError("severe latency multiplier must be at least 1")
        if degradation_seconds <= 0:
            raise ValueError("degradation duration must be positive")
        self._window_size = window_size
        self._minimum_latency_samples = minimum_latency_samples
        self._severe_latency_multiplier = severe_latency_multiplier
        self._degradation_seconds = degradation_seconds
        self._observations: dict[str, deque[_Observation]] = defaultdict(
            lambda: deque(maxlen=self._window_size)
        )
        self._degraded_until: dict[str, float] = {}

    def record_success(self, key: str, usage: ProviderUsage | None, *, budget_ms: float) -> None:
        latency = usage.latency if usage is not None else None
        ttft = latency.first_visible_token_ms if latency is not None else None
        total = (
            latency.completion_ms
            if latency is not None and latency.completion_ms is not None
            else usage.latency_ms
            if usage is not None
            else None
        )
        self._observations[key].append(
            _Observation(success=True, ttft_ms=ttft, total_ms=total, status_code=200)
        )
        self._refresh_degradation(key, budget_ms=budget_ms)

    def record_failure(self, key: str, error: Exception, *, budget_ms: float) -> None:
        status_code = error.status_code if isinstance(error, ProviderError) else None
        self._observations[key].append(
            _Observation(success=False, ttft_ms=None, total_ms=None, status_code=status_code)
        )
        if isinstance(error, ProviderQuotaError | ProviderUnavailableError) or (
            status_code is not None and (status_code == 429 or status_code >= 500)
        ):
            self._degraded_until[key] = monotonic() + self._degradation_seconds
        self._refresh_degradation(key, budget_ms=budget_ms)

    def snapshot(self, key: str, *, budget_ms: float) -> ProviderHealthSnapshot:
        observations = tuple(self._observations.get(key, ()))
        successes = tuple(item for item in observations if item.success)
        ttft = tuple(item.ttft_ms for item in successes if item.ttft_ms is not None)
        total = tuple(item.total_ms for item in successes if item.total_ms is not None)
        recent_429 = sum(item.status_code == 429 for item in observations)
        recent_5xx = sum(
            item.status_code is not None and 500 <= item.status_code <= 599 for item in observations
        )
        degraded = monotonic() < self._degraded_until.get(key, 0)
        if len(ttft) >= self._minimum_latency_samples:
            p95 = _nearest_rank(ttft, 0.95)
            degraded = degraded or (
                p95 is not None and p95 > budget_ms * self._severe_latency_multiplier
            )
        return ProviderHealthSnapshot(
            sample_count=len(observations),
            success_count=len(successes),
            failure_count=len(observations) - len(successes),
            ttft_p50_ms=_nearest_rank(ttft, 0.50),
            ttft_p95_ms=_nearest_rank(ttft, 0.95),
            total_p50_ms=_nearest_rank(total, 0.50),
            total_p95_ms=_nearest_rank(total, 0.95),
            error_rate=(len(observations) - len(successes)) / len(observations)
            if observations
            else 0,
            recent_429_count=recent_429,
            recent_5xx_count=recent_5xx,
            quota_limited=recent_429 > 0,
            degraded=degraded,
        )

    def _refresh_degradation(self, key: str, *, budget_ms: float) -> None:
        snapshot = self.snapshot(key, budget_ms=budget_ms)
        latency_bad = (
            snapshot.ttft_p95_ms is not None
            and snapshot.success_count >= self._minimum_latency_samples
            and snapshot.ttft_p95_ms > budget_ms * self._severe_latency_multiplier
        )
        errors_bad = snapshot.sample_count >= 3 and snapshot.error_rate >= 0.5
        if latency_bad or errors_bad:
            self._degraded_until[key] = monotonic() + self._degradation_seconds


def _nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return round(ordered[rank - 1], 3)
