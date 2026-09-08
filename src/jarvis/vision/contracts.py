"""Provider-neutral Phase 7A capture ports."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from .models import CaptureControl, CaptureRequest, EphemeralFrame, IndicatorState

FrameConsumer = Callable[[EphemeralFrame], Awaitable[None]]


@runtime_checkable
class FrameSource(Protocol):
    async def open(self, request: CaptureRequest) -> None: ...

    async def capture(self, *, session_id: str, sequence: int) -> EphemeralFrame: ...

    async def close(self) -> None: ...


@runtime_checkable
class CaptureIndicator(Protocol):
    async def show(self, state: IndicatorState) -> None: ...

    async def clear(self, session_id: str) -> None: ...


@runtime_checkable
class CaptureSettingsStore(Protocol):
    def load_control(self) -> CaptureControl: ...

    def save_control(self, control: CaptureControl) -> None: ...
