"""Provider-neutral Phase 10 wearable port."""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from .models import (
    WearableAuthorization,
    WearableDeviceDescriptor,
    WearableNegotiationRequest,
    WearableNegotiationResult,
    WearableOperationReceipt,
    WearableOperationRequest,
)


@runtime_checkable
class WearableClient(Protocol):
    async def describe(self) -> WearableDeviceDescriptor: ...

    async def negotiate(
        self,
        request: WearableNegotiationRequest,
        *,
        cancel: asyncio.Event | None = None,
    ) -> WearableNegotiationResult: ...

    async def execute(
        self,
        request: WearableOperationRequest,
        authorization: WearableAuthorization,
        *,
        cancel: asyncio.Event | None = None,
    ) -> WearableOperationReceipt: ...

    async def close(self) -> None: ...
