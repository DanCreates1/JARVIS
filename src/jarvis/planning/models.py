"""Strict contracts for durable, bounded Phase 6 task graphs."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, JsonValue, StringConstraints, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier

HandlerName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]
NodeId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$",
    ),
]


class TaskStatus(StrEnum):
    PROPOSED = "proposed"
    READY = "ready"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_RECONCILIATION = "needs_reconciliation"


class NodeStatus(StrEnum):
    PROPOSED = "proposed"
    READY = "ready"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    NEEDS_RECONCILIATION = "needs_reconciliation"


class TaskNodeKind(StrEnum):
    READ_ONLY = "read_only"
    EFFECT = "effect"


class TaskRetryMode(StrEnum):
    NEVER = "never"
    TRANSIENT = "transient"
    RECONCILE_FIRST = "reconcile_first"


class TaskFailureClass(StrEnum):
    TRANSIENT = "transient"
    TERMINAL = "terminal"
    DENIED = "denied"
    TIMEOUT = "timeout"
    CAPACITY = "capacity"
    CANCELLED = "cancelled"
    UNCERTAIN = "uncertain"
    INVALID_RESULT = "invalid_result"


class TaskEventType(StrEnum):
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_PAUSED = "task_paused"
    TASK_RESUMED = "task_resumed"
    TASK_CANCEL_REQUESTED = "task_cancel_requested"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_PARTIAL = "task_partial"
    TASK_CANCELLED = "task_cancelled"
    TASK_RECONCILIATION_REQUIRED = "task_reconciliation_required"
    NODE_READY = "node_ready"
    NODE_WAITING_APPROVAL = "node_waiting_approval"
    NODE_APPROVAL_BOUND = "node_approval_bound"
    NODE_STARTED = "node_started"
    NODE_VERIFYING = "node_verifying"
    NODE_RETRY_SCHEDULED = "node_retry_scheduled"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_SKIPPED = "node_skipped"
    NODE_CANCELLED = "node_cancelled"
    NODE_COMPENSATING = "node_compensating"
    NODE_COMPENSATED = "node_compensated"
    NODE_RECONCILIATION_REQUIRED = "node_reconciliation_required"
    BUDGET_EXHAUSTED = "budget_exhausted"
    ORPHAN_RECOVERED = "orphan_recovered"
    TASK_DELETED = "task_deleted"


class TaskProvenance(CoreModel):
    source_type: Annotated[str, Field(pattern=r"^(host|model|research|api|test)$")]
    source_id: Identifier
    untrusted: bool = True

    @model_validator(mode="after")
    def model_and_research_remain_untrusted(self) -> Self:
        if self.source_type in {"model", "research"} and not self.untrusted:
            raise ValueError("model and research plans must remain untrusted")
        return self


class TaskBudget(CoreModel):
    max_steps: Annotated[int, Field(ge=1, le=100)] = 25
    max_wall_seconds: Annotated[float, Field(gt=0, le=86_400)] = 300
    max_tokens: Annotated[int, Field(ge=0, le=1_000_000)] = 20_000
    max_provider_requests: Annotated[int, Field(ge=0, le=1_000)] = 20
    max_retries: Annotated[int, Field(ge=0, le=10)] = 3
    max_tool_calls: Annotated[int, Field(ge=0, le=1_000)] = 25
    max_cost_usd: Annotated[float, Field(ge=0, le=0)] = 0
    max_concurrency: Annotated[int, Field(ge=1, le=4)] = 2


class TaskCharge(CoreModel):
    steps: Annotated[int, Field(ge=1, le=1)] = 1
    tokens: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    provider_requests: Annotated[int, Field(ge=0, le=1_000)] = 0
    tool_calls: Annotated[int, Field(ge=0, le=1_000)] = 1
    cost_usd: Annotated[float, Field(ge=0, le=0)] = 0


class TaskUsage(CoreModel):
    steps: Annotated[int, Field(ge=0)] = 0
    tokens: Annotated[int, Field(ge=0)] = 0
    provider_requests: Annotated[int, Field(ge=0)] = 0
    retries: Annotated[int, Field(ge=0)] = 0
    tool_calls: Annotated[int, Field(ge=0)] = 0
    cost_usd: Annotated[float, Field(ge=0)] = 0

    def plus(self, charge: TaskCharge, *, retry: bool = False) -> TaskUsage:
        return TaskUsage(
            steps=self.steps + charge.steps,
            tokens=self.tokens + charge.tokens,
            provider_requests=self.provider_requests + charge.provider_requests,
            retries=self.retries + int(retry),
            tool_calls=self.tool_calls + charge.tool_calls,
            cost_usd=self.cost_usd + charge.cost_usd,
        )

    def fits(self, budget: TaskBudget) -> bool:
        return (
            self.steps <= budget.max_steps
            and self.tokens <= budget.max_tokens
            and self.provider_requests <= budget.max_provider_requests
            and self.retries <= budget.max_retries
            and self.tool_calls <= budget.max_tool_calls
            and self.cost_usd <= budget.max_cost_usd
        )


class TaskNodeProposal(CoreModel):
    id: NodeId
    handler: HandlerName
    arguments: Annotated[dict[str, JsonValue], Field(max_length=50)] = Field(default_factory=dict)
    dependencies: Annotated[tuple[NodeId, ...], Field(max_length=99)] = ()
    timeout_seconds: Annotated[float, Field(gt=0, le=30)] = 5
    retry_limit: Annotated[int, Field(ge=0, le=10)] = 0
    idempotency_key: Identifier | None = None
    charge: TaskCharge = Field(default_factory=TaskCharge)

    @field_validator("dependencies")
    @classmethod
    def require_distinct_dependencies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("node dependencies must be distinct")
        return value

    @model_validator(mode="after")
    def prevent_self_dependency(self) -> Self:
        if self.id in self.dependencies:
            raise ValueError("node cannot depend on itself")
        return self


class TaskPlanProposal(CoreModel):
    objective: Annotated[str, Field(min_length=1, max_length=2_000)]
    owner: Identifier
    provenance: TaskProvenance
    budget: TaskBudget = Field(default_factory=TaskBudget)
    deadline_at: datetime
    nodes: Annotated[tuple[TaskNodeProposal, ...], Field(min_length=1, max_length=100)]

    @field_validator("deadline_at")
    @classmethod
    def require_aware_deadline(cls, value: datetime) -> datetime:
        return _aware(value, "task deadline")

    @model_validator(mode="after")
    def require_distinct_node_ids(self) -> Self:
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("task node IDs must be distinct")
        return self


class TaskNode(CoreModel):
    id: NodeId
    handler: HandlerName
    kind: TaskNodeKind
    retry_mode: TaskRetryMode
    arguments: Annotated[dict[str, JsonValue], Field(max_length=50)] = Field(default_factory=dict)
    dependencies: Annotated[tuple[NodeId, ...], Field(max_length=99)] = ()
    timeout_seconds: Annotated[float, Field(gt=0, le=30)]
    retry_limit: Annotated[int, Field(ge=0, le=10)]
    idempotency_key: Identifier | None = None
    approval_grant_id: Identifier | None = None
    charge: TaskCharge

    @model_validator(mode="after")
    def require_effect_identity(self) -> Self:
        if self.kind is TaskNodeKind.EFFECT and self.idempotency_key is None:
            raise ValueError("effect nodes require an idempotency key")
        if self.kind is TaskNodeKind.READ_ONLY and self.approval_grant_id is not None:
            raise ValueError("read-only nodes cannot bind approval grants")
        if self.retry_mode is TaskRetryMode.NEVER and self.retry_limit:
            raise ValueError("non-retryable handlers require retry_limit=0")
        return self


class TaskGraph(CoreModel):
    id: Identifier
    host_id: Identifier
    objective: Annotated[str, Field(min_length=1, max_length=2_000)]
    owner: Identifier
    provenance: TaskProvenance
    budget: TaskBudget
    deadline_at: datetime
    nodes: Annotated[tuple[TaskNode, ...], Field(min_length=1, max_length=100)]
    plan_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    created_at: datetime

    @field_validator("deadline_at", "created_at")
    @classmethod
    def require_aware_times(cls, value: datetime) -> datetime:
        return _aware(value, "task graph")


class TaskNodeRuntime(CoreModel):
    node_id: NodeId
    status: NodeStatus = NodeStatus.PROPOSED
    attempts: Annotated[int, Field(ge=0, le=11)] = 0
    output: JsonValue | None = None
    error_code: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    failure_class: TaskFailureClass | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_aware_optional_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value, "node runtime")


class TaskRecord(CoreModel):
    graph: TaskGraph
    status: TaskStatus = TaskStatus.PROPOSED
    nodes: tuple[TaskNodeRuntime, ...]
    usage: TaskUsage = Field(default_factory=TaskUsage)
    version: Annotated[int, Field(ge=1)] = 1
    pause_requested: bool = False
    cancel_requested: bool = False
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def require_aware_update(cls, value: datetime) -> datetime:
        return _aware(value, "task update")

    @model_validator(mode="after")
    def require_runtime_alignment(self) -> Self:
        graph_ids = [node.id for node in self.graph.nodes]
        runtime_ids = [node.node_id for node in self.nodes]
        if runtime_ids != graph_ids:
            raise ValueError("task runtime nodes must align with graph order")
        return self


class TaskEvent(CoreModel):
    sequence: Annotated[int, Field(ge=1)]
    id: Identifier
    task_id: Identifier
    host_id: Identifier
    node_id: NodeId | None = None
    event_type: TaskEventType
    task_status: TaskStatus
    node_status: NodeStatus | None = None
    reason_code: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_aware_event_time(cls, value: datetime) -> datetime:
        return _aware(value, "task event")


class TaskDeletionReceipt(CoreModel):
    task_id: Identifier
    deleted_nodes: Annotated[int, Field(ge=0)]
    deleted_events: Annotated[int, Field(ge=0)]
    deleted_at: datetime


class TaskExportReceipt(CoreModel):
    path: Annotated[str, Field(min_length=1, max_length=4_096)]
    task_count: Annotated[int, Field(ge=0)]
    event_count: Annotated[int, Field(ge=0)]
    exported_at: datetime


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)
