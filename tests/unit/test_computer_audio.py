from __future__ import annotations

import os
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

import jarvis.computer.audio as audio
from jarvis.computer.audio import (
    AudioPostconditionError,
    CoreAudioError,
    CoreAudioHResultError,
    CoreAudioProtocolError,
    MasterVolumeOperation,
    MasterVolumeState,
    get_master_mute,
    get_master_volume_scalar,
    get_master_volume_state,
    set_master_mute,
    set_master_volume_scalar,
)
from jarvis.computer.windows import ElevatedProcessError, UnsupportedPlatformError

WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="requires Windows Core Audio")


@pytest.fixture(autouse=True)
def _prevent_real_elevation_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep fake mutation tests platform-neutral without a public guard bypass."""

    monkeypatch.setattr(audio._windows, "_require_non_elevated", lambda: None)


class FakeEndpoint:
    def __init__(
        self,
        *,
        scalar: float = 0.25,
        muted: bool = False,
        scalar_readback_offset: float = 0.0,
        apply_scalar: bool = True,
        apply_mute: bool = True,
        scalar_error: CoreAudioError | None = None,
        mute_error: CoreAudioError | None = None,
    ) -> None:
        self.scalar: Any = scalar
        self.muted: Any = muted
        self.scalar_readback_offset = scalar_readback_offset
        self.apply_scalar = apply_scalar
        self.apply_mute = apply_mute
        self.scalar_error = scalar_error
        self.mute_error = mute_error
        self.scalar_calls: list[tuple[float, UUID]] = []
        self.mute_calls: list[tuple[bool, UUID]] = []
        self.close_count = 0

    def get_scalar(self) -> float:
        return cast(float, self.scalar)

    def get_mute(self) -> bool:
        return cast(bool, self.muted)

    def set_scalar(self, value: float, event_context: UUID) -> None:
        self.scalar_calls.append((value, event_context))
        if self.scalar_error is not None:
            raise self.scalar_error
        if self.apply_scalar:
            self.scalar = value + self.scalar_readback_offset

    def set_mute(self, value: bool, event_context: UUID) -> None:
        self.mute_calls.append((value, event_context))
        if self.mute_error is not None:
            raise self.mute_error
        if self.apply_mute:
            self.muted = value

    def close(self) -> None:
        self.close_count += 1


def test_injected_endpoint_reads_state_and_always_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = FakeEndpoint(scalar=0.375, muted=True)
    monkeypatch.setattr(audio, "_default_endpoint_factory", lambda: endpoint)

    state = get_master_volume_state()

    assert state == MasterVolumeState(scalar=0.375, muted=True)
    assert endpoint.close_count == 1


def test_scalar_and_mute_getters_are_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    scalar_endpoint = FakeEndpoint(scalar=0.625, muted=False)
    mute_endpoint = FakeEndpoint(scalar=0.25, muted=True)

    monkeypatch.setattr(audio, "_default_endpoint_factory", lambda: scalar_endpoint)
    assert get_master_volume_scalar() == 0.625
    monkeypatch.setattr(audio, "_default_endpoint_factory", lambda: mute_endpoint)
    assert get_master_mute() is True
    assert scalar_endpoint.close_count == 1
    assert mute_endpoint.close_count == 1


def test_absolute_scalar_set_once_returns_verified_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = FakeEndpoint(scalar=0.2, muted=True)
    context = uuid4()
    guard_calls: list[None] = []
    monkeypatch.setattr(audio, "_default_endpoint_factory", lambda: endpoint)
    monkeypatch.setattr(audio._windows, "_require_non_elevated", lambda: guard_calls.append(None))

    receipt = set_master_volume_scalar(
        0.6,
        event_context=context,
    )

    assert guard_calls == [None]
    assert endpoint.scalar_calls == [(0.6, context)]
    assert endpoint.mute_calls == []
    assert endpoint.close_count == 1
    assert receipt.operation is MasterVolumeOperation.SET_SCALAR
    assert receipt.event_context == context
    assert receipt.before == MasterVolumeState(scalar=0.2, muted=True)
    assert receipt.after == MasterVolumeState(scalar=0.6, muted=True)
    assert receipt.requested_scalar == 0.6
    assert receipt.requested_muted is None


def test_absolute_mute_set_once_returns_verified_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = FakeEndpoint(scalar=0.4, muted=False)
    context = uuid4()
    monkeypatch.setattr(audio, "_default_endpoint_factory", lambda: endpoint)

    receipt = set_master_mute(
        True,
        event_context=context,
    )

    assert endpoint.mute_calls == [(True, context)]
    assert endpoint.scalar_calls == []
    assert endpoint.close_count == 1
    assert receipt.operation is MasterVolumeOperation.SET_MUTE
    assert receipt.event_context == context
    assert receipt.before == MasterVolumeState(scalar=0.4, muted=False)
    assert receipt.after == MasterVolumeState(scalar=0.4, muted=True)
    assert receipt.requested_scalar is None
    assert receipt.requested_muted is True


@pytest.mark.parametrize(
    "value",
    [-0.001, 1.001, float("nan"), float("inf"), True, "0.5", None],
)
def test_scalar_bounds_fail_before_guard_or_endpoint(
    value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    guard_calls: list[None] = []
    factory_calls: list[None] = []
    monkeypatch.setattr(audio._windows, "_require_non_elevated", lambda: guard_calls.append(None))
    monkeypatch.setattr(
        audio,
        "_default_endpoint_factory",
        lambda: (factory_calls.append(None), FakeEndpoint())[1],
    )

    with pytest.raises(ValueError, match="finite number"):
        set_master_volume_scalar(
            cast(Any, value),
            event_context=uuid4(),
        )

    assert guard_calls == []
    assert factory_calls == []


@pytest.mark.parametrize(
    "tolerance",
    [-0.001, 0.0011, float("nan"), float("inf"), True, "0.001"],
)
def test_verification_tolerance_is_narrow_and_finite(
    tolerance: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        audio._windows,
        "_require_non_elevated",
        lambda: pytest.fail("guard must not run"),
    )
    monkeypatch.setattr(
        audio,
        "_default_endpoint_factory",
        lambda: pytest.fail("factory must not run"),
    )
    with pytest.raises(ValueError, match="tolerance"):
        set_master_volume_scalar(
            0.5,
            event_context=uuid4(),
            verification_tolerance=cast(Any, tolerance),
        )


@pytest.mark.parametrize("context", [UUID(int=0), "not-a-uuid", None])
def test_event_context_must_be_non_null_uuid(
    context: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        audio._windows,
        "_require_non_elevated",
        lambda: pytest.fail("guard must not run"),
    )
    monkeypatch.setattr(
        audio,
        "_default_endpoint_factory",
        lambda: pytest.fail("factory must not run"),
    )
    with pytest.raises(ValueError, match="non-null UUID"):
        set_master_volume_scalar(
            0.5,
            event_context=cast(Any, context),
        )


@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_mute_requires_an_actual_boolean(value: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        audio._windows,
        "_require_non_elevated",
        lambda: pytest.fail("guard must not run"),
    )
    monkeypatch.setattr(
        audio,
        "_default_endpoint_factory",
        lambda: pytest.fail("factory must not run"),
    )
    with pytest.raises(ValueError, match="boolean"):
        set_master_mute(
            cast(Any, value),
            event_context=uuid4(),
        )


def test_mutation_fails_closed_when_process_is_elevated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory_calls: list[None] = []

    def reject_elevation() -> None:
        raise ElevatedProcessError("elevated process refused")

    monkeypatch.setattr(audio._windows, "_require_non_elevated", reject_elevation)
    monkeypatch.setattr(
        audio,
        "_default_endpoint_factory",
        lambda: (factory_calls.append(None), FakeEndpoint())[1],
    )
    with pytest.raises(ElevatedProcessError, match="elevated"):
        set_master_volume_scalar(
            0.5,
            event_context=uuid4(),
        )

    assert factory_calls == []


def test_scalar_readback_mismatch_raises_typed_postcondition_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = FakeEndpoint(scalar=0.2, muted=False, apply_scalar=False)
    context = uuid4()
    monkeypatch.setattr(audio, "_default_endpoint_factory", lambda: endpoint)

    with pytest.raises(AudioPostconditionError) as captured:
        set_master_volume_scalar(
            0.8,
            event_context=context,
        )

    error = captured.value
    assert error.operation is MasterVolumeOperation.SET_SCALAR
    assert error.event_context == context
    assert error.before == MasterVolumeState(scalar=0.2, muted=False)
    assert error.observed == MasterVolumeState(scalar=0.2, muted=False)
    assert error.requested_scalar == 0.8
    assert endpoint.scalar_calls == [(0.8, context)]
    assert endpoint.close_count == 1


def test_mute_readback_mismatch_raises_typed_postcondition_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = FakeEndpoint(scalar=0.2, muted=False, apply_mute=False)
    context = uuid4()
    monkeypatch.setattr(audio, "_default_endpoint_factory", lambda: endpoint)

    with pytest.raises(AudioPostconditionError) as captured:
        set_master_mute(
            True,
            event_context=context,
        )

    error = captured.value
    assert error.operation is MasterVolumeOperation.SET_MUTE
    assert error.requested_muted is True
    assert endpoint.mute_calls == [(True, context)]
    assert endpoint.close_count == 1


def test_scalar_readback_within_explicit_tolerance_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = FakeEndpoint(scalar=0.2, scalar_readback_offset=0.0005)
    monkeypatch.setattr(audio, "_default_endpoint_factory", lambda: endpoint)

    receipt = set_master_volume_scalar(
        0.5,
        event_context=uuid4(),
        verification_tolerance=0.001,
    )

    assert receipt.after.scalar == pytest.approx(0.5005)
    assert len(endpoint.scalar_calls) == 1


@pytest.mark.parametrize(
    ("scalar", "muted"),
    [(1.1, False), (float("nan"), False), (0.5, 1)],
)
def test_malformed_endpoint_state_fails_closed_and_closes(
    scalar: float, muted: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    endpoint = FakeEndpoint(scalar=scalar, muted=cast(Any, muted))
    monkeypatch.setattr(audio, "_default_endpoint_factory", lambda: endpoint)

    with pytest.raises(CoreAudioProtocolError, match="invalid state"):
        get_master_volume_state()

    assert endpoint.close_count == 1


def test_setter_error_is_not_retried_and_endpoint_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = FakeEndpoint(scalar_error=CoreAudioError("injected failure"))
    context = uuid4()
    monkeypatch.setattr(audio, "_default_endpoint_factory", lambda: endpoint)

    with pytest.raises(CoreAudioError, match="injected failure"):
        set_master_volume_scalar(
            0.5,
            event_context=context,
        )

    assert endpoint.scalar_calls == [(0.5, context)]
    assert endpoint.close_count == 1


def test_non_windows_default_adapter_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audio, "_IS_WINDOWS", False)
    monkeypatch.setattr(audio, "_ole32", None)

    with pytest.raises(UnsupportedPlatformError, match="unavailable"):
        get_master_volume_state()


@WINDOWS_ONLY
def test_real_default_endpoint_read_is_bounded_and_read_only() -> None:
    try:
        state = get_master_volume_state()
    except CoreAudioHResultError as exc:
        if exc.hresult == 0x80070490:
            pytest.skip("Windows host has no default audio endpoint")
        raise

    assert 0.0 <= state.scalar <= 1.0
    assert type(state.muted) is bool
