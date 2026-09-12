from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.wearables import (
    FakeWearableClient,
    WearableAuthorization,
    WearableCapability,
    WearableCapabilityDescriptor,
    WearableCapabilityLimits,
    WearableConnectionState,
    WearableDataClass,
    WearableDeviceDescriptor,
    WearableError,
    WearableFailureCode,
    WearableOperationRequest,
    WearablePermissionState,
    WearableTransport,
    required_data_class,
    requires_visible_indicator,
)

NOW = datetime(2026, 9, 11, 20, 0, tzinfo=UTC)


def client_and_grant(
    capability: WearableCapability,
    *,
    indicator_available: bool = True,
    expired: bool = False,
) -> tuple[FakeWearableClient, WearableAuthorization]:
    descriptor = WearableCapabilityDescriptor(
        capability=capability,
        data_class=required_data_class(capability),
        permission=WearablePermissionState.GRANTED,
        limits=WearableCapabilityLimits(
            max_payload_bytes=4096,
            max_duration_ms=2000,
            max_events=4,
        ),
        visible_indicator_required=requires_visible_indicator(capability),
    )
    device = WearableDeviceDescriptor(
        device_id="wearable:test",
        vendor="jarvis",
        model="contract-simulator",
        adapter_id="jarvis.fake",
        adapter_version="1.0.0",
        transport=WearableTransport.SIMULATOR,
        connection=WearableConnectionState.AVAILABLE,
        capabilities=(descriptor,),
        simulated=True,
    )
    grant = WearableAuthorization(
        grant_id="grant:trusted",
        host_id="host:test",
        device_id="wearable:test",
        session_id="session:test",
        capabilities=(capability,),
        media_allowed=required_data_class(capability) is WearableDataClass.MEDIA,
        health_allowed=capability is WearableCapability.HEALTH,
        issued_at=NOW - timedelta(minutes=2),
        expires_at=NOW - timedelta(minutes=1) if expired else NOW + timedelta(minutes=5),
    )
    return (
        FakeWearableClient(
            device,
            trusted_authorizations=(grant,),
            indicator_available=indicator_available,
            now=lambda: NOW,
        ),
        grant,
    )


def operation(
    capability: WearableCapability,
    *,
    request_id: str,
    session_id: str = "session:test",
) -> WearableOperationRequest:
    return WearableOperationRequest(
        request_id=request_id,
        host_id="host:test",
        device_id="wearable:test",
        session_id=session_id,
        capability=capability,
        purpose="security_test",
        data_class=required_data_class(capability),
        max_payload_bytes=1024,
        max_duration_ms=1000,
        max_events=1,
        visible_indicator_required=requires_visible_indicator(capability),
    )


@pytest.mark.asyncio
async def test_caller_constructed_grant_is_not_trusted() -> None:
    client, trusted = client_and_grant(WearableCapability.INPUT)
    forged = trusted.model_copy(update={"grant_id": "grant:forged"})
    with pytest.raises(WearableError) as error:
        await client.execute(
            operation(WearableCapability.INPUT, request_id="request:forged"), forged
        )
    assert error.value.code is WearableFailureCode.AUTHORIZATION_DENIED


@pytest.mark.asyncio
async def test_exact_session_and_capability_binding_is_enforced() -> None:
    client, grant = client_and_grant(WearableCapability.INPUT)
    with pytest.raises(WearableError) as session_error:
        await client.execute(
            operation(
                WearableCapability.INPUT,
                request_id="request:wrong-session",
                session_id="session:other",
            ),
            grant,
        )
    assert session_error.value.code is WearableFailureCode.AUTHORIZATION_DENIED

    client, grant = client_and_grant(WearableCapability.INPUT)
    client.remove_capability(WearableCapability.INPUT)
    with pytest.raises(WearableError) as capability_error:
        await client.execute(
            operation(WearableCapability.INPUT, request_id="request:removed"), grant
        )
    assert capability_error.value.code is WearableFailureCode.UNSUPPORTED_CAPABILITY


@pytest.mark.asyncio
async def test_expired_and_revoked_grants_fail_closed() -> None:
    expired_client, expired_grant = client_and_grant(WearableCapability.INPUT, expired=True)
    with pytest.raises(WearableError) as expired:
        await expired_client.execute(
            operation(WearableCapability.INPUT, request_id="request:expired"), expired_grant
        )
    assert expired.value.code is WearableFailureCode.AUTHORIZATION_EXPIRED

    client, grant = client_and_grant(WearableCapability.INPUT)
    client.revoke_authorization(grant.grant_id)
    with pytest.raises(WearableError) as revoked:
        await client.execute(
            operation(WearableCapability.INPUT, request_id="request:revoked"), grant
        )
    assert revoked.value.code is WearableFailureCode.AUTHORIZATION_DENIED

    client, grant = client_and_grant(WearableCapability.INPUT)
    client.set_connection(WearableConnectionState.REVOKED)
    client.set_connection(WearableConnectionState.AVAILABLE)
    with pytest.raises(WearableError) as reconnected:
        await client.execute(
            operation(WearableCapability.INPUT, request_id="request:reconnected"), grant
        )
    assert reconnected.value.code is WearableFailureCode.AUTHORIZATION_DENIED


@pytest.mark.asyncio
async def test_camera_and_microphone_refuse_missing_indicator() -> None:
    for index, capability in enumerate(
        (WearableCapability.CAMERA, WearableCapability.AUDIO_INPUT), start=1
    ):
        client, grant = client_and_grant(capability, indicator_available=False)
        with pytest.raises(WearableError) as error:
            await client.execute(
                operation(capability, request_id=f"request:indicator:{index}"), grant
            )
        assert error.value.code is WearableFailureCode.INDICATOR_UNAVAILABLE


@pytest.mark.asyncio
async def test_request_replay_is_rejected_before_duplicate_effect() -> None:
    client, grant = client_and_grant(WearableCapability.NOTIFICATION)
    request = operation(WearableCapability.NOTIFICATION, request_id="request:once")
    await client.execute(request, grant)
    with pytest.raises(WearableError) as replay:
        await client.execute(request, grant)
    assert replay.value.code is WearableFailureCode.REPLAYED_REQUEST


@pytest.mark.asyncio
async def test_health_receipt_contains_no_health_values() -> None:
    client, grant = client_and_grant(WearableCapability.HEALTH)
    receipt = await client.execute(
        operation(WearableCapability.HEALTH, request_id="request:health"), grant
    )
    serialized = receipt.model_dump_json()
    assert receipt.cloud_disclosed is False
    assert receipt.content_retained is False
    assert "heart" not in serialized
    assert "health" in serialized


def test_operation_cannot_downgrade_media_or_health_classification() -> None:
    for capability in (
        WearableCapability.CAMERA,
        WearableCapability.AUDIO_INPUT,
        WearableCapability.HEALTH,
    ):
        with pytest.raises(ValueError, match="wrong data classification"):
            WearableOperationRequest(
                request_id=f"request:classification:{capability.value}",
                host_id="host:test",
                device_id="wearable:test",
                session_id="session:test",
                capability=capability,
                purpose="security_test",
                data_class=WearableDataClass.PRIVATE,
                max_payload_bytes=1024,
                max_duration_ms=1000,
                max_events=1,
                visible_indicator_required=requires_visible_indicator(capability),
            )
