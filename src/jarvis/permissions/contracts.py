"""Ports separating policy, approval, durable state, audit, and OS execution."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from .models import (
    ActionAuditEvent,
    ActionDefinition,
    ActionEffect,
    ActorContext,
    ApprovalDecision,
    ApprovalGrant,
    ApprovalRequest,
    CanonicalAction,
    ExecutionReceipt,
    PostconditionEvidence,
    RollbackReceipt,
)


@runtime_checkable
class ActionStateStore(Protocol):
    """Durable atomic state needed for one-use grants and idempotency."""

    async def get_receipt(self, idempotency_key: str) -> ExecutionReceipt | None: ...

    async def claim_grant(self, grant: ApprovalGrant, *, claimed_at: datetime) -> bool:
        """Atomically claim an exact unused grant; return false for any replay/conflict."""
        ...

    async def complete_grant(
        self,
        grant: ApprovalGrant,
        receipt: ExecutionReceipt,
    ) -> None:
        """Atomically persist the terminal receipt for later reconciliation."""
        ...


@runtime_checkable
class ActionAuditStore(Protocol):
    async def append_action_event(self, event: ActionAuditEvent) -> None: ...


@runtime_checkable
class ActionHandler(Protocol):
    """One reviewed fixed action implementation behind broker dispatch."""

    @property
    def definition(self) -> ActionDefinition: ...

    async def execute(self, action: CanonicalAction) -> ActionEffect: ...

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence: ...

    async def rollback(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
        *,
        reason: str,
    ) -> RollbackReceipt: ...


@runtime_checkable
class TrustedApprovalSurface(Protocol):
    """Trusted UI port. Model/chat content never implements or invokes this port."""

    async def review(self, request: ApprovalRequest) -> ApprovalDecision: ...


@runtime_checkable
class PrivilegeBroker(Protocol):
    async def execute(
        self,
        grant: ApprovalGrant,
        *,
        actor: ActorContext,
    ) -> ExecutionReceipt: ...
