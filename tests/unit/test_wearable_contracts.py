from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jarvis.wearables import (
    FakeWearableClient,
    WearableAuthorization,
    WearableCapability,
    WearableCapabilityDescriptor,
    WearableCapabilityLimits,
    WearableClient,
    WearableConnectionState,
    WearableDataClass,
    WearableDeviceDescriptor,
    WearableError,
    WearableFailureCode,
    WearableNegotiationRequest,
    WearableOperationRequest,
    WearablePermissionState,
    WearableTransport,
    required_data_class,
    requires_visible_indicator,
)

NOW = datetime(2026, 9, 11, 20, 0, tzinfo=UTC)


def capability(
    name: WearableCapability,
    *,
    permission: WearablePermissionState = WearablePermissionState.GRANTED,
) -> WearableCapabilityDescriptor:
    return WearableCapabilityDescriptor(
        capability=name,
        data_class=required_data_class(name),
        permission=permission,
        limits=WearableCapabilityLimits(
            max_payload_bytes=4096,
            max_duration_ms=2000,
            max_events=4,
        ),
        visible_indicator_required=requires_visible_indicator(name),
    )


def device(*names: WearableCapability) -> WearableDeviceDescriptor:
    selected = names or tuple(WearableCapability)
    return WearableDeviceDescriptor(
        device_id="wearable:test",
        vendor="jarvis",
        model="contract-simulator",
        adapter_id="jarvis.fake",
        adapter_version="1.0.0",
        transport=WearableTransport.SIMULATOR,
        connection=WearableConnectionState.AVAILABLE,
        capabilities=tuple(capability(name) for name in selected),
        simulated=True,
    )


def authorization(
    *names: WearableCapability,
    session_id: str = "session:test",
    expires_at: datetime | None = None,
) -> WearableAuthorization:
    selected = names or (WearableCapability.INPUT,)
    return WearableAuthorization(
        grant_id="grant:test",
        host_id="host:test",
        device_id="wearable:test",
        session_id=session_id,
        capabilities=selected,
        media_allowed=any(
            required_data_class(item) is WearableDataClass.MEDIA for item in selected
        ),
        health_allowed=WearableCapability.HEALTH in selected,
        issued_at=NOW,
        expires_at=expires_at or datetime(2099, 1, 1, tzinfo=UTC),
    )


def operation(
    name: WearableCapability,
    *,
    request_id: str = "operation-request:test",
    session_id: str = "session:test",
    max_payload_bytes: int = 1024,
) -> WearableOperationRequest:
    return WearableOperationRequest(
        request_id=request_id,
        host_id="host:test",
        device_id="wearable:test",
        session_id=session_id,
        capability=name,
        purpose="contract_test",
        data_class=required_data_class(name),
        max_payload_bytes=max_payload_bytes,
        max_duration_ms=1000,
        max_events=1,
        visible_indicator_required=requires_visible_indicator(name),
    )


def negotiation(**updates: object) -> WearableNegotiationRequest:
    values: dict[str, object] = {
        "request_id": "negotiation:test",
        "host_id": "host:test",
        "device_id": "wearable:test",
        "session_id": "session:test",
        "required_capabilities": (WearableCapability.INPUT,),
        "optional_capabilities": (WearableCapability.DISPLAY,),
    }
    values.update(updates)
    return WearableNegotiationRequest(**values)


def test_device_requires_unique_capabilities_and_simulator_transport() -> None:
    duplicate = capability(WearableCapability.INPUT)
    with pytest.raises(ValidationError, match="must be unique"):
        WearableDeviceDescriptor(
            device_id="wearable:test",
            vendor="jarvis",
            model="simulator",
            adapter_id="jarvis.fake",
            adapter_version="1.0.0",
            transport=WearableTransport.SIMULATOR,
            connection=WearableConnectionState.AVAILABLE,
            capabilities=(duplicate, duplicate),
            simulated=True,
        )
    with pytest.raises(ValidationError, match="simulated devices"):
        WearableDeviceDescriptor.model_validate(
            {**device().model_dump(), "transport": WearableTransport.DIRECT}
        )


@pytest.mark.parametrize("name", list(WearableCapability))
def test_capability_classification_and_indicator_are_fixed(name: WearableCapability) -> None:
    expected_class = required_data_class(name)
    expected_indicator = requires_visible_indicator(name)
    assert capability(name).data_class is expected_class
    assert capability(name).visible_indicator_required is expected_indicator
    with pytest.raises(ValidationError, match="wrong data classification"):
        WearableCapabilityDescriptor(
            capability=name,
            data_class=(
                WearableDataClass.HEALTH
                if expected_class is not WearableDataClass.HEALTH
                else WearableDataClass.PRIVATE
            ),
            permission=WearablePermissionState.GRANTED,
            limits=capability(name).limits,
            visible_indicator_required=expected_indicator,
        )


def test_media_and_health_authorization_must_be_explicit() -> None:
    with pytest.raises(ValidationError, match="media capability"):
        WearableAuthorization(
            grant_id="grant:media",
            host_id="host:test",
            device_id="wearable:test",
            session_id="session:test",
            capabilities=(WearableCapability.CAMERA,),
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=1),
        )
    with pytest.raises(ValidationError, match="health capability"):
        WearableAuthorization(
            grant_id="grant:health",
            host_id="host:test",
            device_id="wearable:test",
            session_id="session:test",
            capabilities=(WearableCapability.HEALTH,),
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=1),
        )


@pytest.mark.asyncio
async def test_negotiation_reports_capabilities_but_grants_no_authority() -> None:
    client = FakeWearableClient(device(WearableCapability.INPUT, WearableCapability.DISPLAY))
    assert isinstance(client, WearableClient)
    result = await client.negotiate(negotiation())
    assert result.authorization_granted is False
    assert tuple(item.capability for item in result.available_capabilities) == (
        WearableCapability.DISPLAY,
        WearableCapability.INPUT,
    )


@pytest.mark.asyncio
async def test_negotiation_fails_for_missing_required_or_newer_protocol() -> None:
    client = FakeWearableClient(device(WearableCapability.INPUT))
    with pytest.raises(WearableError) as missing:
        await client.negotiate(
            negotiation(
                request_id="negotiation:missing",
                required_capabilities=(WearableCapability.CAMERA,),
                optional_capabilities=(),
            )
        )
    assert missing.value.code is WearableFailureCode.UNSUPPORTED_CAPABILITY
    with pytest.raises(WearableError) as version:
        await client.negotiate(negotiation(request_id="negotiation:version", protocol_minor=1))
    assert version.value.code is WearableFailureCode.INCOMPATIBLE_VERSION


@pytest.mark.asyncio
async def test_valid_operation_returns_content_free_ephemeral_receipt() -> None:
    grant = authorization(WearableCapability.CAMERA)
    client = FakeWearableClient(device(WearableCapability.CAMERA), trusted_authorizations=(grant,))
    receipt = await client.execute(operation(WearableCapability.CAMERA), grant)
    assert receipt.indicator_observed is True
    assert receipt.content_retained is False
    assert receipt.cloud_disclosed is False
    assert receipt.bytes_processed == 1024
    with pytest.raises(ValidationError, match="observed indicator"):
        receipt.__class__.model_validate(
            {**receipt.model_dump(mode="python"), "indicator_observed": False}
        )


@pytest.mark.asyncio
async def test_operation_denies_permission_and_excess_limits() -> None:
    grant = authorization(WearableCapability.INPUT)
    denied_device = device(WearableCapability.INPUT).model_copy(
        update={
            "capabilities": (
                capability(
                    WearableCapability.INPUT,
                    permission=WearablePermissionState.DENIED,
                ),
            )
        }
    )
    denied_client = FakeWearableClient(denied_device, trusted_authorizations=(grant,))
    with pytest.raises(WearableError) as denied:
        await denied_client.execute(operation(WearableCapability.INPUT), grant)
    assert denied.value.code is WearableFailureCode.PERMISSION_DENIED

    bounded_client = FakeWearableClient(
        device(WearableCapability.INPUT), trusted_authorizations=(grant,)
    )
    with pytest.raises(WearableError) as bounded:
        await bounded_client.execute(
            operation(WearableCapability.INPUT, max_payload_bytes=4097), grant
        )
    assert bounded.value.code is WearableFailureCode.LIMIT_EXCEEDED


@pytest.mark.asyncio
async def test_cancel_disconnect_close_and_adapter_removal_fail_closed() -> None:
    grant = authorization(WearableCapability.INPUT)
    client = FakeWearableClient(device(WearableCapability.INPUT), trusted_authorizations=(grant,))
    cancel = asyncio.Event()
    cancel.set()
    with pytest.raises(WearableError) as cancelled:
        await client.execute(operation(WearableCapability.INPUT), grant, cancel=cancel)
    assert cancelled.value.code is WearableFailureCode.CANCELLED

    client.set_connection(WearableConnectionState.DISCONNECTED)
    with pytest.raises(WearableError) as disconnected:
        await client.negotiate(negotiation(request_id="negotiation:disconnected"))
    assert disconnected.value.code is WearableFailureCode.DEVICE_UNAVAILABLE

    client.set_connection(WearableConnectionState.AVAILABLE)
    client.remove_capability(WearableCapability.INPUT)
    with pytest.raises(WearableError) as removed:
        await client.negotiate(negotiation(request_id="negotiation:removed"))
    assert removed.value.code is WearableFailureCode.UNSUPPORTED_CAPABILITY

    await client.close()
    assert (await client.describe()).connection is WearableConnectionState.DISCONNECTED
