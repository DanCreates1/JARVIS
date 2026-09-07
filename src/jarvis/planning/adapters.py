"""Narrow Phase 3/5 adapters for bounded specialized task contexts."""

from __future__ import annotations

from jarvis.computer.runtime import ComputerRuntimeComponents
from jarvis.permissions import ExecutionOutcome, ExecutionReceipt
from jarvis.permissions.service import ActionCoordinatorStatus
from jarvis.permissions.sqlite_store import GrantStatus
from jarvis.research import SQLiteResearchStore

from .contracts import (
    TaskHandlerContext,
    TaskHandlerDefinition,
    TaskHandlerError,
    TaskHandlerResult,
)
from .models import TaskFailureClass, TaskNodeKind, TaskRetryMode


class StoredResearchTaskHandler:
    """Read metadata from an already host-approved research report."""

    definition = TaskHandlerDefinition(
        name="research.report.inspect",
        kind=TaskNodeKind.READ_ONLY,
        retry_mode=TaskRetryMode.NEVER,
        max_timeout_seconds=5,
        max_output_bytes=16 * 1_024,
    )

    def __init__(self, store: SQLiteResearchStore) -> None:
        self._store = store

    async def validate(self, context: TaskHandlerContext) -> None:
        if set(context.node.arguments) != {"report_id"}:
            raise ValueError("research.report.inspect requires exactly report_id")
        report_id = context.node.arguments["report_id"]
        if not isinstance(report_id, str) or not report_id.strip():
            raise ValueError("research report ID must be a nonblank string")

    async def execute(self, context: TaskHandlerContext) -> TaskHandlerResult:
        report_id = str(context.node.arguments["report_id"])
        report = await self._store.get_report(host_id=context.host_id, report_id=report_id)
        if report is None:
            raise TaskHandlerError("research_report_not_found", TaskFailureClass.TERMINAL)
        return TaskHandlerResult(
            output={
                "report_id": report.id,
                "state": report.state.value,
                "source_ids": list(report.source_ids),
                "claim_ids": list(report.claim_ids),
                "untrusted": True,
            }
        )

    async def verify(self, context: TaskHandlerContext, result: TaskHandlerResult) -> bool:
        return isinstance(result.output, dict) and result.output.get("report_id") == str(
            context.node.arguments["report_id"]
        )

    async def compensate(
        self, context: TaskHandlerContext, result: TaskHandlerResult | None
    ) -> bool:
        return True

    async def reconcile(self, context: TaskHandlerContext) -> TaskHandlerResult | None:
        return None


class ComputerGrantTaskHandler:
    """Execute only one already-issued exact Phase 3 grant; never propose or approve."""

    definition = TaskHandlerDefinition(
        name="computer.grant.execute",
        kind=TaskNodeKind.EFFECT,
        retry_mode=TaskRetryMode.RECONCILE_FIRST,
        max_timeout_seconds=30,
        max_output_bytes=8 * 1_024,
        requires_approval=True,
    )

    def __init__(self, computer: ComputerRuntimeComponents) -> None:
        self._computer = computer

    async def validate(self, context: TaskHandlerContext) -> None:
        if set(context.node.arguments) != {"action_id", "idempotency_key"}:
            raise ValueError(
                "computer.grant.execute requires exactly action_id and idempotency_key"
            )
        action_id = context.node.arguments["action_id"]
        key = context.node.arguments["idempotency_key"]
        if not isinstance(action_id, str) or not isinstance(key, str):
            raise ValueError("computer grant binding values must be strings")
        grant_id = context.node.approval_grant_id
        if grant_id is None:
            return
        record = await self._computer.store.get_grant_record(grant_id)
        if record is None or record.status is not GrantStatus.ACTIVE:
            raise TaskHandlerError("grant_inactive", TaskFailureClass.DENIED)
        action = record.grant.action
        if action.action_id != action_id or action.idempotency_key != key:
            raise TaskHandlerError("grant_binding_mismatch", TaskFailureClass.DENIED)
        if action.actor != self._computer.actor:
            raise TaskHandlerError("grant_actor_mismatch", TaskFailureClass.DENIED)

    async def execute(self, context: TaskHandlerContext) -> TaskHandlerResult:
        grant_id = context.node.approval_grant_id
        assert grant_id is not None
        result = await self._computer.coordinator.execute(grant_id, actor=self._computer.actor)
        if result.status is ActionCoordinatorStatus.DENIED:
            raise TaskHandlerError(result.code or "broker_denied", TaskFailureClass.DENIED)
        receipt = result.receipt
        if receipt is None:
            raise TaskHandlerError("missing_execution_receipt", TaskFailureClass.UNCERTAIN)
        if receipt.outcome is not ExecutionOutcome.SUCCEEDED:
            failure = (
                TaskFailureClass.UNCERTAIN
                if receipt.outcome is ExecutionOutcome.UNCERTAIN
                else TaskFailureClass.TERMINAL
            )
            raise TaskHandlerError(receipt.error_code or "computer_effect_failed", failure)
        return _computer_result(receipt)

    async def verify(self, context: TaskHandlerContext, result: TaskHandlerResult) -> bool:
        return (
            isinstance(result.output, dict)
            and result.output.get("outcome") == ExecutionOutcome.SUCCEEDED.value
            and result.output.get("idempotency_key") == context.node.idempotency_key
        )

    async def compensate(
        self, context: TaskHandlerContext, result: TaskHandlerResult | None
    ) -> bool:
        return False

    async def reconcile(self, context: TaskHandlerContext) -> TaskHandlerResult | None:
        key = context.node.arguments["idempotency_key"]
        assert isinstance(key, str)
        receipt = await self._computer.store.get_receipt(key)
        if receipt is None or receipt.outcome is not ExecutionOutcome.SUCCEEDED:
            return None
        return _computer_result(receipt)


def _computer_result(receipt: ExecutionReceipt) -> TaskHandlerResult:
    # Retain no private action result payload.
    return TaskHandlerResult(
        output={
            "receipt_id": receipt.receipt_id,
            "action_id": receipt.action_id,
            "idempotency_key": receipt.idempotency_key,
            "outcome": receipt.outcome.value,
            "postcondition_verified": True,
        }
    )
