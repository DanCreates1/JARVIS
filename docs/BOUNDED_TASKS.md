# Bounded Tasks

Phase 6 executes validated, durable task DAGs. Planning never grants authority. Execution is
disabled by default, foreground-only, host-scoped, and limited to handlers registered during
runtime composition.

## Safety contract

- A submitted JSON document is an untrusted `TaskPlanProposal`.
- Deterministic validation resolves handler kind, retry policy, resource charge, and approval
  requirement from the host registry. A plan cannot supply or override them.
- Cycles, unknown dependencies or handlers, excessive deadlines, unsafe retry settings, reused
  idempotency keys, and any host-budget expansion are rejected before persistence.
- Steps, wall time, tokens, provider requests, retries, tool calls, cloud cost, and concurrency are
  hard ceilings. Charges are reserved before dispatch. Cloud cost is fixed at `$0`.
- At most four independent read-only nodes may run together. Effect nodes always serialize.
- Effects require an idempotency key and an exact existing Phase 3 one-use grant. Task commands
  cannot create or approve that authority. Loopback API has no run, approval, or reconcile endpoint.
- Scheduler state is checkpointed before and after effects. An interrupted effect is never blindly
  replayed; it enters `needs_reconciliation` until handler-specific inspection proves outcome.
- No background scheduler, recursive agent creation, dynamic tool registration, arbitrary shell,
  or communication-send handler ships in Phase 6.

## Supported handlers

| Handler | Behavior | Authority |
| --- | --- | --- |
| `task.value` | Returns one bounded JSON value for graph composition/testing | Read-only |
| `research.report.inspect` | Reads metadata for an approved host-scoped Phase 5 report | Read-only; research stays untrusted |
| `computer.grant.execute` | Consumes one exact Phase 3 grant through existing broker | Effect; computer gates and exact grant required |

Handlers validate exact argument schemas. Outputs are bounded before persistence. Events and effect
checkpoints contain lifecycle metadata and reason codes, not arguments, report text, action payloads,
or raw results.

## Operator workflow

Create a UTF-8 JSON proposal. Set `deadline_at` to a current RFC 3339 UTC timestamp within both plan
and host wall-time limits.

```json
{
  "objective": "Inspect one approved research report",
  "owner": "local-operator",
  "provenance": {
    "source_type": "host",
    "source_id": "operator-plan-1",
    "untrusted": true
  },
  "budget": {
    "max_steps": 1,
    "max_wall_seconds": 300,
    "max_tokens": 0,
    "max_provider_requests": 0,
    "max_retries": 0,
    "max_tool_calls": 1,
    "max_cost_usd": 0,
    "max_concurrency": 1
  },
  "deadline_at": "2026-09-07T18:00:00Z",
  "nodes": [
    {
      "id": "inspect",
      "handler": "research.report.inspect",
      "arguments": {"report_id": "<approved-report-id>"}
    }
  ]
}
```

Preview and inspect without execution:

```powershell
uv run jarvis task create .\plan.json
uv run jarvis task list
uv run jarvis task show <task-id>
uv run jarvis task events <task-id>
```

After reviewing plan, budget, dependencies, and handlers, enable execution only in current trusted
operator environment. Every run remains an explicit foreground command:

```powershell
$env:JARVIS_TASK_EXECUTION_ENABLED = "true"
uv run jarvis task run <task-id>
```

Control and recovery commands:

```powershell
uv run jarvis task pause <task-id>
uv run jarvis task resume <task-id>
uv run jarvis task cancel <task-id>
uv run jarvis task bind-approval <task-id> <node-id> <existing-grant-id> --expected-version <n>
uv run jarvis task reconcile <task-id> <node-id>
uv run jarvis task export .\tasks-export.json
uv run jarvis task delete <task-id> --confirm-task-id <task-id>
```

Pause takes effect before next node. Resume only clears pause state; it does not start work.
Cancellation stops remaining read-only work, but an uncertain in-flight effect still requires
reconciliation. Export refuses overwrite. Deletion physically removes graph, outputs, events,
checkpoints, and approval bindings, leaving only a content-free tombstone. Existing database backup
copies remain separate artifacts and must be managed independently.

## Recovery

After process interruption, inspect task and events. Orphaned read-only nodes return to ready state
only when retry and remaining budgets allow. Orphaned `running`, `verifying`, or `compensating`
effects enter `needs_reconciliation`. Run explicit reconcile command; handler checks durable external
evidence such as a Phase 3 receipt. If no safe determination exists, no effect replay occurs.

To disable task execution for later starts:

```powershell
$env:JARVIS_TASK_EXECUTION_ENABLED = "false"
```

For computer effects, also run `uv run jarvis computer disable`; this rotates Phase 3 authority
epoch and prevents old grants from reviving.

## Verification benchmark

Use a new directory under ignored `runtime/`:

```powershell
uv run python scripts/phase6-task-benchmark.py `
  --work-dir runtime/phase6-task-benchmark-local `
  --samples 100 `
  --golden-scenarios 100 `
  --enforce
```

Gate requires 100 warm six-node DAG samples at p95 no more than 50 ms, 100 deterministic
failure/retry/approval/cancel/restart scenarios, expected terminal states, ordered audit, and zero
budget violations, unauthorized effects, or duplicate effects.
