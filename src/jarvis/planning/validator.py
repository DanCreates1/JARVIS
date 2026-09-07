"""Deterministic validation for untrusted task-plan proposals."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .models import (
    TaskBudget,
    TaskGraph,
    TaskNode,
    TaskNodeKind,
    TaskPlanProposal,
    TaskRetryMode,
)
from .registry import TaskHandlerRegistry


class TaskPlanValidationError(ValueError):
    """Untrusted plan cannot become an executable graph."""


class TaskPlanValidator:
    def __init__(
        self,
        registry: TaskHandlerRegistry,
        *,
        envelope: TaskBudget | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry
        self._envelope = envelope or TaskBudget()
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def envelope(self) -> TaskBudget:
        return self._envelope

    def validate(
        self,
        proposal: TaskPlanProposal,
        *,
        host_id: str,
        task_id: str | None = None,
    ) -> TaskGraph:
        proposal = TaskPlanProposal.model_validate(proposal.model_dump())
        now = _aware(self._clock())
        self._validate_budget(proposal.budget)
        if proposal.deadline_at <= now:
            raise TaskPlanValidationError("task deadline must be in the future")
        if proposal.deadline_at > now + timedelta(seconds=proposal.budget.max_wall_seconds):
            raise TaskPlanValidationError("task deadline exceeds its wall-time budget")
        if len(proposal.nodes) > proposal.budget.max_steps:
            raise TaskPlanValidationError("task node count exceeds step budget")

        proposal_ids = {node.id for node in proposal.nodes}
        nodes: list[TaskNode] = []
        worst_steps = 0
        worst_tokens = 0
        worst_requests = 0
        worst_tools = 0
        worst_cost = 0.0
        worst_retries = 0
        for proposed in proposal.nodes:
            missing = set(proposed.dependencies).difference(proposal_ids)
            if missing:
                raise TaskPlanValidationError(
                    f"node {proposed.id!r} has unknown dependencies: {sorted(missing)!r}"
                )
            try:
                handler = self._registry.get(proposed.handler)
            except KeyError as exc:
                raise TaskPlanValidationError(str(exc)) from None
            definition = handler.definition
            if proposed.timeout_seconds > definition.max_timeout_seconds:
                raise TaskPlanValidationError(
                    f"node {proposed.id!r} exceeds handler timeout ceiling"
                )
            if definition.retry_mode is TaskRetryMode.NEVER and proposed.retry_limit:
                raise TaskPlanValidationError(f"node {proposed.id!r} handler cannot retry")
            if proposed.retry_limit > proposal.budget.max_retries:
                raise TaskPlanValidationError(f"node {proposed.id!r} exceeds retry budget")
            if definition.kind is TaskNodeKind.EFFECT and proposed.idempotency_key is None:
                raise TaskPlanValidationError(
                    f"effect node {proposed.id!r} requires an idempotency key"
                )
            multiplier = proposed.retry_limit + 1
            worst_steps += multiplier
            worst_tokens += proposed.charge.tokens * multiplier
            worst_requests += proposed.charge.provider_requests * multiplier
            worst_tools += proposed.charge.tool_calls * multiplier
            worst_cost += proposed.charge.cost_usd * multiplier
            worst_retries += proposed.retry_limit
            nodes.append(
                TaskNode(
                    id=proposed.id,
                    handler=proposed.handler,
                    kind=definition.kind,
                    retry_mode=definition.retry_mode,
                    arguments=proposed.arguments,
                    dependencies=proposed.dependencies,
                    timeout_seconds=proposed.timeout_seconds,
                    retry_limit=proposed.retry_limit,
                    idempotency_key=proposed.idempotency_key,
                    charge=proposed.charge,
                )
            )
        if worst_steps > proposal.budget.max_steps:
            raise TaskPlanValidationError("declared attempts exceed step budget")
        if worst_tokens > proposal.budget.max_tokens:
            raise TaskPlanValidationError("declared token use exceeds budget")
        if worst_requests > proposal.budget.max_provider_requests:
            raise TaskPlanValidationError("declared provider requests exceed budget")
        if worst_tools > proposal.budget.max_tool_calls:
            raise TaskPlanValidationError("declared tool calls exceed budget")
        if worst_cost > proposal.budget.max_cost_usd:
            raise TaskPlanValidationError("declared cost exceeds budget")
        if worst_retries > proposal.budget.max_retries:
            raise TaskPlanValidationError("declared retries exceed budget")
        _reject_cycles(nodes)

        digest_payload = proposal.model_dump_json().encode("utf-8")
        return TaskGraph(
            id=task_id or str(uuid4()),
            host_id=host_id,
            objective=proposal.objective,
            owner=proposal.owner,
            provenance=proposal.provenance,
            budget=proposal.budget,
            deadline_at=proposal.deadline_at,
            nodes=tuple(nodes),
            plan_sha256=hashlib.sha256(digest_payload).hexdigest(),
            created_at=now,
        )

    def _validate_budget(self, budget: TaskBudget) -> None:
        envelope = self._envelope
        comparisons = {
            "steps": (budget.max_steps, envelope.max_steps),
            "wall time": (budget.max_wall_seconds, envelope.max_wall_seconds),
            "tokens": (budget.max_tokens, envelope.max_tokens),
            "provider requests": (
                budget.max_provider_requests,
                envelope.max_provider_requests,
            ),
            "retries": (budget.max_retries, envelope.max_retries),
            "tool calls": (budget.max_tool_calls, envelope.max_tool_calls),
            "cost": (budget.max_cost_usd, envelope.max_cost_usd),
            "concurrency": (budget.max_concurrency, envelope.max_concurrency),
        }
        for name, (requested, maximum) in comparisons.items():
            if requested > maximum:
                raise TaskPlanValidationError(f"task {name} budget exceeds host envelope")


def _reject_cycles(nodes: list[TaskNode]) -> None:
    dependencies = {node.id: node.dependencies for node in nodes}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise TaskPlanValidationError("task graph contains a dependency cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dependency in dependencies[node_id]:
            visit(dependency)
        visiting.remove(node_id)
        visited.add(node_id)

    for node in nodes:
        visit(node.id)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("task validator clock must be timezone-aware")
    return value.astimezone(UTC)
