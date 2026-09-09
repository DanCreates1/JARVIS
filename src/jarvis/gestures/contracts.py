"""Provider-neutral ports for local Phase 7B landmark detection."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from jarvis.vision.models import EphemeralFrame

from .models import GestureObservation, LandmarkFrame

GestureSink = Callable[[GestureObservation], Awaitable[None]]


@runtime_checkable
class HandLandmarkDetector(Protocol):
    async def detect(self, frame: EphemeralFrame) -> LandmarkFrame: ...

    async def close(self) -> None: ...
