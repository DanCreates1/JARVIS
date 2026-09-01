"""Composition root for default-disabled Phase 3 computer authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from jarvis.broker import LocalActionBroker
from jarvis.config import Settings
from jarvis.permissions import (
    ActionCoordinator,
    ActorContext,
    InteractionInterface,
    PermissionEngine,
    SQLiteActionStore,
    sha256_fingerprint,
)

from .config import ComputerAccessConfigStore, ComputerAccessPolicy
from .identity import IdentityKeyStore, LocalActorFactory
from .registry import ComputerActionRegistry, build_computer_registry


class ComputerAccessDisabledError(RuntimeError):
    """Controlled access is not enabled by both trusted configuration gates."""


@dataclass(slots=True)
class ComputerRuntimeComponents:
    settings: Settings
    policy: ComputerAccessPolicy
    registry: ComputerActionRegistry
    store: SQLiteActionStore
    actor: ActorContext
    broker: LocalActionBroker
    coordinator: ActionCoordinator

    async def close(self) -> None:
        await self.store.close()

    async def __aenter__(self) -> ComputerRuntimeComponents:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()


async def build_computer_runtime(
    settings: Settings,
    *,
    interface: InteractionInterface = InteractionInterface.LOCAL_CLI,
) -> ComputerRuntimeComponents:
    """Build exact local authority only after both host-owned gates pass."""
    if not settings.computer_access_enabled:
        raise ComputerAccessDisabledError("computer access master switch is disabled")
    policy = ComputerAccessConfigStore(settings.data_dir).load()
    if not policy.enabled:
        raise ComputerAccessDisabledError("computer access policy file is disabled")

    registry = build_computer_registry(policy)
    policy_fingerprint = sha256_fingerprint(policy.model_dump(mode="json"))
    policy_store = ComputerAccessConfigStore(settings.data_dir)

    def authority_guard(_grant: object) -> bool:
        try:
            current = policy_store.load()
        except (OSError, ValueError):
            return False
        return (
            current.enabled
            and sha256_fingerprint(current.model_dump(mode="json")) == policy_fingerprint
        )

    actor = LocalActorFactory(IdentityKeyStore(settings.data_dir)).create(
        interface=interface,
        capabilities=registry.required_capabilities,
    )
    store = SQLiteActionStore(settings.database_path)
    await store.initialize()
    try:
        engine = PermissionEngine(policy_version=policy.policy_version)
        broker = LocalActionBroker(
            registry.actions,
            state_store=store,
            audit_store=store,
            policy_version=policy.policy_version,
            authority_guard=authority_guard,
        )
        coordinator = ActionCoordinator(
            store=store,
            permission_engine=engine,
            broker=broker,
            action_ttl=timedelta(
                seconds=min(
                    15 * 60,
                    policy.approval_ttl_seconds + policy.grant_ttl_seconds + 15,
                )
            ),
            approval_ttl=timedelta(seconds=policy.approval_ttl_seconds),
            grant_ttl=timedelta(seconds=policy.grant_ttl_seconds),
        )
    except BaseException:
        await store.close()
        raise
    return ComputerRuntimeComponents(
        settings=settings,
        policy=policy,
        registry=registry,
        store=store,
        actor=actor,
        broker=broker,
        coordinator=coordinator,
    )
