"""Default-off scoped PWA adapter for generic Phase 11C ownership state."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from jarvis.remote import REQUEST_AUDIENCE, RemoteIdentityContext, RemoteScope

from .device_models import CandidateOwnership, VisibleProactivityState
from .device_store import DeviceOwnershipDeniedError, SQLiteProactivityDeviceStore


class PWAProactivityAdapter:
    """Expose only content-free coordination under existing Phase 8 identity."""

    def __init__(
        self,
        store: SQLiteProactivityDeviceStore,
        *,
        configured_enabled: bool = False,
        policy_enabled: bool = False,
        enabled_features: frozenset[str] = frozenset(),
        lease_seconds: int = 60,
    ) -> None:
        if not 30 <= lease_seconds <= 300:
            raise ValueError("device ownership lease must be 30 through 300 seconds")
        self._store = store
        self._configured_enabled = configured_enabled
        self._policy_enabled = policy_enabled
        self._enabled_features = enabled_features
        self._lease_seconds = lease_seconds

    async def list_visible(
        self, *, context: RemoteIdentityContext, limit: int = 100, now: datetime | None = None
    ) -> Sequence[VisibleProactivityState]:
        self._require(context, manage=False, now=now)
        return await self._store.list_visible(
            host_id=context.host_id,
            device_id=context.device_id,
            limit=limit,
            now=now,
            allowed_features=self._enabled_features,
        )

    async def claim(
        self,
        *,
        context: RemoteIdentityContext,
        candidate_id: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> CandidateOwnership:
        self._require(context, manage=True, now=now)
        return await self._store.claim(
            host_id=context.host_id,
            device_id=context.device_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            lease_seconds=self._lease_seconds,
            now=now,
            allowed_features=self._enabled_features,
        )

    async def renew(
        self,
        *,
        context: RemoteIdentityContext,
        candidate_id: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> CandidateOwnership:
        self._require(context, manage=True, now=now)
        return await self._store.renew(
            host_id=context.host_id,
            device_id=context.device_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            lease_seconds=self._lease_seconds,
            now=now,
            allowed_features=self._enabled_features,
        )

    async def release(
        self,
        *,
        context: RemoteIdentityContext,
        candidate_id: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> CandidateOwnership:
        self._require(context, manage=True, now=now)
        return await self._store.release(
            host_id=context.host_id,
            device_id=context.device_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            now=now,
            allowed_features=self._enabled_features,
        )

    async def handoff(
        self,
        *,
        context: RemoteIdentityContext,
        candidate_id: str,
        target_device_id: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> CandidateOwnership:
        self._require(context, manage=True, now=now)
        return await self._store.handoff(
            host_id=context.host_id,
            device_id=context.device_id,
            target_device_id=target_device_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            lease_seconds=self._lease_seconds,
            now=now,
            allowed_features=self._enabled_features,
        )

    def _require(
        self, context: RemoteIdentityContext, *, manage: bool, now: datetime | None
    ) -> None:
        if not self._configured_enabled or not self._policy_enabled:
            raise DeviceOwnershipDeniedError("PWA proactivity adapter is disabled")
        if context.audience != REQUEST_AUDIENCE:
            raise DeviceOwnershipDeniedError("PWA proactivity audience denied")
        timestamp = now or datetime.now(UTC)
        if context.expires_at is not None and context.expires_at <= timestamp:
            raise DeviceOwnershipDeniedError("PWA proactivity session expired")
        required = {RemoteScope.CLIENT_PROACTIVITY_READ}
        if manage:
            required.add(RemoteScope.CLIENT_PROACTIVITY_MANAGE)
        if not required.issubset(context.scopes):
            raise DeviceOwnershipDeniedError("PWA proactivity scope denied")
