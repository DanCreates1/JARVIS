from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jarvis.planning import (
    TaskBudget,
    TaskCharge,
    TaskHandlerContext,
    TaskHandlerDefinition,
    TaskHandlerRegistry,
    TaskHandlerResult,
    TaskNodeKind,
    TaskNodeProposal,
    TaskPlanProposal,
    TaskPlanValidationError,
    TaskPlanValidator,
    TaskProvenance,
    TaskRetryMode,
    TaskUsage,
    ValueTaskHandler,
)

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


def proposal(*nodes: TaskNodeProposal, budget: TaskBudget | None = None) -> TaskPlanProposal:
    return TaskPlanProposal(
        objective="bounded fixture",
        owner="host-owner",
        provenance=TaskProvenance(source_type="test", source_id="fixture"),
        budget=budget or TaskBudget(),
        deadline_at=NOW + timedelta(seconds=60),
        nodes=nodes,
    )


class EffectHandler:
    definition = TaskHandlerDefinition(
        name="effect.fixture",
        kind=TaskNodeKind.EFFECT,
        retry_mode=TaskRetryMode.RECONCILE_FIRST,
        max_timeout_seconds=5,
        requires_approval=True,
    )

    async def validate(self, context: TaskHandlerContext) -> None:
        pass

    async def execute(self, context: TaskHandlerContext) -> TaskHandlerResult:
        return TaskHandlerResult(output=True)

    async def verify(self, context: TaskHandlerContext, result: TaskHandlerResult) -> bool:
        return True

    async def compensate(
        self, context: TaskHandlerContext, result: TaskHandlerResult | None
    ) -> bool:
        return False

    async def reconcile(self, context: TaskHandlerContext) -> TaskHandlerResult | None:
        return None


def validator() -> TaskPlanValidator:
    return TaskPlanValidator(
        TaskHandlerRegistry((ValueTaskHandler(), EffectHandler())), clock=lambda: NOW
    )


def test_models_enforce_zero_cost_and_untrusted_external_provenance() -> None:
    with pytest.raises(ValidationError):
        TaskBudget(max_cost_usd=0.01)
    with pytest.raises(ValidationError):
        TaskProvenance(source_type="model", source_id="planner", untrusted=False)
    assert TaskUsage().plus(TaskCharge(tokens=2), retry=True).retries == 1


def test_handler_definition_requires_effect_approval() -> None:
    with pytest.raises(ValidationError):
        TaskHandlerDefinition(
            name="unsafe",
            kind=TaskNodeKind.EFFECT,
            retry_mode=TaskRetryMode.NEVER,
            max_timeout_seconds=1,
        )


def test_validator_builds_typed_dag_and_resolves_handler_security_metadata() -> None:
    graph = validator().validate(
        proposal(
            TaskNodeProposal(id="a", handler="task.value", arguments={"value": 1}),
            TaskNodeProposal(
                id="b",
                handler="effect.fixture",
                arguments={},
                dependencies=("a",),
                idempotency_key="effect-1",
            ),
        ),
        host_id="host-a",
        task_id="task-a",
    )
    assert graph.id == "task-a"
    assert graph.host_id == "host-a"
    assert graph.nodes[0].kind is TaskNodeKind.READ_ONLY
    assert graph.nodes[1].kind is TaskNodeKind.EFFECT
    assert graph.nodes[1].approval_grant_id is None


@pytest.mark.parametrize(
    ("nodes", "message"),
    [
        (
            (
                TaskNodeProposal(
                    id="a", handler="task.value", arguments={"value": 1}, dependencies=("b",)
                ),
                TaskNodeProposal(
                    id="b", handler="task.value", arguments={"value": 2}, dependencies=("a",)
                ),
            ),
            "cycle",
        ),
        (
            (TaskNodeProposal(id="a", handler="missing.handler", arguments={}),),
            "unknown task handler",
        ),
        (
            (
                TaskNodeProposal(
                    id="a", handler="task.value", arguments={"value": 1}, dependencies=("missing",)
                ),
            ),
            "unknown dependencies",
        ),
        (
            (TaskNodeProposal(id="a", handler="effect.fixture", arguments={}),),
            "idempotency key",
        ),
    ],
)
def test_validator_rejects_unsafe_graph_shapes(
    nodes: tuple[TaskNodeProposal, ...], message: str
) -> None:
    with pytest.raises(TaskPlanValidationError, match=message):
        validator().validate(proposal(*nodes), host_id="host-a")


def test_validator_rejects_budget_and_deadline_expansion() -> None:
    restrictive = TaskPlanValidator(
        TaskHandlerRegistry((ValueTaskHandler(),)),
        envelope=TaskBudget(max_steps=2, max_wall_seconds=30, max_tool_calls=2),
        clock=lambda: NOW,
    )
    over = proposal(
        TaskNodeProposal(id="a", handler="task.value", arguments={"value": 1}),
        budget=TaskBudget(max_steps=3, max_wall_seconds=60, max_tool_calls=3),
    )
    with pytest.raises(TaskPlanValidationError, match="host envelope"):
        restrictive.validate(over, host_id="host-a")


def test_registry_rejects_duplicates_and_unknown_names() -> None:
    with pytest.raises(ValueError, match="at least one"):
        TaskHandlerRegistry(())
    with pytest.raises(ValueError, match="duplicate"):
        TaskHandlerRegistry((ValueTaskHandler(), ValueTaskHandler()))
    registry = TaskHandlerRegistry((ValueTaskHandler(),))
    assert registry.names == frozenset({"task.value"})
    with pytest.raises(KeyError, match="unknown task handler"):
        registry.get("unknown")


@pytest.mark.parametrize(
    ("node", "budget", "message"),
    [
        (
            TaskNodeProposal(
                id="value", handler="task.value", arguments={"value": 1}, timeout_seconds=6
            ),
            TaskBudget(),
            "timeout ceiling",
        ),
        (
            TaskNodeProposal(
                id="value", handler="task.value", arguments={"value": 1}, retry_limit=1
            ),
            TaskBudget(max_retries=1),
            "cannot retry",
        ),
        (
            TaskNodeProposal(
                id="effect",
                handler="effect.fixture",
                arguments={},
                retry_limit=2,
                idempotency_key="effect-retry",
            ),
            TaskBudget(max_steps=3, max_retries=1, max_tool_calls=3),
            "exceeds retry budget",
        ),
        (
            TaskNodeProposal(
                id="effect",
                handler="effect.fixture",
                arguments={},
                retry_limit=1,
                idempotency_key="effect-steps",
            ),
            TaskBudget(max_steps=1, max_retries=1, max_tool_calls=2),
            "attempts exceed step budget",
        ),
        (
            TaskNodeProposal(
                id="value",
                handler="task.value",
                arguments={"value": 1},
                charge=TaskCharge(tokens=1),
            ),
            TaskBudget(max_tokens=0),
            "token use exceeds budget",
        ),
        (
            TaskNodeProposal(
                id="value",
                handler="task.value",
                arguments={"value": 1},
                charge=TaskCharge(provider_requests=1),
            ),
            TaskBudget(max_provider_requests=0),
            "provider requests exceed budget",
        ),
        (
            TaskNodeProposal(
                id="value",
                handler="task.value",
                arguments={"value": 1},
                charge=TaskCharge(tool_calls=2),
            ),
            TaskBudget(max_tool_calls=1),
            "tool calls exceed budget",
        ),
    ],
)
def test_validator_rejects_handler_and_aggregate_budget_violations(
    node: TaskNodeProposal, budget: TaskBudget, message: str
) -> None:
    with pytest.raises(TaskPlanValidationError, match=message):
        validator().validate(proposal(node, budget=budget), host_id="host-a")


def test_validator_rejects_expired_excessive_and_over_node_deadlines() -> None:
    expired = proposal(TaskNodeProposal(id="a", handler="task.value", arguments={"value": 1}))
    expired = expired.model_copy(update={"deadline_at": NOW})
    with pytest.raises(TaskPlanValidationError, match="future"):
        validator().validate(expired, host_id="host-a")

    excessive = proposal(
        TaskNodeProposal(id="a", handler="task.value", arguments={"value": 1}),
        budget=TaskBudget(max_wall_seconds=30),
    )
    with pytest.raises(TaskPlanValidationError, match="wall-time"):
        validator().validate(excessive, host_id="host-a")

    over_nodes = proposal(
        TaskNodeProposal(id="a", handler="task.value", arguments={"value": 1}),
        TaskNodeProposal(id="b", handler="task.value", arguments={"value": 2}),
        budget=TaskBudget(max_steps=1, max_tool_calls=2),
    )
    with pytest.raises(TaskPlanValidationError, match="node count"):
        validator().validate(over_nodes, host_id="host-a")

    naive_clock = TaskPlanValidator(
        TaskHandlerRegistry((ValueTaskHandler(),)), clock=lambda: NOW.replace(tzinfo=None)
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        naive_clock.validate(expired, host_id="host-a")


@pytest.mark.parametrize(
    "field",
    [
        "max_wall_seconds",
        "max_tokens",
        "max_provider_requests",
        "max_retries",
        "max_tool_calls",
        "max_concurrency",
    ],
)
def test_validator_rejects_each_host_budget_dimension(field: str) -> None:
    values = {
        "max_wall_seconds": 3_601,
        "max_tokens": 100_001,
        "max_provider_requests": 101,
        "max_retries": 6,
        "max_tool_calls": 101,
        "max_concurrency": 4,
    }
    envelope_values = {field: values[field] - 1}
    proposal_values = {field: values[field]}
    restrictive = TaskPlanValidator(
        TaskHandlerRegistry((ValueTaskHandler(),)),
        envelope=TaskBudget(**envelope_values),
        clock=lambda: NOW,
    )
    candidate = proposal(
        TaskNodeProposal(id="a", handler="task.value", arguments={"value": 1}),
        budget=TaskBudget(**proposal_values),
    )
    with pytest.raises(TaskPlanValidationError, match="host envelope"):
        restrictive.validate(candidate, host_id="host-a")
