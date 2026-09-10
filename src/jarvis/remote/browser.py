"""Phase 8B browser-origin and bounded request-rate policy."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from threading import Lock


class BrowserOriginError(ValueError):
    """An Origin header did not exactly match configured browser trust."""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


@dataclass(slots=True)
class _Window:
    started_at: float
    count: int
    last_seen_at: float


class FixedWindowRateLimiter:
    """Process-local abuse brake with deterministic ceilings and bounded key state."""

    def __init__(
        self,
        *,
        max_entries: int = 4_096,
        window_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries < 1:
            raise ValueError("rate limiter entry ceiling must be positive")
        if window_seconds < 1:
            raise ValueError("rate limiter window must be positive")
        self._max_entries = max_entries
        self._window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[str, _Window] = {}
        self._lock = Lock()

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._windows)

    def check(self, key: str, *, limit: int) -> RateLimitDecision:
        if not key or limit < 1:
            raise ValueError("rate limit key and positive limit are required")
        now = self._clock()
        with self._lock:
            current = self._windows.get(key)
            if current is None or now - current.started_at >= self._window_seconds:
                self._prune(now)
                if len(self._windows) >= self._max_entries:
                    oldest = min(self._windows, key=lambda item: self._windows[item].last_seen_at)
                    del self._windows[oldest]
                self._windows[key] = _Window(now, 1, now)
                return RateLimitDecision(True, 0)
            current.last_seen_at = now
            if current.count >= limit:
                remaining = max(1, int(self._window_seconds - (now - current.started_at) + 0.999))
                return RateLimitDecision(False, remaining)
            current.count += 1
            return RateLimitDecision(True, 0)

    def _prune(self, now: float) -> None:
        stale = [
            key
            for key, window in self._windows.items()
            if now - window.started_at >= self._window_seconds
        ]
        for key in stale:
            del self._windows[key]


class BrowserOriginPolicy:
    """Exact allowlist. Never reflects an untrusted Origin value."""

    def __init__(self, trusted_origins: Iterable[str]) -> None:
        self._trusted = frozenset(trusted_origins)

    def require(self, values: tuple[str, ...]) -> str:
        if len(values) != 1:
            raise BrowserOriginError("exactly one browser origin is required")
        origin = values[0]
        if origin == "null" or origin not in self._trusted:
            raise BrowserOriginError("browser origin is not trusted")
        return origin

    def optional(self, values: tuple[str, ...]) -> str | None:
        if not values:
            return None
        return self.require(values)
