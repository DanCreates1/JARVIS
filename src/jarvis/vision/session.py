"""Default-off foreground capture controller with technical privacy enforcement."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from contextlib import suppress
from typing import TypeVar, cast
from uuid import uuid4

from .contracts import CaptureIndicator, CaptureSettingsStore, FrameConsumer, FrameSource
from .models import (
    CaptureError,
    CaptureFailureCode,
    CaptureRequest,
    CaptureStopReason,
    CaptureSummary,
    EphemeralFrame,
    IndicatorState,
)
from .settings_store import VisionSettingsError

_T = TypeVar("_T")


class _Stopped(RuntimeError):
    pass


class CaptureController:
    """Own exactly one bounded capture; no resident listener or retained media exists."""

    def __init__(
        self,
        *,
        source: FrameSource,
        indicator: CaptureIndicator,
        settings_store: CaptureSettingsStore,
        host_enabled: bool,
        control_poll_seconds: float = 0.05,
    ) -> None:
        if not 0.01 <= control_poll_seconds <= 1:
            raise ValueError("control poll interval must be from 0.01 through 1 second")
        self.source = source
        self.indicator = indicator
        self.settings_store = settings_store
        self.host_enabled = host_enabled
        self.control_poll_seconds = control_poll_seconds
        self._session_lock = asyncio.Lock()
        self._active_stop: asyncio.Event | None = None
        self._active_reason: CaptureStopReason | None = None
        self._monitor_error: CaptureError | None = None

    @property
    def active(self) -> bool:
        return self._session_lock.locked()

    def kill(self) -> None:
        """Stop the active in-process capture; persisted disable is owned by the settings store."""
        self._active_reason = CaptureStopReason.KILL_SWITCH
        if self._active_stop is not None:
            self._active_stop.set()

    async def run(
        self,
        request: CaptureRequest,
        *,
        consumer: FrameConsumer,
        cancel: asyncio.Event | None = None,
    ) -> CaptureSummary:
        if self._session_lock.locked():
            raise CaptureError(CaptureFailureCode.BUSY, "another capture session is active")
        async with self._session_lock:
            self._require_enabled()
            session_id = f"capture-{uuid4().hex}"
            stop = asyncio.Event()
            self._active_stop = stop
            self._active_reason = None
            self._monitor_error = None
            started_ns = time.monotonic_ns()
            indicator_visible = False
            source_opened = False
            monitor = asyncio.create_task(self._monitor_control(stop, cancel))
            frames_delivered = 0
            bytes_delivered = 0
            stop_reason = CaptureStopReason.FRAME_LIMIT
            primary_error: BaseException | None = None
            try:
                state = IndicatorState(
                    session_id=session_id,
                    source=request.source,
                    source_id=request.source_id,
                    purpose=request.purpose,
                    region=request.region,
                    requested_fps=request.requested_fps,
                    max_frames=request.max_frames,
                )
                try:
                    await self.indicator.show(state)
                    indicator_visible = True
                except Exception as exc:
                    raise CaptureError(
                        CaptureFailureCode.INDICATOR_FAILED,
                        "visible capture indicator could not be activated",
                    ) from exc
                await self._await_or_stop(
                    self.source.open(request),
                    stop,
                    timeout_seconds=request.open_timeout_ms / 1_000,
                    timeout_code=CaptureFailureCode.OPEN_TIMEOUT,
                    timeout_message="capture source open timed out",
                )
                source_opened = True
                while frames_delivered < request.max_frames:
                    if self._monitor_error is not None:
                        raise self._monitor_error
                    if stop.is_set():
                        raise _Stopped
                    elapsed_ns = time.monotonic_ns() - started_ns
                    if elapsed_ns >= request.max_duration_ms * 1_000_000:
                        stop_reason = CaptureStopReason.DURATION_LIMIT
                        break
                    target_ns = started_ns + int(
                        frames_delivered * 1_000_000_000 / request.requested_fps
                    )
                    await self._wait_until(target_ns, stop)
                    if time.monotonic_ns() - started_ns >= request.max_duration_ms * 1_000_000:
                        stop_reason = CaptureStopReason.DURATION_LIMIT
                        break
                    sequence = frames_delivered + 1
                    frame = await self._await_or_stop(
                        self.source.capture(session_id=session_id, sequence=sequence),
                        stop,
                        timeout_seconds=request.frame_timeout_ms / 1_000,
                        timeout_code=CaptureFailureCode.FRAME_TIMEOUT,
                        timeout_message="frame capture timed out",
                    )
                    try:
                        self._validate_frame(frame, request, session_id, sequence)
                        await self._await_or_stop(
                            consumer(frame),
                            stop,
                            timeout_seconds=request.consumer_timeout_ms / 1_000,
                            timeout_code=CaptureFailureCode.CONSUMER_TIMEOUT,
                            timeout_message="frame consumer timed out",
                        )
                        frames_delivered += 1
                        bytes_delivered += frame.metadata.byte_count
                    finally:
                        frame.release()
                if stop.is_set():
                    raise _Stopped
            except _Stopped:
                monitor_error = self._get_monitor_error()
                if monitor_error is not None:
                    primary_error = monitor_error
                else:
                    stop_reason = self._active_reason or CaptureStopReason.CANCELLED
            except BaseException as exc:
                primary_error = exc
            finally:
                monitor.cancel()
                with suppress(asyncio.CancelledError):
                    await monitor
                close_error: BaseException | None = None
                if source_opened:
                    try:
                        await self.source.close()
                    except BaseException as exc:
                        close_error = exc
                else:
                    with suppress(Exception):
                        await self.source.close()
                indicator_error: BaseException | None = None
                if indicator_visible:
                    try:
                        await self.indicator.clear(session_id)
                    except BaseException as exc:
                        indicator_error = exc
                self._active_stop = None
                self._active_reason = None
                self._monitor_error = None
                if primary_error is None and close_error is not None:
                    primary_error = CaptureError(
                        CaptureFailureCode.SOURCE_LOST,
                        "capture source did not close cleanly",
                    )
                if primary_error is None and indicator_error is not None:
                    primary_error = CaptureError(
                        CaptureFailureCode.INDICATOR_FAILED,
                        "capture indicator did not clear cleanly",
                    )
            if primary_error is not None:
                raise primary_error
            duration_ms = (time.monotonic_ns() - started_ns) / 1_000_000
            return CaptureSummary(
                session_id=session_id,
                source=request.source,
                source_id=request.source_id,
                purpose=request.purpose,
                frames_delivered=frames_delivered,
                bytes_delivered=bytes_delivered,
                duration_ms=min(duration_ms, request.max_duration_ms + 5_000),
                stop_reason=stop_reason,
            )

    def _require_enabled(self) -> None:
        if not self.host_enabled:
            raise CaptureError(
                CaptureFailureCode.DISABLED,
                "host vision capture configuration is disabled",
            )
        try:
            enabled = self.settings_store.load_control().enabled
        except (VisionSettingsError, OSError) as exc:
            raise CaptureError(
                CaptureFailureCode.SETTINGS_INVALID,
                "vision control settings are unreadable",
            ) from exc
        if not enabled:
            raise CaptureError(
                CaptureFailureCode.DISABLED,
                "vision software kill switch is enabled",
            )

    async def _monitor_control(
        self,
        stop: asyncio.Event,
        cancel: asyncio.Event | None,
    ) -> None:
        while not stop.is_set():
            if cancel is not None and cancel.is_set():
                self._active_reason = CaptureStopReason.CANCELLED
                stop.set()
                return
            try:
                control = self.settings_store.load_control()
            except Exception:
                self._monitor_error = CaptureError(
                    CaptureFailureCode.SETTINGS_INVALID,
                    "vision control settings became unreadable",
                )
                stop.set()
                return
            if not control.enabled:
                self._active_reason = CaptureStopReason.KILL_SWITCH
                stop.set()
                return
            await asyncio.sleep(self.control_poll_seconds)

    async def _wait_until(self, target_ns: int, stop: asyncio.Event) -> None:
        remaining = (target_ns - time.monotonic_ns()) / 1_000_000_000
        if remaining <= 0:
            return
        try:
            await asyncio.wait_for(stop.wait(), remaining)
        except TimeoutError:
            return
        raise _Stopped

    async def _await_or_stop(
        self,
        awaitable: Awaitable[_T],
        stop: asyncio.Event,
        *,
        timeout_seconds: float,
        timeout_code: CaptureFailureCode,
        timeout_message: str,
    ) -> _T:
        operation: asyncio.Future[_T] = asyncio.ensure_future(awaitable)
        stop_wait = asyncio.create_task(stop.wait())
        wait_set = {
            cast(asyncio.Future[object], operation),
            cast(asyncio.Future[object], stop_wait),
        }
        done, _ = await asyncio.wait(
            wait_set,
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if operation in done:
            stop_wait.cancel()
            with suppress(asyncio.CancelledError):
                await stop_wait
            return await operation
        operation.cancel()
        with suppress(asyncio.CancelledError):
            await operation
        stop_wait.cancel()
        with suppress(asyncio.CancelledError):
            await stop_wait
        if stop.is_set():
            raise _Stopped
        raise CaptureError(timeout_code, timeout_message)

    def _get_monitor_error(self) -> CaptureError | None:
        return self._monitor_error

    @staticmethod
    def _validate_frame(
        frame: EphemeralFrame,
        request: CaptureRequest,
        session_id: str,
        sequence: int,
    ) -> None:
        metadata = frame.metadata
        if (
            metadata.session_id != session_id
            or metadata.sequence != sequence
            or metadata.source is not request.source
            or metadata.source_id != request.source_id
            or metadata.purpose is not request.purpose
            or metadata.width != request.region.width
            or metadata.height != request.region.height
            or metadata.pixel_format is not request.pixel_format
        ):
            raise CaptureError(
                CaptureFailureCode.SOURCE_MISMATCH,
                "frame metadata does not match the approved capture envelope",
            )
        age_ns = time.monotonic_ns() - metadata.monotonic_ns
        if age_ns < -50_000_000:
            raise CaptureError(
                CaptureFailureCode.MALFORMED_FRAME,
                "frame monotonic timestamp is in the future",
            )
        if age_ns > request.max_frame_age_ms * 1_000_000:
            raise CaptureError(CaptureFailureCode.FRAME_STALE, "captured frame is stale")
        try:
            if len(frame.pixels) != metadata.byte_count:
                raise ValueError
        except (RuntimeError, ValueError) as exc:
            raise CaptureError(
                CaptureFailureCode.MALFORMED_FRAME,
                "captured frame buffer is invalid",
            ) from exc
