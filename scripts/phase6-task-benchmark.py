"""Reproducible Phase 6 bounded-task correctness, recovery, and latency benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from jarvis.planning import (
    NodeStatus,
    SQLiteTaskStore,
    TaskBudget,
    TaskEventType,
    TaskFailureClass,
    TaskHandlerContext,
    TaskHandlerDefinition,
    TaskHandlerError,
    TaskHandlerRegistry,
    TaskHandlerResult,
    TaskNodeKind,
    TaskNodeProposal,
    TaskPlanProposal,
    TaskPlanValidator,
    TaskProvenance,
    TaskRetryMode,
    TaskScheduler,
    TaskStatus,
    TaskUsage,
    ValueTaskHandler,
)

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
RUNTIME_ROOT: Final = (REPOSITORY_ROOT / "runtime").resolve()
TARGETS: Final = {
    "performance_samples": 100,
    "golden_scenarios": 100,
    "p95_ms": 50.0,
    "failures": 0,
    "duplicate_effects": 0,
    "unauthorized_effects": 0,
    "budget_violations": 0,
}


class BenchmarkHandler:
    def __init__(
        self,
        name: str,
        *,
        effect: bool = False,
        retry: bool = False,
        fail: bool = False,
    ) -> None:
        kind = TaskNodeKind.EFFECT if effect else TaskNodeKind.READ_ONLY
        self.definition = TaskHandlerDefinition(
            name=name,
            kind=kind,
            retry_mode=(TaskRetryMode.RECONCILE_FIRST if effect else TaskRetryMode.TRANSIENT)
            if retry or effect
            else TaskRetryMode.NEVER,
            max_timeout_seconds=5,
            requires_approval=effect,
        )
        self._fail = fail
        self._failed_once: set[str] = set()
        self.effects: set[str] = set()
        self.duplicate_effects = 0

    async def validate(self, context: TaskHandlerContext) -> None:
        if context.node.arguments:
            raise ValueError("benchmark handlers take no arguments")

    async def execute(self, context: TaskHandlerContext) -> TaskHandlerResult:
        if self._fail:
            raise TaskHandlerError("fixture_terminal", TaskFailureClass.TERMINAL)
        if (
            self.definition.retry_mode is TaskRetryMode.TRANSIENT
            and context.node.id not in self._failed_once
        ):
            self._failed_once.add(context.node.id)
            raise TaskHandlerError("fixture_transient", TaskFailureClass.TRANSIENT)
        if self.definition.kind is TaskNodeKind.EFFECT:
            assert context.node.idempotency_key is not None
            if context.node.idempotency_key in self.effects:
                self.duplicate_effects += 1
            self.effects.add(context.node.idempotency_key)
        return TaskHandlerResult(output=context.node.id)

    async def verify(self, context: TaskHandlerContext, result: TaskHandlerResult) -> bool:
        return result.output == context.node.id

    async def compensate(
        self, context: TaskHandlerContext, result: TaskHandlerResult | None
    ) -> bool:
        return False

    async def reconcile(self, context: TaskHandlerContext) -> TaskHandlerResult | None:
        if context.node.idempotency_key in self.effects:
            return TaskHandlerResult(output=context.node.id)
        return None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", default="results.json")
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--golden-scenarios", type=int, default=100)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args(argv)
    if args.samples < 100:
        parser.error("--samples must be at least 100")
    if args.golden_scenarios < 100:
        parser.error("--golden-scenarios must be at least 100")
    if Path(args.output).name != args.output or not args.output.endswith(".json"):
        parser.error("--output must be a plain JSON filename")
    return args


def prepare_work_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    try:
        resolved.relative_to(RUNTIME_ROOT)
    except ValueError as exc:
        raise ValueError("work directory must be a new child of repository runtime/") from exc
    if resolved == RUNTIME_ROOT or resolved.exists() or resolved.is_symlink():
        raise FileExistsError("work directory must be a new non-link child of runtime/")
    resolved.mkdir(parents=True)
    return resolved


async def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    work_dir = Path(args.work_dir)
    database = work_dir / "phase6-benchmark.db"
    store = SQLiteTaskStore(database)
    await store.initialize()
    transient = BenchmarkHandler("benchmark.transient", retry=True)
    terminal = BenchmarkHandler("benchmark.terminal", fail=True)
    effect = BenchmarkHandler("benchmark.effect", effect=True)
    registry = TaskHandlerRegistry((ValueTaskHandler(), transient, terminal, effect))
    envelope = TaskBudget(
        max_steps=100,
        max_wall_seconds=300,
        max_tokens=100_000,
        max_provider_requests=100,
        max_retries=10,
        max_tool_calls=100,
        max_concurrency=4,
    )
    validator = TaskPlanValidator(registry, envelope=envelope)
    scheduler = TaskScheduler(
        store=store,
        registry=registry,
        validator=validator,
        execution_enabled=True,
    )
    durations: list[float] = []
    failures = 0
    budget_violations = 0
    unauthorized_effects = 0
    terminal_counts: dict[str, int] = {}

    # Warm migration, statement, and filesystem caches; excluded from distribution.
    await _run_happy(scheduler, "warm-up")
    for index in range(args.samples):
        started = time.perf_counter()
        result = await _run_happy(scheduler, f"perf-{index}")
        durations.append((time.perf_counter() - started) * 1_000)
        if result.status is not TaskStatus.COMPLETED or result.usage.steps != 6:
            failures += 1
        if not result.usage.fits(result.graph.budget):
            budget_violations += 1

    for index in range(args.golden_scenarios):
        scenario = index % 5
        task_id = f"golden-{index}"
        if scenario == 0:
            result = await _run_dependency_failure(scheduler, task_id)
            expected = TaskStatus.FAILED
        elif scenario == 1:
            result = await _run_retry(scheduler, task_id)
            expected = TaskStatus.COMPLETED
        elif scenario == 2:
            result = await _run_approval(scheduler, task_id, effect)
            expected = TaskStatus.COMPLETED
        elif scenario == 3:
            result = await _run_cancel(scheduler, task_id)
            expected = TaskStatus.CANCELLED
        else:
            result = await _run_orphan_effect(scheduler, task_id)
            expected = TaskStatus.NEEDS_RECONCILIATION
        terminal_counts[result.status.value] = terminal_counts.get(result.status.value, 0) + 1
        if result.status is not expected:
            failures += 1
        if not result.usage.fits(result.graph.budget):
            budget_violations += 1
        if scenario in {2, 4} and effect.duplicate_effects:
            failures += 1

    events = await store.list_events(host_id="benchmark-host", task_id="perf-0")
    sequences = [event.sequence for event in events]
    if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
        failures += 1
    await scheduler.close()

    p50 = statistics.median(durations)
    p95 = _percentile(durations, 0.95)
    checks = {
        "performance_sample_count": len(durations) >= TARGETS["performance_samples"],
        "golden_scenario_count": args.golden_scenarios >= TARGETS["golden_scenarios"],
        "terminal_correctness": failures == TARGETS["failures"],
        "no_duplicate_effects": effect.duplicate_effects == TARGETS["duplicate_effects"],
        "no_unauthorized_effects": unauthorized_effects == TARGETS["unauthorized_effects"],
        "hard_budgets": budget_violations == TARGETS["budget_violations"],
        "p95_latency": p95 <= TARGETS["p95_ms"],
        "ordered_audit": bool(sequences),
    }
    result = {
        "schema": "jarvis.phase6.task-benchmark.v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="microseconds"),
        "passed": all(checks.values()),
        "targets": TARGETS,
        "metrics": {
            "performance_samples": len(durations),
            "golden_scenarios": args.golden_scenarios,
            "p50_ms": p50,
            "p95_ms": p95,
            "max_ms": max(durations),
            "failures": failures,
            "duplicate_effects": effect.duplicate_effects,
            "unauthorized_effects": unauthorized_effects,
            "budget_violations": budget_violations,
            "terminal_counts": terminal_counts,
        },
        "checks": checks,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "pid": os.getpid(),
            "max_concurrency": 4,
            "cloud_cost_usd": 0,
        },
    }
    if args.enforce and not result["passed"]:
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"Phase 6 benchmark failed: {', '.join(failed)}")
    return result


def _proposal(
    task_id: str, nodes: tuple[TaskNodeProposal, ...], *, retries: int = 0
) -> TaskPlanProposal:
    return TaskPlanProposal(
        objective=f"bounded benchmark {task_id}",
        owner="benchmark-owner",
        provenance=TaskProvenance(source_type="test", source_id="phase6-benchmark"),
        budget=TaskBudget(
            max_steps=len(nodes) + retries,
            max_wall_seconds=60,
            max_tokens=0,
            max_provider_requests=0,
            max_retries=retries,
            max_tool_calls=len(nodes) + retries,
            max_concurrency=4,
        ),
        deadline_at=datetime.now(UTC) + timedelta(seconds=30),
        nodes=nodes,
    )


async def _run_happy(scheduler: TaskScheduler, task_id: str):  # type: ignore[no-untyped-def]
    nodes = (
        TaskNodeProposal(id="root", handler="task.value", arguments={"value": 0}),
        TaskNodeProposal(
            id="a", handler="task.value", arguments={"value": 1}, dependencies=("root",)
        ),
        TaskNodeProposal(
            id="b", handler="task.value", arguments={"value": 2}, dependencies=("root",)
        ),
        TaskNodeProposal(
            id="c", handler="task.value", arguments={"value": 3}, dependencies=("root",)
        ),
        TaskNodeProposal(
            id="join", handler="task.value", arguments={"value": 4}, dependencies=("a", "b", "c")
        ),
        TaskNodeProposal(
            id="done", handler="task.value", arguments={"value": 5}, dependencies=("join",)
        ),
    )
    await scheduler.submit(
        host_id="benchmark-host", task_id=task_id, proposal=_proposal(task_id, nodes)
    )
    return await scheduler.run(host_id="benchmark-host", task_id=task_id)


async def _run_dependency_failure(scheduler: TaskScheduler, task_id: str):  # type: ignore[no-untyped-def]
    nodes = (
        TaskNodeProposal(id="fail", handler="benchmark.terminal", arguments={}),
        TaskNodeProposal(
            id="blocked", handler="task.value", arguments={"value": 1}, dependencies=("fail",)
        ),
    )
    await scheduler.submit(
        host_id="benchmark-host", task_id=task_id, proposal=_proposal(task_id, nodes)
    )
    return await scheduler.run(host_id="benchmark-host", task_id=task_id)


async def _run_retry(scheduler: TaskScheduler, task_id: str):  # type: ignore[no-untyped-def]
    nodes = (
        TaskNodeProposal(
            id=task_id,
            handler="benchmark.transient",
            arguments={},
            retry_limit=1,
        ),
    )
    await scheduler.submit(
        host_id="benchmark-host",
        task_id=task_id,
        proposal=_proposal(task_id, nodes, retries=1),
    )
    return await scheduler.run(host_id="benchmark-host", task_id=task_id)


async def _run_approval(scheduler: TaskScheduler, task_id: str, effect: BenchmarkHandler):
    nodes = (
        TaskNodeProposal(
            id="effect",
            handler="benchmark.effect",
            arguments={},
            idempotency_key=f"effect-{task_id}",
        ),
    )
    created = await scheduler.submit(
        host_id="benchmark-host", task_id=task_id, proposal=_proposal(task_id, nodes)
    )
    waiting = await scheduler.run(host_id="benchmark-host", task_id=task_id)
    if waiting.status is not TaskStatus.WAITING_APPROVAL or f"effect-{task_id}" in effect.effects:
        raise RuntimeError("effect ran without approval")
    await scheduler.bind_approval(
        host_id="benchmark-host",
        task_id=task_id,
        node_id="effect",
        grant_id=f"grant-{task_id}",
        expected_version=waiting.version,
    )
    result = await scheduler.run(host_id="benchmark-host", task_id=task_id)
    replay = await scheduler.run(host_id="benchmark-host", task_id=task_id)
    if replay != result or created.graph.plan_sha256 != result.graph.plan_sha256:
        raise RuntimeError("task replay changed terminal state or immutable plan")
    return result


async def _run_cancel(scheduler: TaskScheduler, task_id: str):  # type: ignore[no-untyped-def]
    nodes = (TaskNodeProposal(id="value", handler="task.value", arguments={"value": 1}),)
    await scheduler.submit(
        host_id="benchmark-host", task_id=task_id, proposal=_proposal(task_id, nodes)
    )
    return await scheduler.cancel(host_id="benchmark-host", task_id=task_id)


async def _run_orphan_effect(scheduler: TaskScheduler, task_id: str):  # type: ignore[no-untyped-def]
    nodes = (
        TaskNodeProposal(
            id="effect",
            handler="benchmark.effect",
            arguments={},
            idempotency_key=f"orphan-{task_id}",
        ),
    )
    created = await scheduler.submit(
        host_id="benchmark-host", task_id=task_id, proposal=_proposal(task_id, nodes)
    )
    bound = await scheduler.bind_approval(
        host_id="benchmark-host",
        task_id=task_id,
        node_id="effect",
        grant_id=f"grant-{task_id}",
        expected_version=created.version,
    )
    orphan = bound.nodes[0].model_copy(
        update={"status": NodeStatus.RUNNING, "attempts": 1, "started_at": datetime.now(UTC)}
    )
    injected = bound.model_copy(
        update={
            "status": TaskStatus.RUNNING,
            "nodes": (orphan,),
            "usage": TaskUsage(steps=1, tool_calls=1),
        }
    )
    await scheduler.store.save(
        injected,
        expected_version=bound.version,
        event_type=TaskEventType.NODE_STARTED,
        node_id="effect",
    )
    return await scheduler.run(host_id="benchmark-host", task_id=task_id)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction + 0.999999) - 1))
    return ordered[index]


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    work_dir = prepare_work_dir(args.work_dir)
    args.work_dir = work_dir
    try:
        result = asyncio.run(run_benchmark(args))
    except Exception as exc:
        print(f"Phase 6 benchmark failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    output = work_dir / args.output
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
