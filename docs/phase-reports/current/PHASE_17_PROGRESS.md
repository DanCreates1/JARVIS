# Phase 17 — Background scheduling and proactivity

- Status: `implemented-closeout-pending`
- Started / updated: 2026-11-08 / 2026-11-08
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: gpt-6-astra / ultra (recommendation only)
- Session start / five-hour stop: 2026-11-08 19:33 EST / 2026-11-09 00:33 EST

## Objective and scope

Explicit trusted-local opt-in to bounded background schedule evaluation, using the existing
proactivity policy, canonical SQLite store, runner leases and generic local inbox. Suggestions
remain inert. No task execution, provider acquisition, event subscriptions, model/cloud calls,
OS notifications, external sends, service installation, startup registration or production
activation. Stop before Phase 18. Phase 14 is complete; Phase 15/16 external blockers are independent.

## Baseline and preservation

- `main` at `3452f9b`, initially tracks `origin/main`. All 28 held provider/native/document paths
  captured as exact hashes, copies and patch in ignored `runtime/phase17/` before edits.
- Current Phase Execution, full master roadmap, current architecture, security, legacy Phase 11
  evidence and current Phase 14/16 reports inspected. Historical foreground code is reusable,
  not evidence of current background acceptance. No owner database/profile/credential inspected.
- Python locked environment, uv 0.12.15, Node 24.20.0, Gitleaks 8.30.1. Locks remain unchanged.

## Acceptance checklist

Frozen before implementation or measurement:

- [x] Exact host/config/version-bound local review and activation; global, runner and per-feature
  gates all required. Default off. One canonical worker owner with expiring fenced lease.
- [x] One caller-owned process; absolute approval expiry and monotonic lifetime <=3,600 s;
  poll 1–60 s, <=3,600 durable tick reservations, <=500 rule scans/tick, 5 s tick timeout;
  no catch-up burst or event/provider polling. Stop observation <=2 s on idle unlocked store.
- [x] Existing one-time/daily IANA schedules, quiet hours, DST gap/fold, stale/expiry, rate/attention
  budgets; no early suggestion. Missing/suspended/late occurrences do not replay.
- [x] Concurrent owners, lease loss, killed/restarted process, stop/re-enable generation,
  feature/config revocation, cancellation, persistence failure and stale token deny without
  duplicate inbox items or unauthorized activity. Transactions fence candidate and inbox writes.
- [x] Candidate/inbox/control/audit metadata excludes private titles, previews, provider content,
  task payloads and credentials. Zero task/tool/provider/model calls, external sends and cost.
- [x] Fixed simulation >=30 virtual days and >=1,000 decisions; 100% oracle agreement,
  zero false/quiet/disabled/duplicate suggestions. >=100 recovery/denial incidents.
- [x] Real Windows isolated synthetic worker soak >=1,800 s and >=1,800 ticks;
  tick p95 <=50 ms, process CPU <=5% of one logical core, RSS growth <=50 MiB;
  no production controls or owner state touched. Removal leaves normal on-demand Core usable.
- [x] Full working and exact isolated-publication gates; >=85% combined branch/statement coverage,
  root/base/restored optional/Garmin audits, PWA/prototype checks, installed-wheel smoke,
  secrets/links/whitespace review.
- [ ] Safe publication and fresh exact-commit CI; development and local acceptance complete.
- [x] Manual phone checks **skipped by owner; unverified**. No physical/native/MVP acceptance.

## Milestone log

1. Baseline preserved; scope, budgets, lifecycle and quantitative targets frozen. Python 3.11
   asyncio cancellation/monotonic deadlines and SQLite immediate-transaction documentation checked.
2. Implemented local preview/enable/run/status/stop, generation-bound consent and one renewable
   90-second worker lease in additive migration 021. Existing runner is reused with no task store,
   handoff or external sender. Candidate/claim/inbox/control transitions fence old tokens inside
   SQLite transactions. Early creation/dispatch and actual quiet-time crossing fail closed.
3. Focused policy/runner/CLI/security matrix: 69 pass before the final additional process/failure
   fixtures. Current tests also cover actual killed Windows subprocess, new-consent recovery,
   bounded timeout/drain, rollback on persistence failure and live policy revocation. No new
   dependency, configuration field, profile, scope, service or production control.
4. Fixed policy oracle: 30 virtual days, four timezones, 1,000/1,000 correct decisions, precision/
   recall 1.0, 120 useful positives, zero false/quiet/disabled activity or budget breach. Current
   worker incidents: 100 scenarios, 400/400 expected duplicate-owner/stale/replay denials.
   Two-tick development run is explicitly not full-soak acceptance. Full real-clock soak running.
5. Root/base/restored optional/Garmin and isolated audits pass; original installed package
   inventory restored exactly. Working/isolated PWA lifecycle/PCM 175, desktop 72 and prototype
   9 pass. Exact publication wheel installed in a separate hash-locked environment passes default
   denial, synthetic rule/consent/two-tick inbox/stop/removal. All 28 held paths remain exact.
6. Initial complete working suite: 2,308 pass, three existing skips, 87.04%, plus one failure:
   migration inventory still expected 1–20. Updated it to require 1–21 and explicitly assert the
   new control table; all 14 migration tests pass. Initial isolated run also hit 23 fixture setup
   errors because its explicit basetemp parent did not yet exist. A fresh verified ignored root
   basetemp fixes that preparation error. Both full gates rerunning; no production source changed.
7. Development harness cleanup initially left an open SQLite connection on Windows; explicit
   connection closing fixes it. Wheel dependency setup initially inherited an unpinned root UV
   constraint incompatible with hash mode; isolated `uv --no-config pip install --require-hashes`
   installs the exact exported lock and smoke passes. Failed receipts remain; no gate weakened.
8. V2 full working/publication suites pass 2,309/2,310 tests, three existing skips each,
   87.04%/87.00% coverage. Post-review found that a backward clock jump before process restart
   could widen the initial wall-derived deadline. Claim now rejects time before consent creation,
   process startup checks time again after claim, and remaining monotonic lifetime is independently
   capped at 3,600 s. Four regression cases include 1 s, 301 s and one-day rollback plus the
   claim-to-start gap. Focused final matrix: 50 pass, 23.22 s. Fresh V3 complete suites and real
   >=1,800-tick soak started; earlier receipts do not substitute for current source. Rebuilt V3
   wheel installed and synthetic lifecycle smoke passes; no dependency source changed.
9. V3 full suites pass 2,313/2,314 tests, three existing skips each, 87.04%/87.00%. Final CLI
   review tightened enablement to require the full preview SHA-256 in `--expected-digest` as
   well as the short typing phrase; same-prefix/wrong-full-digest regression denies activation.
   Seven CLI tests and the rebuilt/installed V4 wheel smoke pass. Only CLI and its test changed:
   all worker/runner/store/model/SQL/benchmark bytes used by the running V3 soak are unchanged.
   V4 complete suites rerun against the final whole publication source. No source changed after
   that freeze; subsequent edits are documentation only.
10. Final V4 full working suite: **2,313 pass**, three existing skips, **87.05%**, **297.28 s**.
    Exact isolated publication: **2,314 pass**, three existing skips, **87.00%**, **281.29 s**.
    Extra publication test belongs to the preserved original provider contract, not a gate waiver.
    Ruff format/lint and Mypy (191 source files) pass for both. Existing TestClient deprecation
    and three platform/capability skips remain. Native/physical acceptance is not established.
11. Final current-worker soak passes **1,800 ticks in 1,824.9724 s**, three expected synthetic
    inbox items, tick p95 **8.3644 ms**, average CPU **0.8254% of one logical core**, RSS growth
    **9.3867 MiB**. Fixed simulation is 1,000/1,000 correct; 100 worker incidents produce 400/400
    expected denials. Zero duplicates, private previews, provider/tool/task/effect/external-send
    activity or cloud cost. Exact rule/worker-plan removal, temporary-state deletion and ordinary
    synthetic on-demand Core turn/deletion pass afterward. Old pre-clock-repair soak remains
    retained as superseded evidence, not current acceptance. No owner state or production controls.

## Decisions, authority and blockers

Owner authorizes development and isolated verification only. Real production activation and all
external notifications explicitly excluded. No such approval requested or inferred. Reuse existing
runner and scheduler contracts; no second task scheduler, detached daemon or automatic handoff.
No new dependencies, provider scopes, device enrollment or real calendar/email acquisition.

## Verification and measurements

Final V4 automated source gates and real-clock V3 worker soak pass; publication CI pending.
Raw evidence stays under ignored `runtime/phase17/`. Worker/runner/store/model/SQL/benchmark
hashes agree exactly between the V3 soak source and V4 publication; the V4-only change is the
trusted-local CLI full-digest check plus its regression. Complete V4 suites and installed wheel
exercise that final CLI. No production worker or owner store was used.
Reviewed task-only source currently includes 19 paths, 14 frozen code/test/migration/script hashes,
147 local links/anchors and 629 exact publication files. Built wheel matches changed module and
migration bytes. History/exact-source secret scans and whitespace checks pass. Current Core
architecture already requires this opt-in/one-owner boundary; its held document remains unchanged,
and [worker contract](../../BACKGROUND_PROACTIVITY.md) records implementation and recovery.

## Known limits, recovery and deferred scope

Laptop must be awake/reachable. Stop/revoke before inspecting or removing an opt-in. No catch-up
for stale occurrences. Phase 18 remains unstarted. Prior external/latency/volume/provider holds
remain unchanged.

## Publication and handoff

Safe task-only source contains 19 reviewed paths and 14 frozen code/test/migration/script hashes.
All 28 held paths remain byte/deletion-identical and excluded. Both dependency locks, provider/
native changes and current architecture document remain unchanged. Original optional installed
package inventory is restored exactly. Full working/isolated source gates, installed exact wheel,
simulation, soak, recovery/removal, audits and source/link/secret/whitespace review pass.
Repository workflows contain CI only; no deployment or notification step is introduced.
Task-only commit/push and fresh exact-commit CI remain the closeout gate, recorded separately in
ignored receipts and final handoff. Progress remains 14/19 primary receipts closed (~74%) until
that gate closes. No Phase 18 implementation, production activation or external notification.
