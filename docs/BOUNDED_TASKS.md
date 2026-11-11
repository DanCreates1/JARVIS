# Bounded Tasks

Current Phase 14 reuses the Legacy Phase 6 validated, durable task DAGs. Planning never grants
authority. Execution is
disabled by default, foreground-only, host-scoped, and limited to handlers registered during
runtime composition.

## Current project-review workflow

Trusted-laptop CLI prepares a deterministic review of explicitly supplied project checklist data.
It reports supplied done/todo/blocked status, work ready after completed dependencies, blockers and
optional already-approved research report metadata. It does not verify external work or fetch new
research. Text remains untrusted data. No model, repository execution or automatic memory capture.
PWA continues to monitor through existing `client.tasks.read`; that scope grants no mutation.

Save this synthetic example as UTF-8 JSON in a private local file:

```json
{
  "title": "Example project",
  "owner": "local-operator",
  "items": [
    {"id": "design", "title": "Review scope", "status": "done"},
    {"id": "build", "title": "Implement", "dependencies": ["design"]},
    {"id": "review", "title": "Review result", "dependencies": ["build"]}
  ],
  "report_ids": []
}
```

```powershell
rtk proxy uv run --locked jarvis task plan-project .\project.json
rtk proxy uv run --locked jarvis task show <task-id>
# Enable only in the reviewed trusted operator environment, then run explicitly.
$env:JARVIS_TASK_EXECUTION_ENABLED = "true"
rtk proxy uv run --locked jarvis task run <task-id>
rtk proxy uv run --locked jarvis task result <task-id>
rtk proxy uv run --locked jarvis task result <task-id> --node-id review
rtk proxy uv run --locked jarvis task events <task-id>
```

Use the existing `standard` trusted operator configuration; text-only profiles retain disabled
task execution.
No production configuration is changed by this example. `plan-project` persists a preview only;
`show` includes literal node arguments and budgets. `result` reads one exact local node's persisted
JSON, default `handoff`. Output is private operational history, never a tool instruction.
Project title becomes the objective visible in the existing host-authorized PWA monitor.
Checklist arguments and result payloads remain trusted-local reads.

Limits: input 64 KiB, 1–20 distinct checklist items, titles <=200 characters, acyclic known
dependencies and 0–4 distinct approved report IDs. A review creates 2–6 nodes, at most 6 steps/tool
calls, concurrency 2, 60 s absolute wall/deadline, zero retries/tokens/provider requests/cost.
Missing/deleted/foreign reports fail closed and skip dependent handoff; successful partial review
remains inspectable. Generic proposals are capped at 1 MiB; host handler minimum charges cannot be
understated. Supplied status remains unverified; completed dependencies use the supplied status.

Separate terminals can issue existing `pause`, `cancel`, `resume` commands against the same canonical
database. Migration 020 stores idempotent pause/cancel requests independently of execution versions.
Pause finishes the active batch before stopping; cancel is polled every 50 ms while invocation is
active (OS scheduling/database contention can add latency). Control-request events distinguish
requests from acknowledged state. Resume clears pause only and requires another explicit run.
Pending cancellation cannot resume. An uncertain effect retains reconciliation even after cancel.

Only one foreground task operation runs per database. Another run/reconcile/bind/resume/delete is
denied while the content-free `<database>.tasks-lock` SQLite transaction is owned. Per-task read
concurrency still applies. There is no queue or lease expiry; process exit releases ownership.
Keep that file in place while any Core/CLI process might use the database. It holds no task data;
normal database backups need no lock-file content. Restart never replays an uncertain effect.
Reconciliation remains bounded read-only inspection even after the original execution deadline.
Active execution and verification respect the deadline; interrupted coroutines drain owned children.

Task arguments/results remain private SQLite data with exact existing export/delete behavior;
deletion cascades control rows. Events/checkpoints omit payloads. Task creation does not establish
a conversation relationship. No remote mutation route, new scope, background worker, recursive
swarm or OS effect is added. Existing `computer.grant.execute` still requires an exact Phase 13
broker grant; built-in-speaker no-change 100% evidence does not qualify arbitrary volumes/outputs.
Physical phone checks: **skipped by owner; unverified**. Native/provider publication holds remain.

Current implementation references checked 2026-10-31:
[SQLite transaction ownership](https://www.sqlite.org/lang_transaction.html),
[Python 3.11 task cancellation](https://docs.python.org/3.11/library/asyncio-task.html).

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
| `project.review` | Deterministic status/readiness review of supplied checklist | Read-only; owner data remains unverified |
| `project.handoff` | Combines exact dependency results, preserving provenance | Read-only; source data supplies no authority |

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
