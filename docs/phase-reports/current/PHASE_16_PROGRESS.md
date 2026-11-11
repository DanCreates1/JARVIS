# Phase 16 — Calendar and reminders

- Status: `blocked-external`
- Started / updated: 2026-11-01 / 2026-11-01
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: gpt-6-astra / ultra (recommendation only)
- Session start / five-hour stop: first captured clock 2026-11-01 19:33 / 2026-11-02 00:33 America/Toronto

## Objective and scope

Inspect bounded events, detect conflicts, prepare unsent changes and reuse existing
owner-authored foreground reminder policy. Phase 7 dependency is complete. Phase 15
is independently blocked; no email access is required. Read historical expansion J,
security, execution protocol, full roadmap and current architecture before implementation.
Use a local explicit `.ics` source pending provider selection; no ambient account discovery,
network, provider mutation, invitations, background worker, client scopes or model tools.

## Baseline and preservation

Baseline `fc0a54f`, branch `main`. Existing dirty provider/native/documentation changes
remain held, including shared architecture/security files. Snapshot exact bytes before edits.
Reuse installed Python/ZoneInfo/tzdata, typed Core models, CLI and existing proactivity
store/preview/activation/disable/delete/foreground runner. No new scheduler or credential store.
Primary contracts checked: RFC 5545, Python ZoneInfo, Google Calendar event-list/auth docs.
Provider selection is missing information, not permission for account access.

## Acceptance checklist

- [x] Bounded local ICS read and provider-neutral validated snapshots; explicit observed-at,
  export freshness unknown, stale after five minutes, no persisted calendar copy.
- [x] UTC, IANA timezone, exclusive all-day ends, daily/weekly finite recurrence, DST gap/fold,
  exclusions, cancellation and half-open busy conflicts. Unsupported recurrence fails closed.
- [x] Source size <=256 KiB, <=100 source events, <=366 instances/series, <=512 returned
  occurrences, <=31-day query, <=5-second read deadline, zero retries/network/cost.
- [x] Reject invalid/duplicate/unsupported input, links/non-local files, malformed provider
  results; cancellation and disable/re-enable reject obsolete results. No automatic cache/retry.
- [x] Exact-source-bound changes are volatile proposals only; source text grants no authority.
  Reminders prepare existing zero-effect proactivity proposals; activation remains trusted-local.
- [x] Synthetic restart, duplicate/cancel/privacy/ownership tests and working/isolated full gates.
- [ ] Authorized selected-source read evidence; missing local path or live provider/auth remains
  external input. Physical phone checks: **skipped by owner; unverified**.
- [ ] Runbook, safe publication, exact remote refs and fresh CI. No full phase closure without
  required live read evidence.

## Milestone log

1. Initiation: architecture/security/legacy references and current code/tools inspected.
   Calendar source selection requested; independent local adapter work continues.
2. Implemented used provider-neutral read contract, bounded local ICS adapter and explicit
   `calendar inspect`, `prepare` and `reminder` Core CLI entries. Calendar data stays volatile,
   outside models/PWA/cloud/memory. No source, store or credential discovery. No settings,
   scopes, migrations, dependency versions, production profiles or background controls changed.
3. Frozen synthetic oracle covers UTC/Toronto DST gap/fold, elapsed timed duration, exclusive
   all-day ends, finite daily/weekly recurrence, exclusions, cancelled/transparent conflicts,
   unsupported semantics, limits, malformed providers, actual five-second cancellation,
   disable/re-enable generations, file replacement/reparse/hardlink denial and private output.
   Actual reminder draft uses canonical store, exact activation, cross-host denial, restart,
   duplicate prevention, disable and deletion; zero effects/notification sends.
4. Review repaired ordinary-time reminder fold handling and clipped long all-day events to
   query windows before conflict comparison. Added regression for a 31-day event spanning
   fall-back (745 hours). Provider revalidation suppresses serializer diagnostics and maps
   error codes through a fixed allowlist; malformed provider data cannot disclose private
   values through warnings/errors. Focused final matrix: **88 tests pass**, 6.42 s before
   formatting-only allowlist normalization; both exact final-source full suites below include it.
5. Final exact frozen working source: **2,062 tests pass**, three existing skips, **86.75%**
   combined statement/branch coverage, 217.70 s. Exact isolated publication source:
   **2,060 tests pass**, three existing skips, **86.70%**, 204.38 s. Test-count difference
   belongs to preserved held working tests/provider source; none is swept into publication.
   Existing Starlette TestClient deprecation remains. Calendar module coverage:
   CLI/service 100%, parser 98.72%, models 97.70%, local-file adapter 91.36%.
6. Root/isolated Ruff format/lint and Mypy pass (183 source files). Locked root and Garmin
   sync/audits pass; root installed optional environment audit passes and its frozen package
   inventory remains unchanged. Working/isolated PWA lifecycle/PCM **175 tests**, desktop
   accessibility **72 cases**, prototype-text **9 cases** pass. No PWA source changed.
7. Fresh wheel built from exact publication source matches frozen module bytes. Installed into
   a separate hash-locked environment, it passes actual Windows synthetic read, prepare-cancel,
   new-service read, unchanged source and reminder-draft smoke. Zero owner credentials, network
   calendar reads, writes, model/cloud calls or cost. Synthetic file removed by harness.
8. Source review: **14 safe paths**, **140 local links/anchors**, **610 publication source files**,
   all **32 held paths** byte/deletion-identical. History, staged patch and exact publication
   source secret scans pass. Native manifests/provider edits/private/runtime artifacts excluded.

## Decisions, authority and blockers

No actual owner calendar, account, credential or provider profile inspected. Local source
selection does not grant external calendar scopes or writes. Any provider-specific auth/read
needs the selected exact provider/account/calendar and applicable authority. New grants and
external writes remain consequential boundaries. Existing email approval covers email only.

External blocker after independent work: source/provider question has no answer; no selected
owner `.ics` path or calendar provider/account/calendar/auth/read decision is available. No owner
source can be read or required live proof recorded without that input. Completed synthetic
implementation, recovery, release checks and prepared operator contract instead. Do not infer
Google selection from personal Gmail or inspect a connected calendar to guess. No Phase 17 work
started. Provider writes/invitations remain separately exact-approved future operations.

## Verification and measurements

Frozen matrix and limits above precede implementation and measurement. Ignored evidence under
`runtime/phase16/`: held/source/package hash inventories, `final-working-v2` and
`final-isolated-v2` logs/exit receipts, coverage JSON, isolated worktree, built wheel and smoke.
Working Python 3.11.9; isolated/wheel Python 3.11.16; uv 0.12.15; Node 24.20.0;
Windows 10.0.26300; installed tzdata 2026.3. No provider performance measured.

Commands through RTK: `uv lock --check`, isolated `uv sync --locked --link-mode copy`,
Ruff format/check, `mypy src`, complete strict pytest with fresh absolute ignored runtime
basetemps and unchanged 85% coverage gate; root optional/base/Garmin `python -m pip_audit
--strict`; Garmin lock/sync; Node lifecycle/PCM and desktop/prototype harnesses;
`uv build --wheel`, hash-locked wheel installation and synthetic smoke; Gitleaks history/
staged/exact-source checks, link/anchor/source-hash review and `git diff --check`.

Development-only runs are superseded by final v2 source receipts. Initial wrapper had a
PowerShell exit-code escaping error after passing tests; two later superseded suites were
stopped for final privacy hardening. They earn no final-source gate credit. A Node receipt
printer initially failed on a Unicode checkmark after successful tests; UTF-8 output fixed
and Node gate rerun. Initial wheel setup hit Windows incompatible-hardlink error 396;
hash-locked `--link-mode copy` repair passes. Wheel smoke uses rebuilt publication wheel,
not the earlier working-source wheel. No source/gate/threshold weakened to pass.

## Known limits, recovery and deferred scope

Local export freshness cannot prove current provider state. Unsupported ICS semantics reject
the whole snapshot; conflict absence never proves availability across missing sources. No remote
PWA calendar scope, chat integration or notifications. Existing reminder controls remain off.

## Publication and handoff

Task paths only; all 32 held paths preserved, including shared architecture/security and
email-resume changes. Ten application/test/ignore source hashes frozen before final full gates;
documentation alone updated afterward. Current architecture is unchanged; [calendar contract](../../CALENDAR.md)
records placement/lifecycle/recovery. Exact staged/publication agreement, root refs/push and
fresh exact-commit CI are separately checked during publication and retained in ignored receipt
plus final handoff. No phase completion or live provider acceptance inferred from publication.
Progress **14/19 primary receipts closed (~74%)**, unweighted management count;
mobile/physical acceptance remains unestablished. Next current phase: **Continue Phase 16**
with selected explicit source/provider and applicable live-read authority. Phase 15 remains
independently blocked; Phase 17 is not started by this report.
