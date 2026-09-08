"""Deterministic Phase 7A fakes for contract tests and privacy benchmarks."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from .models import CaptureControl, CaptureRequest, EphemeralFrame, FrameMetadata, IndicatorState


class FakeCaptureSettings:
    def __init__(self, *, enabled: bool = True, fail_after_loads: int | None = None) -> None:
        self.control = CaptureControl(enabled=enabled)
        self.fail_after_loads = fail_after_loads
        self.load_count = 0

    def load_control(self) -> CaptureControl:
        self.load_count += 1
        if self.fail_after_loads is not None and self.load_count > self.fail_after_loads:
            raise RuntimeError("forced settings failure")
        return self.control

    def save_control(self, control: CaptureControl) -> None:
        self.control = control


class FakeCaptureIndicator:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        fail_show: bool = False,
        fail_clear: bool = False,
    ) -> None:
        self.events = events if events is not None else []
        self.fail_show = fail_show
        self.fail_clear = fail_clear
        self.visible = False
        self.states: list[IndicatorState] = []

    async def show(self, state: IndicatorState) -> None:
        self.events.append("indicator:show")
        if self.fail_show:
            raise RuntimeError("forced indicator failure")
        self.visible = True
        self.states.append(state)

    async def clear(self, session_id: str) -> None:
        self.events.append("indicator:clear")
        if self.fail_clear:
            raise RuntimeError("forced clear failure")
        if not self.states or self.states[-1].session_id != session_id:
            raise RuntimeError("wrong indicator session")
        self.visible = False


class FakeFrameSource:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        open_delay: float = 0,
        capture_delay: float = 0,
        open_error: BaseException | None = None,
        capture_error: BaseException | None = None,
        frame_age_ms: int = 0,
        source_id_override: str | None = None,
        block_capture: asyncio.Event | None = None,
    ) -> None:
        self.events = events if events is not None else []
        self.open_delay = open_delay
        self.capture_delay = capture_delay
        self.open_error = open_error
        self.capture_error = capture_error
        self.frame_age_ms = frame_age_ms
        self.source_id_override = source_id_override
        self.block_capture = block_capture
        self.request: CaptureRequest | None = None
        self.open_count = 0
        self.capture_count = 0
        self.close_count = 0
        self.last_frame: EphemeralFrame | None = None
        self.capture_started = asyncio.Event()

    async def open(self, request: CaptureRequest) -> None:
        self.events.append("source:open")
        self.open_count += 1
        if self.open_delay:
            await asyncio.sleep(self.open_delay)
        if self.open_error is not None:
            raise self.open_error
        self.request = request

    async def capture(self, *, session_id: str, sequence: int) -> EphemeralFrame:
        self.events.append(f"source:capture:{sequence}")
        self.capture_count += 1
        self.capture_started.set()
        if self.block_capture is not None:
            await self.block_capture.wait()
        if self.capture_delay:
            await asyncio.sleep(self.capture_delay)
        if self.capture_error is not None:
            raise self.capture_error
        request = self.request
        if request is None:
            raise RuntimeError("fake source not open")
        byte_count = request.region.width * request.region.height * 3
        metadata = FrameMetadata(
            session_id=session_id,
            sequence=sequence,
            source=request.source,
            source_id=self.source_id_override or request.source_id,
            purpose=request.purpose,
            captured_at=datetime.now(UTC),
            monotonic_ns=time.monotonic_ns() - self.frame_age_ms * 1_000_000,
            width=request.region.width,
            height=request.region.height,
            byte_count=byte_count,
        )
        self.last_frame = EphemeralFrame(metadata, bytearray([7]) * byte_count)
        return self.last_frame

    async def close(self) -> None:
        self.events.append("source:close")
        self.close_count += 1
        self.request = None
