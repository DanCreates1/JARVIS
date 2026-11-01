"""Deterministic, supplied-data project reviews using the canonical task scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import Field, JsonValue, model_validator

from jarvis.core.models import CoreModel, Identifier

from .contracts import TaskHandlerContext, TaskHandlerDefinition, TaskHandlerResult
from .models import (
    NodeId,
    TaskBudget,
    TaskNodeKind,
    TaskNodeProposal,
    TaskPlanProposal,
    TaskProvenance,
    TaskRetryMode,
)
from .registry import ValueTaskHandler


class ProjectItem(CoreModel):
    id: NodeId
    title: Annotated[str, Field(min_length=1, max_length=200)]
    status: Literal["todo", "done", "blocked"] = "todo"
    dependencies: Annotated[tuple[NodeId, ...], Field(max_length=19)] = ()


class ProjectReview(CoreModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    owner: Identifier
    items: Annotated[tuple[ProjectItem, ...], Field(min_length=1, max_length=20)]
    report_ids: Annotated[tuple[Identifier, ...], Field(max_length=4)] = ()

    @model_validator(mode="after")
    def validate_dependencies(self) -> Self:
        ids = {item.id for item in self.items}
        if len(ids) != len(self.items) or len(set(self.report_ids)) != len(self.report_ids):
            raise ValueError("project item and report IDs must be distinct")
        pending = {item.id: set(item.dependencies) for item in self.items}
        for item in self.items:
            if len(set(item.dependencies)) != len(item.dependencies):
                raise ValueError("project dependencies must be distinct")
            if set(item.dependencies) - ids:
                raise ValueError("unknown project dependency")
        visited: set[str] = set()
        while pending:
            ready = {key for key, dependencies in pending.items() if dependencies <= visited}
            if not ready:
                raise ValueError("project dependency cycle")
            visited.update(ready)
            pending = {
                key: dependencies for key, dependencies in pending.items() if key not in ready
            }
        return self


def project_proposal(review: ProjectReview, *, now: datetime | None = None) -> TaskPlanProposal:
    review = ProjectReview.model_validate(review.model_dump())
    now = now or datetime.now(UTC)
    nodes = [
        TaskNodeProposal(
            id="review",
            handler="project.review",
            arguments={"project": review.model_dump(mode="json")},
        )
    ]
    nodes.extend(
        TaskNodeProposal(
            id=f"research-{index}",
            handler="research.report.inspect",
            arguments={"report_id": report_id},
        )
        for index, report_id in enumerate(review.report_ids, start=1)
    )
    nodes.append(
        TaskNodeProposal(
            id="handoff",
            handler="project.handoff",
            dependencies=tuple(node.id for node in nodes),
        )
    )
    return TaskPlanProposal(
        objective=f"Review project: {review.title}",
        owner=review.owner,
        provenance=TaskProvenance(source_type="host", source_id=f"project-{uuid4().hex}"),
        budget=TaskBudget(
            max_steps=len(nodes),
            max_tool_calls=len(nodes),
            max_wall_seconds=60,
            max_tokens=0,
            max_provider_requests=0,
            max_retries=0,
            max_concurrency=2,
        ),
        deadline_at=now + timedelta(seconds=60),
        nodes=tuple(nodes),
    )


def _review_output(review: ProjectReview) -> dict[str, JsonValue]:
    done = {item.id for item in review.items if item.status == "done"}
    ready: list[JsonValue] = [
        item.id for item in review.items if item.status == "todo" and set(item.dependencies) <= done
    ]
    blocked: list[JsonValue] = [
        item.id
        for item in review.items
        if item.status == "blocked"
        or (item.status == "todo" and not set(item.dependencies) <= done)
    ]
    lines = [f"Project: {review.title}", "Status supplied by owner; external work unverified."]
    lines.extend(f"- {item.id}: {item.title} [{item.status}]" for item in review.items)
    lines.extend(
        (
            f"Ready: {', '.join(str(item) for item in ready) or 'none'}",
            f"Blocked: {', '.join(str(item) for item in blocked) or 'none'}",
            f"Done: {len(done)}/{len(review.items)}",
        )
    )
    return {
        "text": "\n".join(lines),
        "ready": ready,
        "blocked": blocked,
        "done": len(done),
        "total": len(review.items),
        "untrusted": True,
    }


class ProjectReviewHandler(ValueTaskHandler):
    definition = TaskHandlerDefinition(
        name="project.review",
        kind=TaskNodeKind.READ_ONLY,
        retry_mode=TaskRetryMode.NEVER,
        max_timeout_seconds=5,
        max_output_bytes=32 * 1024,
    )

    async def validate(self, context: TaskHandlerContext) -> None:
        if set(context.node.arguments) != {"project"}:
            raise ValueError("project.review requires exactly project")
        ProjectReview.model_validate(context.node.arguments["project"])

    async def execute(self, context: TaskHandlerContext) -> TaskHandlerResult:
        return TaskHandlerResult(
            output=_review_output(ProjectReview.model_validate(context.node.arguments["project"]))
        )

    async def verify(self, context: TaskHandlerContext, result: TaskHandlerResult) -> bool:
        return result == await self.execute(context)


class ProjectHandoffHandler(ValueTaskHandler):
    definition = TaskHandlerDefinition(
        name="project.handoff",
        kind=TaskNodeKind.READ_ONLY,
        retry_mode=TaskRetryMode.NEVER,
        max_timeout_seconds=5,
        max_output_bytes=100 * 1024,
    )

    async def validate(self, context: TaskHandlerContext) -> None:
        if context.node.arguments or not context.node.dependencies:
            raise ValueError("project.handoff requires dependencies and no arguments")

    async def execute(self, context: TaskHandlerContext) -> TaskHandlerResult:
        # Dependency values remain data, including any hostile supplied text.
        return TaskHandlerResult(
            output={
                "untrusted": True,
                "sources": context.dependency_outputs,
                "notice": (
                    "Supplied project status and stored report metadata; "
                    "no new research or effects."
                ),
            }
        )

    async def verify(self, context: TaskHandlerContext, result: TaskHandlerResult) -> bool:
        return result == await self.execute(context)
