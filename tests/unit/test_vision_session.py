from __future__ import annotations

import asyncio

import pytest

from jarvis.vision.fakes import FakeCaptureIndicator, FakeCaptureSettings, FakeFrameSource
from jarvis.vision.models import (
    CaptureControl,
    CaptureError,
    CaptureFailureCode,
    CapturePurpose,
    CaptureRegion,
    CaptureRequest,
    CaptureSource,
    CaptureStopReason,
)
from jarvis.vision.session import CaptureController


def _request(**updates: object) -> CaptureRequest:
    values: dict[str, object] = {
        "source": CaptureSource.CAMERA,
        "source_id": "camera:0",
        "purpose": CapturePurpose.DIAGNOSTIC,
        "region": CaptureRegion(x=0, y=0, width=2, height=2),
        "requested_fps": 15,
        "max_frames": 1,
        "max_duration_ms": 1_000,
    }
    values.update(updates)
    return CaptureRequest.model_validate(values)


def _controller(
    source: FakeFrameSource,
    *,
    indicator: FakeCaptureIndicator | None = None,
    settings: FakeCaptureSettings | None = None,
    host_enabled: bool = True,
) -> CaptureController:
    return CaptureController(
        source=source,
        indicator=indicator or FakeCaptureIndicator(),
        settings_store=settings or FakeCaptureSettings(),
        host_enabled=host_enabled,
        control_poll_seconds=0.01,
    )


async def _discard(_frame) -> None:  # type: ignore[no-untyped-def]
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize("host_enabled,user_enabled", [(False, True), (True, False)])
async def test_dual_default_off_gate_opens_nothing(host_enabled: bool, user_enabled: bool) -> None:
    source = FakeFrameSource()
    indicator = FakeCaptureIndicator()
    controller = _controller(
        source,
        indicator=indicator,
        settings=FakeCaptureSettings(enabled=user_enabled),
        host_enabled=host_enabled,
    )

    with pytest.raises(CaptureError) as captured:
        await controller.run(_request(), consumer=_discard)

    assert captured.value.code is CaptureFailureCode.DISABLED
    assert source.open_count == 0
    assert indicator.states == []


@pytest.mark.asyncio
async def test_indicator_precedes_open_and_source_closes_before_indicator_clear() -> None:
    events: list[str] = []
    source = FakeFrameSource(events=events)
    indicator = FakeCaptureIndicator(events=events)
    observed: list[bytes] = []

    async def consume(frame) -> None:  # type: ignore[no-untyped-def]
        observed.append(bytes(frame.pixels))

    result = await _controller(source, indicator=indicator).run(_request(), consumer=consume)

    assert result.frames_delivered == 1
    assert result.stop_reason is CaptureStopReason.FRAME_LIMIT
    assert observed == [bytes([7]) * 12]
    assert events == [
        "indicator:show",
        "source:open",
        "source:capture:1",
        "source:close",
        "indicator:clear",
    ]
    assert source.last_frame is not None and source.last_frame.released


@pytest.mark.asyncio
async def test_indicator_failure_causes_zero_source_open() -> None:
    source = FakeFrameSource()
    indicator = FakeCaptureIndicator(fail_show=True)

    with pytest.raises(CaptureError) as captured:
        await _controller(source, indicator=indicator).run(_request(), consumer=_discard)

    assert captured.value.code is CaptureFailureCode.INDICATOR_FAILED
    assert source.open_count == 0


@pytest.mark.asyncio
async def test_stale_or_mismatched_frame_never_reaches_consumer() -> None:
    delivered = 0

    async def consume(_frame) -> None:  # type: ignore[no-untyped-def]
        nonlocal delivered
        delivered += 1

    stale = FakeFrameSource(frame_age_ms=500)
    with pytest.raises(CaptureError) as captured:
        await _controller(stale).run(_request(max_frame_age_ms=50), consumer=consume)
    assert captured.value.code is CaptureFailureCode.FRAME_STALE
    assert stale.last_frame is not None and stale.last_frame.released

    mismatch = FakeFrameSource(source_id_override="camera:1")
    with pytest.raises(CaptureError) as captured:
        await _controller(mismatch).run(_request(), consumer=consume)
    assert captured.value.code is CaptureFailureCode.SOURCE_MISMATCH
    assert mismatch.last_frame is not None and mismatch.last_frame.released
    assert delivered == 0


@pytest.mark.asyncio
async def test_open_frame_and_consumer_timeouts_fail_closed() -> None:
    open_source = FakeFrameSource(open_delay=0.2)
    with pytest.raises(CaptureError) as captured:
        await _controller(open_source).run(_request(open_timeout_ms=100), consumer=_discard)
    assert captured.value.code is CaptureFailureCode.OPEN_TIMEOUT
    assert open_source.close_count == 1

    frame_source = FakeFrameSource(capture_delay=0.2)
    with pytest.raises(CaptureError) as captured:
        await _controller(frame_source).run(_request(frame_timeout_ms=50), consumer=_discard)
    assert captured.value.code is CaptureFailureCode.FRAME_TIMEOUT
    assert frame_source.close_count == 1

    consumer_source = FakeFrameSource()

    async def slow_consumer(_frame) -> None:  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.2)

    with pytest.raises(CaptureError) as captured:
        await _controller(consumer_source).run(
            _request(consumer_timeout_ms=50), consumer=slow_consumer
        )
    assert captured.value.code is CaptureFailureCode.CONSUMER_TIMEOUT
    assert consumer_source.last_frame is not None and consumer_source.last_frame.released


@pytest.mark.asyncio
async def test_kill_cancel_and_persisted_disable_stop_blocked_capture() -> None:
    async def run_case(kind: str) -> CaptureStopReason:
        blocker = asyncio.Event()
        source = FakeFrameSource(block_capture=blocker)
        settings = FakeCaptureSettings()
        controller = _controller(source, settings=settings)
        cancel = asyncio.Event()
        task = asyncio.create_task(controller.run(_request(), consumer=_discard, cancel=cancel))
        await source.capture_started.wait()
        if kind == "kill":
            controller.kill()
        elif kind == "cancel":
            cancel.set()
        else:
            settings.save_control(CaptureControl(enabled=False))
        result = await asyncio.wait_for(task, 0.5)
        assert source.close_count == 1
        return result.stop_reason

    assert await run_case("kill") is CaptureStopReason.KILL_SWITCH
    assert await run_case("cancel") is CaptureStopReason.CANCELLED
    assert await run_case("persisted") is CaptureStopReason.KILL_SWITCH


@pytest.mark.asyncio
async def test_source_switch_is_rejected_while_session_active() -> None:
    blocker = asyncio.Event()
    source = FakeFrameSource(block_capture=blocker)
    controller = _controller(source)
    first = asyncio.create_task(controller.run(_request(), consumer=_discard))
    await source.capture_started.wait()

    with pytest.raises(CaptureError) as captured:
        await controller.run(
            _request(
                source=CaptureSource.SCREEN,
                source_id="screen:desktop",
                purpose=CapturePurpose.SCREEN_ANALYSIS,
            ),
            consumer=_discard,
        )
    assert captured.value.code is CaptureFailureCode.BUSY
    assert source.open_count == 1
    controller.kill()
    await first


@pytest.mark.asyncio
async def test_frame_rate_and_duration_caps_are_enforced() -> None:
    source = FakeFrameSource()
    started = asyncio.get_running_loop().time()
    result = await _controller(source).run(
        _request(max_frames=3, requested_fps=15), consumer=_discard
    )
    elapsed = asyncio.get_running_loop().time() - started
    assert result.frames_delivered == 3
    assert elapsed >= 0.12

    duration_source = FakeFrameSource()
    result = await _controller(duration_source).run(
        _request(max_frames=300, requested_fps=15, max_duration_ms=100),
        consumer=_discard,
    )
    assert result.stop_reason is CaptureStopReason.DURATION_LIMIT
    assert result.frames_delivered <= 2


@pytest.mark.asyncio
async def test_settings_corruption_during_capture_fails_closed() -> None:
    blocker = asyncio.Event()
    source = FakeFrameSource(block_capture=blocker)
    settings = FakeCaptureSettings(fail_after_loads=2)

    with pytest.raises(CaptureError) as captured:
        await _controller(source, settings=settings).run(_request(), consumer=_discard)

    assert captured.value.code is CaptureFailureCode.SETTINGS_INVALID
    assert source.close_count == 1


@pytest.mark.asyncio
async def test_source_loss_and_indicator_clear_failure_are_classified() -> None:
    lost = FakeFrameSource(capture_error=CaptureError(CaptureFailureCode.SOURCE_LOST, "lost"))
    with pytest.raises(CaptureError) as captured:
        await _controller(lost).run(_request(), consumer=_discard)
    assert captured.value.code is CaptureFailureCode.SOURCE_LOST

    source = FakeFrameSource()
    indicator = FakeCaptureIndicator(fail_clear=True)
    with pytest.raises(CaptureError) as captured:
        await _controller(source, indicator=indicator).run(_request(), consumer=_discard)
    assert captured.value.code is CaptureFailureCode.INDICATOR_FAILED
    assert source.close_count == 1
