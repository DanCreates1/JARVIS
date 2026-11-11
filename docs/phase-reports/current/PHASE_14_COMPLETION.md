# Phase 14 — Bounded tasks and project workflows

- Status: `complete`
- Started / updated: 2026-10-31 / 2026-10-31
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: gpt-6-astra / ultra (recommendation only)
- Session start / five-hour stop: 2026-11-01 01:10 UTC / 2026-11-01 06:10 UTC

## Objective and scope

Reuse the immutable DAG validator, one durable foreground scheduler, trusted-local CLI and
authenticated read-only PWA task views. Add a useful deterministic project-review workflow over
explicit owner-supplied checklist data and optional already-approved research report metadata.
Plan/inspect/run/pause/cancel/resume must work across separate operator processes. No background
worker, remote control scope, model planner, recursive agents or new effect authority.
Dependencies: current Phases 7 and 13 complete. Action adapter remains exact-grant-only.

## Baseline and preservation

- `main` at `f2348b0`; 28 held provider/native paths captured by hash and patch in ignored
  `runtime/phase14/`. Shared edits will be recomposed for publication; held blobs remain private.
- Legacy Phase 6 foundation and F14/F15 contracts read. Existing handlers: bounded JSON value,
  approved research metadata, exact computer grant. Existing controls use process-local events;
  multiple foreground schedulers lack cross-process ownership. Repair before acceptance.
- Preserve prototype-text, dependency locks, $0, authentication, privacy and exact approval.
  Phase 13 volume evidence remains built-in-speaker no-change 100% only; prior headphone failure
  and arbitrary-percentage/all-output limits remain. No new live audio/app/media effects planned.

## Acceptance checklist

Frozen before implementation and measurement:

- [x] Project review: 1–20 supplied items, explicit done/todo/blocked status, dependency order,
  at most four approved research references, deterministic readable handoff, no invented facts.
  At most 6 nodes, 6 tool calls, 60 s wall/deadline, concurrency 2, zero retries/tokens/provider
  requests/cost. Invalid/oversized/extra-field input fails before persistence.
- [x] Existing immutable validator plus malformed/cycle/unknown handler/over-budget cases.
- [x] Separate-store/process pause/cancel/resume, duplicate run exclusion, process interruption,
  restart reconciliation, ownership denial and zero duplicate/unauthorized effects.
- [x] Deadline bounds active dispatch/verification; external cancellation leaves no live child work.
- [x] >=100 six-node warm DAGs, p95 <=50 ms; >=100 existing golden recovery scenarios;
  all expected states, zero budget violations, unauthorized/duplicate effects, exactly $0.
- [x] Current real Windows trusted-local CLI/Core/SQLite synthetic project workflow and recovery;
  existing PWA read projections, no mutation route/scope or guessed conversation relationship.
- [x] Full working and isolated publication gates, >=85% branch coverage, audits, secrets,
  documented recovery and reviewed source-only publication with fresh exact CI.
- [x] Phone checks **skipped by owner; unverified**; physical/native/MVP acceptance unestablished.

## Milestone log

1. Baseline/contracts audited; acceptance frozen. Current SQLite transaction and Python asyncio
   documentation checked. No dependency adoption or production setting change.
2. Implemented `task plan-project`, literal argument preview and `task result`; deterministic
   readiness/blocked/done review plus optional 0–4 stored-report inspections and dependent handoff.
   All input remains data. Generic plans are limited to 1 MiB and host minimum charges; duplicate
   idempotency keys are rejected. Maximum escaped 20-item checklist fits the 32 KiB review output
   and existing 100 KiB handoff ceiling. No automatic model, research fetch or effect.
3. Migration 020 adds durable idempotent controls. Separate SQLite transaction ownership fences
   simultaneous foreground run/reconcile/bind/resume/delete across processes. No expiring lease
   can take over a live owner. Cancel remains requested until acknowledged; uncertain effects
   survive cancel and failed compensation. Deadlines bound active invocation/verification;
   a second deadline check after async validation prevents dispatch after expiry.
   recovery inspection remains available after expiry. External cancellation drains children.
4. Real Windows subprocess tests prove pause/cancel propagation, duplicate-run exclusion, killed
   runner release, orphan read failure and effect reconciliation without redispatch. Synthetic
   fixtures perform no actual Windows broker effect. Existing 10 ms effect-timeout test was
   made deterministic with 100 ms timeout / 500 ms fixture work; uncertainty/no-replay assertions
   remain unchanged. Concurrency regression fixed without weakening its four-reader assertion.
5. Working intermediate full suites: 1,746 / 3 skips / 86.20% / 164.41 s, then 1,748 / 3 skips /
   86.44% / 185.88 s. Isolated intermediate: 1,749 / 3 skips / 86.40% / 174.89 s. Later output-bound
   correction and new maximum-input test were followed by final full gates below; earlier runs are not
   substituted. Retained Starlette TestClient deprecation and existing platform/capability skips.
6. Initial current benchmark: 100 warm six-node DAGs, p50 24.02 ms, p95 30.87 ms, max 34.58 ms;
   100 golden scenarios, zero failures/budget violations/duplicate or unauthorized effects, $0.
   A later run concurrent with two full suites failed `p95_latency`; legacy harness raises before
   writing its report, so no numeric percentile is invented. Final idle evidence is recorded below;
   unchanged 50 ms target. No failed run is counted as a pass.
7. Root lock/sync, clean base/restored optional audit and Garmin lock/sync/audit pass. Exact
   starting 97-package optional inventory restored. PWA lifecycle/PCM: 173 pass; default desktop
   harness: 72 cases across eight profiles; prototype-text harness: 9 pass. Empty-state doctor:
   all 14 checks pass in working and isolated source, without owner-store access.
8. Prepared 21-path publication source at baseline `f2348b0`; 2 shared files independently
   recomposed from original held snapshots. Other 26 held paths retain exact bytes/deletion.
   Current source sweep: 589 files, 142 local document links/anchors, no secret findings.
   Final completion links/source sweep and publication checks follow below.

## Decisions, authority and blockers

Existing repository authority covers implementation, local synthetic verification and safe GitHub
publication. Remote mutation boundary deliberately excluded; local controls satisfy selected scope.
No external blocker identified. No new OS effect approval inferred from Phase 13 evidence.

## Verification and measurements

Final exact code/config/test hashes were frozen before both full suites. No application,
configuration or test source changed afterward. Working source uses CPython 3.11.9; isolated
publication source uses CPython 3.11.16; uv 0.12.15, Node 24.20.0, Windows build 26300.

| Gate | Working source | Isolated publication source |
| --- | --- | --- |
| Full strict tests / branch coverage | 1751 pass / 3 existing skips / 86.44% / 181.88 s | 1752 pass / 3 existing skips / 86.40% / 168.15 s |
| Format / lint / Mypy | Pass; 173 source files | Pass; 173 source files |
| Root base / restored optional / Garmin audits | Clean; 97 starting package versions restored exactly | Clean base and fresh locked Garmin environment |
| PWA lifecycle / PCM | 173 pass | 173 pass |
| Desktop accessibility / prototype regression | 72 cases / 8 profiles; prototype 9 cases pass | 72 cases / 8 profiles; identical public assets |
| Empty-state doctor | 14/14 pass | 14/14 pass |
| 100 six-node warm DAGs | p50 22.16 ms; p95 29.40 ms; max 32.99 ms | p50 22.55 ms; p95 29.79 ms; max 36.83 ms |
| 100 golden recovery scenarios | All expected states; zero failures, duplicate/unauthorized effects or budget violations; $0 | Same fixed gates pass; $0 |

Final application acceptance includes 28 project/workflow cases and 4 real subprocess recovery/
control cases, plus existing validator, scheduler, broker, ownership, PWA and security suites.
The isolated suite retains the published provider contract, hence one additional legacy provider
test. Three existing local platform/capability skips and the TestClient deprecation remain visible;
none counts as physical acceptance. Benchmark runs above were sequential after full suites ended;
the earlier concurrent-run p95 failure remains recorded. Frozen phase thresholds and benchmark
scenarios remain unchanged.

Commands: `rtk proxy uv lock --check`; `uv sync --locked --link-mode copy` through RTK; locked
Ruff format/check, `python -m mypy src`, `python -m pytest --basetemp <new ignored runtime path>`,
`python -m pip_audit`, Garmin lock/sync/audit, Node lifecycle/PCM/accessibility, synthetic doctor,
`phase6-task-benchmark.py --samples 100 --golden-scenarios 100 --enforce`, Gitleaks history and
exact-source/staged scans, local link/anchor review and `git diff --check`, all through RTK.
Raw artifacts stay under ignored `runtime/phase14/`. No owner store or production policy loaded.

## Known limits, recovery and deferred scope

Foreground execution only. Supplied checklist status is owner data, not verification of external
work. Approved report metadata is not fresh research. Disable execution to prevent later starts;
inspect events and reconcile uncertain effects without replay. No automatic retention purge.

## Publication and handoff

Task-only publication: 21 reviewed paths, including 2 independently recomposed shared files.
All other published source remains identical to `f2348b0`. The 28 held paths remain preserved:
26 untouched paths retain exact bytes/deletion state, while bootstrap and architecture preserve
held changes by inverse recomposition. Both locks, prototype baseline, native manifests, provider
changes and private/runtime/generated artifacts remain excluded from this phase's publication.
The original 97-package optional environment is restored exactly and audited. Source/link/secret/
whitespace checks cover the final publication tree; no unsafe artifact is staged.

Commit/tree, HEAD/tracking/live-remote agreement, held preservation and fresh exact-commit Windows
CI are checked after publication and reported in the final handoff. Earlier CI is not substituted
for the later SHA. A failed publication/CI gate requires repair under existing authority.

Selected Phase 14 acceptance is complete: bounded supplied-project review, trusted-local controls,
durable recovery and authenticated read-only monitoring. No new Windows effect, remote scope,
background worker, production activation or physical/native acceptance is inferred.
Phone checks remain **skipped by owner; unverified**.

Progress: **14/19 primary receipts closed (~74%)**, unweighted management count, not code/effort or
mobile MVP acceptance. Next current phase is **Phase 15 — Email**, not started; provider selection,
current official auth/API/terms review and applicable private-read authority precede live access.
Preserve provider/native holds and endpoint-specific volume limits; no automatic next-phase work.

Final full gates and sequential idle benchmarks above supersede intermediate runs for closure.
