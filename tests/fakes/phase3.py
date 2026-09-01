"""Deterministic fakes for Phase 3 permission and broker tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from pydantic import JsonValue

from jarvis.core import (
    ApprovalRule,
    PermissionLevel,
    SensitivityClass,
    ToolConcurrency,
    ToolDefinition,
    ToolIdempotency,
    ToolRetryPolicy,
    ToolRisk,
    ToolSideEffect,
)
from jarvis.permissions import (
    ActionAuditEvent,
    ActionDefinition,
    ActionEffect,
    ActorContext,
    ApprovalGrant,
    AuthenticationAssurance,
    CanonicalAction,
    ExecutionReceipt,
    InteractionInterface,
    PostconditionEvidence,
    PostconditionStatus,
    RollbackReceipt,
    RollbackStatus,
)

FIXED_NOW = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)
POLICY_VERSION = "phase3-policy-v1"


def actor(
    *,
    session_id: str = "session-1",
    device_id: str = "device-1",
    interface: InteractionInterface = InteractionInterface.TEST,
    assurance: AuthenticationAssurance = AuthenticationAssurance.LOCAL_SESSION,
    authenticated_at: datetime | None = FIXED_NOW,
    capabilities: tuple[str, ...] = ("computer.test",),
) -> ActorContext:
    return ActorContext(
        host_id="host-1",
        session_id=session_id,
        device_id=device_id,
        interface=interface,
        assurance=assurance,
        authenticated_at=(
            None if assurance is AuthenticationAssurance.UNAUTHENTICATED else authenticated_at
        ),
        capabilities=capabilities,
    )


def action_definition(
    level: PermissionLevel = PermissionLevel.LEVEL_2,
    *,
    name: str = "test_action",
    version: str = "1",
    timeout_seconds: float = 0.2,
    max_result_bytes: int = 1_024,
    max_result_items: int = 20,
    supports_rollback: bool = True,
    effect_may_outlive_cancellation: bool = False,
    approval_rule: ApprovalRule | None = None,
    concurrency: ToolConcurrency = ToolConcurrency.SERIAL_PER_SESSION,
) -> ActionDefinition:
    rules = {
        PermissionLevel.LEVEL_0: ApprovalRule.NONE,
        PermissionLevel.LEVEL_1: ApprovalRule.EXPLICIT_ENABLEMENT,
        PermissionLevel.LEVEL_2: ApprovalRule.POLICY_OR_EXPLICIT,
        PermissionLevel.LEVEL_3: ApprovalRule.EXACT_RECENT_AUTH,
        PermissionLevel.LEVEL_4: ApprovalRule.DISABLED,
    }
    risks = {
        PermissionLevel.LEVEL_0: ToolRisk.READ_ONLY,
        PermissionLevel.LEVEL_1: ToolRisk.REVERSIBLE,
        PermissionLevel.LEVEL_2: ToolRisk.REVERSIBLE,
        PermissionLevel.LEVEL_3: ToolRisk.SENSITIVE,
        PermissionLevel.LEVEL_4: ToolRisk.DESTRUCTIVE,
    }
    effects = {
        PermissionLevel.LEVEL_0: ToolSideEffect.NONE,
        PermissionLevel.LEVEL_1: ToolSideEffect.REVERSIBLE,
        PermissionLevel.LEVEL_2: ToolSideEffect.REVERSIBLE,
        PermissionLevel.LEVEL_3: ToolSideEffect.REVERSIBLE,
        PermissionLevel.LEVEL_4: ToolSideEffect.ADMINISTRATIVE,
    }
    idempotency = (
        ToolIdempotency.SIDE_EFFECT_FREE
        if level is PermissionLevel.LEVEL_0
        else ToolIdempotency.IDEMPOTENCY_KEY
    )
    tool = ToolDefinition(
        name=name,
        version=version,
        description="Deterministic broker test action.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "additionalProperties": False,
        },
        permission_level=level,
        approval_rule=approval_rule or rules[level],
        risk=risks[level],
        side_effect=effects[level],
        sensitivity=SensitivityClass.PRIVATE,
        required_capabilities=("computer.test",),
        timeout_seconds=timeout_seconds,
        max_result_bytes=max_result_bytes,
        max_result_items=max_result_items,
        idempotency=idempotency,
        retry_policy=(
            ToolRetryPolicy.TRANSIENT_ONLY
            if level is PermissionLevel.LEVEL_0
            else ToolRetryPolicy.RECONCILE_FIRST
        ),
        concurrency=concurrency,
        postcondition="The fake verifier reports the expected state.",
        recovery="Use the fake rollback method when execution may have changed state.",
    )
    return ActionDefinition(
        tool=tool,
        supports_rollback=(supports_rollback and level is not PermissionLevel.LEVEL_0),
        effect_may_outlive_cancellation=effect_may_outlive_cancellation,
        rollback_timeout_seconds=0.1,
    )


def canonical_action(
    definition: ActionDefinition,
    *,
    action_actor: ActorContext | None = None,
    now: datetime = FIXED_NOW,
    action_id: str | None = None,
    action_version: str | None = None,
    arguments: dict[str, JsonValue] | None = None,
    idempotency_key: str = "idempotency-1",
    policy_version: str = POLICY_VERSION,
) -> CanonicalAction:
    return CanonicalAction.create(
        request_id=f"request-{idempotency_key}",
        action_id=action_id or definition.action_id,
        action_version=action_version or definition.version,
        actor=action_actor or actor(),
        normalized_arguments=arguments or {"value": "safe"},
        permission_level=definition.tool.permission_level,
        approval_rule=definition.tool.approval_rule,
        policy_version=policy_version,
        idempotency_key=idempotency_key,
        human_effect="Apply one bounded fake effect.",
        recovery_limits="Rollback is bounded to this fake effect.",
        created_at=now,
        expires_at=now + timedelta(minutes=2),
        conversation_id="conversation-1",
        tool_call_id="tool-call-1",
        precondition={"state": "before"},
    )


def approval_grant(
    action: CanonicalAction,
    *,
    now: datetime = FIXED_NOW,
    grant_id: str = "grant-1",
    approver: ActorContext | None = None,
) -> ApprovalGrant:
    return ApprovalGrant.create(
        grant_id=grant_id,
        approval_id="approval-1",
        action=action,
        approved_by=approver or action.actor,
        issued_at=now,
        expires_at=now + timedelta(minutes=1),
        nonce=f"nonce-{grant_id}",
    )


class InMemoryActionState:
    def __init__(self) -> None:
        self.claimed_grants: set[str] = set()
        self.claimed_idempotency: set[str] = set()
        self.receipts: dict[str, ExecutionReceipt] = {}
        self.claim_count = 0
        self.complete_count = 0
        self.fail_get = False
        self.fail_claim = False
        self.fail_complete = False
        self._lock = asyncio.Lock()

    async def get_receipt(self, idempotency_key: str) -> ExecutionReceipt | None:
        if self.fail_get:
            raise RuntimeError("forced get failure")
        return self.receipts.get(idempotency_key)

    async def claim_grant(self, grant: ApprovalGrant, *, claimed_at: datetime) -> bool:
        del claimed_at
        if self.fail_claim:
            raise RuntimeError("forced claim failure")
        async with self._lock:
            if (
                grant.grant_id in self.claimed_grants
                or grant.action.idempotency_key in self.claimed_idempotency
            ):
                return False
            self.claimed_grants.add(grant.grant_id)
            self.claimed_idempotency.add(grant.action.idempotency_key)
            self.claim_count += 1
            return True

    async def complete_grant(
        self,
        grant: ApprovalGrant,
        receipt: ExecutionReceipt,
    ) -> None:
        if self.fail_complete:
            raise RuntimeError("forced completion failure")
        self.receipts[grant.action.idempotency_key] = receipt
        self.complete_count += 1


class InMemoryActionAudit:
    def __init__(self, *, fail_calls: set[int] | None = None) -> None:
        self.events: list[ActionAuditEvent] = []
        self.calls = 0
        self.fail_calls = fail_calls or set()

    async def append_action_event(self, event: ActionAuditEvent) -> None:
        self.calls += 1
        if self.calls in self.fail_calls:
            raise RuntimeError("forced audit failure")
        self.events.append(event)


class FakeActionHandler:
    def __init__(
        self,
        definition: ActionDefinition,
        *,
        result: JsonValue = None,
        verify_status: PostconditionStatus = PostconditionStatus.PASSED,
        rollback_status: RollbackStatus = RollbackStatus.SUCCEEDED,
        execute_error: Exception | None = None,
        execute_delay: float = 0,
        block: bool = False,
    ) -> None:
        self._definition = definition
        self.result = result if result is not None else {"ok": True}
        self.verify_status = verify_status
        self.rollback_status = rollback_status
        self.execute_error = execute_error
        self.execute_delay = execute_delay
        self.block = block
        self.execute_started = asyncio.Event()
        self.second_execute_started = asyncio.Event()
        self.release_execute = asyncio.Event()
        self.execute_calls = 0
        self.verify_calls = 0
        self.rollback_calls = 0
        self.rollback_reasons: list[str] = []

    @property
    def definition(self) -> ActionDefinition:
        return self._definition

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        del action
        self.execute_calls += 1
        self.execute_started.set()
        if self.execute_calls >= 2:
            self.second_execute_started.set()
        if self.execute_delay:
            await asyncio.sleep(self.execute_delay)
        if self.block:
            await self.release_execute.wait()
        if self.execute_error is not None:
            raise self.execute_error
        return ActionEffect(result=self.result, rollback_context={"changed": True})

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        del action, effect
        self.verify_calls += 1
        return PostconditionEvidence(
            status=self.verify_status,
            summary=f"Verifier returned {self.verify_status.value}.",
        )

    async def rollback(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
        *,
        reason: str,
    ) -> RollbackReceipt:
        del action, effect
        self.rollback_calls += 1
        self.rollback_reasons.append(reason)
        return RollbackReceipt(
            status=self.rollback_status,
            summary=f"Rollback returned {self.rollback_status.value}.",
        )
