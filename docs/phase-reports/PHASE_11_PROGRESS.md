# Phase 11 Advanced JARVIS Progress Report

Status: `in-progress`
Started: 2026-09-14
Updated: 2026-09-14
Active subphase: Phase 11B — complete; Phase 11C next
Recommended Codex model: `gpt-6-astra`
Recommended reasoning: `ultra`
Phase 11B session / five-hour stop: 2026-09-14T15:10:00-04:00 / 2026-09-14T20:10:00-04:00

## Objective

Extend the completed suggestion-only policy with an explicit foreground, single-owner runner. It
may evaluate due rules, claim one candidate, create a content-minimized local notification inbox
item, and prepare an exact Phase 6 task handoff. It must support snooze, dismiss, accept, cancel,
leases, checkpoints, restart recovery, and deduplication without a hidden daemon, cloud disclosure,
approval creation, automatic task execution, external notification adapter, or retained sensitive
preview.

## Baseline

- Git branch/HEAD: `main` at `2bc80b9b2b8622f3e435a3b45c63e6278a60ab44`, equal to
  `origin/main` after restoring the configured checkout from the existing upstream.
- Worktree state and preserved unrelated changes: clean; ignored `runtime/` evidence preserved.
- Relevant installed software/hardware/provider state: Windows 11 Home `10.0.26200`; ASUS TUF
  Gaming F15 FX506HF; 16,888,967,168 bytes RAM; Python 3.11.9; uv 0.12.5; Git 2.55.0;
  Gitleaks installed; Node 24.20.0. No Phase 11 credential or external service is required.
- Existing tests and failures: Phase 11A closeout reported 1,026 passed, 3 skipped, 85.01%
  coverage. Phase 11B restored the locked environment in this configured checkout; focused runner,
  CLI, policy, migration, and security suites pass with no product failure.
- Prior phase evidence: Phases 4, 5, 6, and 8 are complete. Phase 9 repository implementation is
  complete with live deployment externally blocked. Phase 10A is complete; vendor work is
  owner-deferred. Phase 6 remains foreground-only and has no scheduler daemon.

## Acceptance checklist

### Functional boundary

- [x] Strict contracts distinguish untrusted trigger proposals, exact trusted activation,
  durable active/disabled/expired lifecycle, and inert suggestion candidates.
- [x] Support one-time and daily wall-clock schedules plus allowlisted event triggers, exact IANA
  timezone, explicit expiry, quiet hours, and deterministic next-occurrence preview.
- [x] Host controls create/preview/activate/list/show/disable/delete without running a task or
  notifying a device.
- [x] Global default-off control and per-feature enablement deny evaluation unless both are active.

### Failure, time, restart, and recovery

- [x] Invalid timezone, nonexistent DST time, ambiguous DST fold without explicit choice, skew,
  replay, duplicate occurrence, stale proposal, expired rule/approval, disable, deletion, and
  restart fail closed.
- [x] Evaluation cannot outlive rule scope and cannot produce more than one candidate for one
  occurrence key.
- [x] Store initialization, upgrade, corruption rejection, optimistic conflict, host isolation,
  export, and transitive deletion behavior pass.

### Privacy, authority, and budgets

- [x] Model/research/source content cannot activate a trigger, change schedule/scope, mint an
  approval, raise budgets, select another host, or authorize execution.
- [x] Fixed host ceilings intersect every rule: at most 6 candidates/hour, 24/day, 5-minute clock
  skew, 30-day rule lifetime, 10 task steps, 2 provider requests, 5 tool calls, 10,000 tokens,
  one concurrent candidate, zero cloud cost, and no effect or communication authority.
- [x] Candidate/event/audit persistence contains identifiers, hashes, enum decisions, counts, and
  timestamps only—no prompt, notification body, private memory, research text, tool arguments,
  credentials, or model output.

### Performance, documentation, and release

- [x] Fixed benchmark runs at least 10,000 valid previews and 10,000 clock/authority abuse cases;
  valid p95 <= 5 ms, zero valid failures, zero false accepts, zero duplicate candidates, and RSS
  growth <= 50 MiB.
- [x] Policy/configuration, architecture, security, controls, migration, recovery, and phase status
  documentation match actual behavior.
- [x] Full lock/sync, Ruff, mypy, pytest/coverage, dependency audit, Gitleaks, doctor, package, and
  Git whitespace gates pass.

### Phase 11B durable runner and notification inbox

- [x] One explicit foreground tick atomically owns each candidate with a bounded lease, records
  before/after checkpoints, and never starts a hidden/background daemon.
- [x] Restart reclaims expired pre-delivery leases, but never redelivers a notification or repeats
  a task handoff after durable completion evidence.
- [x] Local inbox items contain generic metadata only. Sensitive/private title, memory, research,
  task arguments/output, provider content, and tool receipts are never copied into notification
  or checkpoint rows.
- [x] Snooze is exact, bounded, and quiet-hour/expiry aware; dismiss/cancel is terminal; disable
  prevents new evaluation and cancels unhanded work without deleting audit evidence.
- [x] Accept may bind only the exact host-owned Phase 6 task named by the activated rule, after
  checking current rule, candidate, task status, task deadline, and the intersection of Phase 11
  and Phase 6 budgets. It does not execute the task or create/bind an approval.
- [x] At most one handoff exists per candidate and one candidate owns a task. Duplicate ticks,
  concurrent claims, process restart, notification failure, offline sink, cancellation, and budget
  denial produce zero duplicate effects.
- [x] Fixed benchmark runs at least 10,000 runner operations plus 10,000 duplicate/restart/denial
  cases; warm p95 <= 10 ms, zero duplicate deliveries/handoffs/effects, and RSS growth <= 50 MiB.
- [x] Runner/inbox controls, migration, recovery, architecture, security, diagnostics, status,
  benchmark, full release, dependency, secret, package, and Git gates pass.

## Milestones

### Phase 11A Milestone 1 — threat model, contracts, and frozen policy

- Status: complete
- Changes: mandatory phase references and prerequisite evidence read; current Git/environment/test
  baseline captured; exclusions and quantitative gates frozen; strict contracts, deterministic
  policy, timezone/DST handling, and adversarial tests implemented.
- Evidence: 63 Phase 4/6 prerequisite tests pass; focused Phase 11A suite passes 24/24; local baseline
  HEAD equaled `origin/main`.
- Remaining: none for milestone.

### Phase 11A Milestone 2 — durable lifecycle and host controls

- Status: complete
- Changes: added migration 011, host-isolated transactional store, exact digest/version activation,
  global/per-feature controls, CLI lifecycle, diagnostics, exclusive export, and transitive delete.
- Evidence: restart, concurrency, duplicate, corruption, stale/expiry, host-isolation, export, and
  raw-SQL deletion tests pass. Doctor reports disabled suggestion-only policy and no runner.
- Remaining: none for milestone.

### Phase 11A Milestone 3 — abuse benchmark and closeout

- Status: complete
- Changes: added fixed abuse/performance benchmark; updated operator, architecture, security,
  setup, overview, roadmap, and playbook documentation; completed release gates.
- Evidence: 10,000 valid plus 10,000 abuse cases pass; repository suite passes 1,026 tests with
  85.01% coverage; dependency and secret scans pass; source/wheel build succeeds.
- Remaining: none for milestone.

### Phase 11B Milestone 1 — runner state, ownership, and frozen notification boundary

- Status: complete
- Changes: froze scope, failure matrix, data boundary, and targets; added migration 012, strict
  dispatch/inbox/checkpoint contracts, atomic leases, terminal states, bounded recovery, and
  content-minimized export/deletion integration.
- Evidence: concurrent ten-way claim produces one owner; expired lease recovery produces one inbox
  item; ten-attempt exhaustion fails terminally; raw rows exclude private proposal title.
- Remaining: none for milestone.

### Phase 11B Milestone 2 — foreground workflow and exact task boundary

- Status: complete
- Changes: added independently gated `proactive tick`, `inbox`, `runner-events`, `snooze`, `dismiss`,
  `cancel`, and `accept`; integrated quiet-time recheck and transitive disable cancellation.
- Evidence: duplicate tick produces no delivery; accept records one exact task/version/digest while
  leaving the task proposed with zero node attempts; wrong task and budget expansion fail closed.
- Remaining: none for milestone.

### Phase 11B Milestone 3 — benchmark, documentation, and closeout

- Status: complete
- Changes: added fixed runner/abuse benchmark; updated configuration, diagnostics, operator,
  architecture, security, setup, overview, roadmap, playbook, and progress documentation.
- Evidence: 10,000 inbox operations plus 10,000 duplicate claims pass at 0.4008 ms and 0.8379 ms
  p95, 0.676 MiB RSS growth, zero duplicates/handoffs/effects; full release gates pass.
- Remaining: none for milestone.

## Decisions

- Decision: Phase 11A produces inert suggestion candidates only.
- Reason: Phase 11B owns durable runner/task handoff/notifications; Phase 6 is foreground-only and
  model output is never authority.
- Alternatives: hidden daemon, automatic task execution, and notification sending are excluded.
- Reversible later: Phase 11B may consume the stable candidate contract behind fresh policy and
  authority checks.
- Decision: Phase 11B runner lifetime is owned by the explicit CLI tick; no scheduler or daemon.
- Reason: foreground lifetime gives visible control and preserves Phase 6/8 ownership boundaries.
- Alternatives: browser push, service installation, periodic process, and remote delivery deferred
  to Phase 11C rather than simulated.
- Reversible later: Phase 11C may add an approved adapter behind the durable dispatch boundary.

## Verification evidence

```text
rtk uv lock --check
PASS: 119 packages resolved

rtk uv run python -m pytest --no-cov -q <Phase 4/6 prerequisite suites>
PASS: 63 passed in 2.52 s

rtk uv run python -m pytest --basetemp runtime/pytest-phase11a-full-rerun
PASS: 1026 passed, 3 skipped, 85.01% coverage in 54.11 s

rtk uv run ruff format --check .
PASS: 320 files already formatted

rtk uv run ruff check .
PASS: all checks passed

rtk uv run python -m mypy src
PASS: no issues in 133 source files

rtk uv run python -m pip_audit
PASS: no known vulnerabilities

rtk gitleaks detect --source . --redact --no-banner
PASS: no leaks found

rtk uv run jarvis doctor
PASS: JARVIS ready; proactivity disabled, zero features, no runner

rtk uv build
PASS: source distribution and wheel built

Phase 11B restored-checkout release gates:

rtk uv lock --check
PASS: 119 packages resolved

rtk .venv/Scripts/python.exe -m ruff format --check .
PASS: 325 files already formatted

rtk .venv/Scripts/python.exe -m ruff check .
PASS: all checks passed

rtk .venv/Scripts/python.exe -m mypy src
PASS: no issues in 136 source files

rtk .venv/Scripts/python.exe -m pytest --basetemp runtime/pytest-phase11b-full-03
PASS: 1,038 passed, 3 skipped, 85.08% coverage in 50.84 s

rtk .venv/Scripts/python.exe -m pip_audit --strict
PASS: no known vulnerabilities

rtk gitleaks detect --source . --redact --no-banner
PASS: 39 commits and 4.54 MB scanned; no leaks found

rtk .venv/Scripts/python.exe -m jarvis doctor
PASS: JARVIS ready with workspace-local private runtime path; policy, runner, and handoff disabled

rtk uv build
PASS: source distribution and wheel built
```

## Benchmarks

- Samples: 10,000 valid plus 10,000 abuse.
- Cold/warm: warm policy evaluation; restart/DST behavior tested separately.
- p50: valid 0.0173 ms; abuse 0.0093 ms.
- p95: valid 0.0205 ms; abuse 0.0101 ms; target <= 5 ms passes.
- Errors/failures: zero valid failures, false accepts, duplicate candidates, task executions,
  notifications, retained candidate content, and cloud disclosures. RSS growth 1.008 MiB.
- Hardware/runtime/model/device versions: Windows laptop; Python 3.11.9; deterministic clock and
  synthetic trigger fixtures; no model, provider, network, or device.
- Relevant settings: global proactivity default off; zero cost; one candidate concurrency.

Phase 11B runner benchmark:

- Samples: 10,000 valid active-inbox reads plus 10,000 duplicate/restart claim attempts.
- p50: valid 0.2526 ms; abuse 0.5482 ms.
- p95: valid 0.4008 ms; abuse 0.8379 ms; target <= 10 ms passes.
- Errors/failures: zero valid failures, false claims, duplicate notifications, unexpected events,
  task handoffs, or effects. RSS growth 0.676 MiB.
- Hardware/runtime: Windows laptop, Python 3.11.16, SQLite WAL, deterministic clock, no model,
  provider, network, task execution, or device.

## Security and privacy

- Threats tested: forged/model activation, budget escalation, host crossover, replay, skew, stale and
  duplicate occurrence, invalid/gap/fold times, disable/expiry/restart, concurrent evaluation/claim,
  lease crash/exhaustion, duplicate handoff, wrong task, and authority-field injection.
- Data boundaries: candidate, dispatch, local inbox, and runner audit persist control metadata only.
- Permissions/approvals: exact trusted host activation only; suggestion and handoff are not approval;
  pre-bound grants are rejected and the runner never invokes a task/effect.
- Audit/retention/deletion: content-free lifecycle and runner audit; exclusive export; transitive
  rule/activation/candidate/dispatch/inbox/event deletion with content-free tombstone verified.
- Secret scan: full working-tree Gitleaks pass.

## Blockers

- None for Phases 11A–11B local implementation.

## Known limits and deferred scope

- Background/service evaluation is deliberately absent. Remote notification transport,
  multi-device ownership, approved adapters, and long-duration usefulness evaluation remain
  Phases 11C–11D.

## Recovery and rollback

- Disable runner and handoff gates first, then the global policy gate. Stop the invoking foreground
  process; inspect inbox/runner events; disable exact rules to cancel unhanded state; export before
  deletion. Additive migrations 011/012 must not be removed from an existing database.

## Final handoff

- Final status: Phases 11A–11B complete; aggregate Phase 11 remains in progress.
- Files changed: proactivity contracts/policy/store/migration, configuration, CLI, diagnostics,
  benchmark/tests, operator/security/architecture/setup/roadmap/playbook documentation, and report.
- Next recommended phase: Phase 11C multi-device ownership and approved scoped adapters.
- Commit/push status: completed under standing repository authorization; exact commit is repository
  `HEAD` and is pushed to `origin/main`.
