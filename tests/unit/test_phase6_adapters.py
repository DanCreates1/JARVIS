from __future__ import annotations

from types import SimpleNamespace

import pytest

from jarvis.permissions import ExecutionOutcome
from jarvis.permissions.service import ActionCoordinatorStatus
from jarvis.permissions.sqlite_store import GrantStatus
from jarvis.planning import (
    ComputerGrantTaskHandler,
    StoredResearchTaskHandler,
    TaskCharge,
    TaskFailureClass,
    TaskHandlerContext,
    TaskHandlerError,
    TaskNode,
    TaskNodeKind,
    TaskRetryMode,
    TaskUsage,
)
from jarvis.research import ResearchReportState


def context(*, grant_id: str | None = None, arguments=None) -> TaskHandlerContext:
    return TaskHandlerContext(
        task_id="task-a",
        host_id="host-a",
        node=TaskNode(
            id="node-a",
            handler="computer.grant.execute",
            kind=TaskNodeKind.EFFECT,
            retry_mode=TaskRetryMode.RECONCILE_FIRST,
            arguments=arguments or {"action_id": "action.safe", "idempotency_key": "effect-key"},
            timeout_seconds=5,
            retry_limit=0,
            idempotency_key="effect-key",
            approval_grant_id=grant_id,
            charge=TaskCharge(),
        ),
        usage=TaskUsage(),
        dependency_outputs={},
    )


class FakeActionStore:
    def __init__(self, *, action_id: str = "action.safe") -> None:
        self.receipt = SimpleNamespace(
            receipt_id="receipt-a",
            action_id=action_id,
            idempotency_key="effect-key",
            outcome=ExecutionOutcome.SUCCEEDED,
            error_code=None,
        )
        action = SimpleNamespace(
            action_id=action_id,
            idempotency_key="effect-key",
            actor="actor-a",
        )
        self.grant = SimpleNamespace(action=action)

    async def get_grant_record(self, grant_id: str):
        return SimpleNamespace(status=GrantStatus.ACTIVE, grant=self.grant)

    async def get_receipt(self, key: str):
        return self.receipt if key == "effect-key" else None


class FakeCoordinator:
    def __init__(self, store: FakeActionStore, *, denied: bool = False) -> None:
        self.store = store
        self.denied = denied
        self.calls = 0

    async def execute(self, grant_id: str, *, actor: object):
        self.calls += 1
        if self.denied:
            return SimpleNamespace(
                status=ActionCoordinatorStatus.DENIED,
                code="grant_replayed",
                receipt=None,
            )
        return SimpleNamespace(
            status=ActionCoordinatorStatus.EXECUTED,
            code=None,
            receipt=self.store.receipt,
        )


@pytest.mark.asyncio
async def test_computer_adapter_validates_exact_grant_before_effect_and_sanitizes_output() -> None:
    store = FakeActionStore()
    coordinator = FakeCoordinator(store)
    computer = SimpleNamespace(store=store, coordinator=coordinator, actor="actor-a")
    handler = ComputerGrantTaskHandler(computer)  # type: ignore[arg-type]
    unbound = context()
    await handler.validate(unbound)
    bound = context(grant_id="grant-a")
    await handler.validate(bound)
    result = await handler.execute(bound)
    assert await handler.verify(bound, result) is True
    assert result.output == {
        "receipt_id": "receipt-a",
        "action_id": "action.safe",
        "idempotency_key": "effect-key",
        "outcome": "succeeded",
        "postcondition_verified": True,
    }
    assert coordinator.calls == 1


@pytest.mark.asyncio
async def test_computer_adapter_rejects_mutation_and_reconciles_without_replay() -> None:
    store = FakeActionStore(action_id="different.action")
    coordinator = FakeCoordinator(store)
    computer = SimpleNamespace(store=store, coordinator=coordinator, actor="actor-a")
    handler = ComputerGrantTaskHandler(computer)  # type: ignore[arg-type]
    bound = context(grant_id="grant-a")
    with pytest.raises(TaskHandlerError) as captured:
        await handler.validate(bound)
    assert captured.value.failure_class is TaskFailureClass.DENIED
    store.grant.action.action_id = "action.safe"
    reconciled = await handler.reconcile(bound)
    assert reconciled is not None
    assert coordinator.calls == 0


@pytest.mark.asyncio
async def test_computer_adapter_maps_broker_denial_without_retry() -> None:
    store = FakeActionStore()
    coordinator = FakeCoordinator(store, denied=True)
    computer = SimpleNamespace(store=store, coordinator=coordinator, actor="actor-a")
    handler = ComputerGrantTaskHandler(computer)  # type: ignore[arg-type]
    with pytest.raises(TaskHandlerError) as captured:
        await handler.execute(context(grant_id="grant-a"))
    assert captured.value.failure_class is TaskFailureClass.DENIED


@pytest.mark.asyncio
async def test_research_adapter_reads_only_approved_host_scoped_metadata() -> None:
    class Store:
        async def get_report(self, *, host_id: str, report_id: str):
            assert host_id == "host-a"
            if report_id == "missing":
                return None
            return SimpleNamespace(
                id=report_id,
                state=ResearchReportState.CURRENT,
                source_ids=("source-a",),
                claim_ids=("claim-a",),
            )

    handler = StoredResearchTaskHandler(Store())  # type: ignore[arg-type]
    read_context = context(
        arguments={"report_id": "report-a"},
    ).model_copy(
        update={
            "node": context().node.model_copy(
                update={
                    "handler": "research.report.inspect",
                    "kind": TaskNodeKind.READ_ONLY,
                    "retry_mode": TaskRetryMode.NEVER,
                    "idempotency_key": None,
                    "arguments": {"report_id": "report-a"},
                }
            )
        }
    )
    await handler.validate(read_context)
    result = await handler.execute(read_context)
    assert result.output["untrusted"] is True  # type: ignore[index]
    missing = read_context.model_copy(
        update={
            "node": read_context.node.model_copy(update={"arguments": {"report_id": "missing"}})
        }
    )
    with pytest.raises(TaskHandlerError, match="research_report_not_found"):
        await handler.execute(missing)
    assert await handler.verify(missing, result) is False
    assert await handler.compensate(read_context, result) is True
    assert await handler.reconcile(read_context) is None
    for arguments in ({}, {"report_id": ""}, {"report_id": 1}):
        invalid = read_context.model_copy(
            update={"node": read_context.node.model_copy(update={"arguments": arguments})}
        )
        with pytest.raises(ValueError):
            await handler.validate(invalid)


@pytest.mark.asyncio
async def test_computer_adapter_fails_closed_for_invalid_binding_actor_and_receipts() -> None:
    store = FakeActionStore()
    coordinator = FakeCoordinator(store)
    computer = SimpleNamespace(store=store, coordinator=coordinator, actor="actor-a")
    handler = ComputerGrantTaskHandler(computer)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="exactly"):
        await handler.validate(context(arguments={"action_id": "action.safe"}))
    with pytest.raises(ValueError, match="strings"):
        await handler.validate(
            context(
                grant_id="grant-a",
                arguments={"action_id": "action.safe", "idempotency_key": 1},
            )
        )

    store.grant.action.actor = "other-actor"
    with pytest.raises(TaskHandlerError, match="grant_actor_mismatch"):
        await handler.validate(context(grant_id="grant-a"))
    store.grant.action.actor = "actor-a"

    store.receipt = None
    with pytest.raises(TaskHandlerError) as missing:
        await handler.execute(context(grant_id="grant-a"))
    assert missing.value.failure_class is TaskFailureClass.UNCERTAIN

    for outcome, failure in (
        (ExecutionOutcome.UNCERTAIN, TaskFailureClass.UNCERTAIN),
        (ExecutionOutcome.FAILED, TaskFailureClass.TERMINAL),
    ):
        store.receipt = SimpleNamespace(
            receipt_id="receipt-failed",
            action_id="action.safe",
            idempotency_key="effect-key",
            outcome=outcome,
            error_code="fixture_failure",
        )
        with pytest.raises(TaskHandlerError) as captured:
            await handler.execute(context(grant_id="grant-a"))
        assert captured.value.failure_class is failure

    assert await handler.reconcile(context(arguments={"idempotency_key": "missing"})) is None
    assert await handler.compensate(context(), None) is False
