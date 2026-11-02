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
Local foundation used an explicit `.ics` source; owner now selected Google primary calendar.
No ambient account discovery,
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

### Google Calendar selection — 2026-11-01

Owner answered the pending source question: **Google Calendar**. This supersedes the missing
provider choice below; exact account/calendar target, new calendar OAuth grant and authorized
live read remain pending. No connected calendar or credential is inferred. Resume baseline
`1a1f7b6`; prior exact-commit CI passed. All 32 held paths and installed package inventory
snapshotted under ignored `runtime/phase16/google/`. First captured resume clock 20:18
America/Toronto; five-hour stop 01:18 on 2026-11-02.

Frozen independent milestone: inactive, default-off Google Calendar read adapter using a
trusted-host access-token port, consumed through existing CalendarService. Exact verified
account and explicit `primary`/owned-calendar selector; no calendar/account discovery, ambient
Gmail tokens, protected store/login creation or automatic auth fallback. Proposed narrow scopes
are `calendar.events.owned.readonly` plus `userinfo.email` for exact verified-account binding.
Shared/non-owned calendars remain unavailable under this contract. Target choice requested as
information; selecting Google does not approve a grant or private read. Owner subsequently
selected **primary calendar, same personal Google account as Phase 15**. Exact mailbox/client
file remain private local inputs; no account profile or credential discovery is needed to guess them.

Pre-measurement limits: one foreground five-second operation including token acquisition and
two GETs (verified-email identity <=16 KiB, one expanded event page <=1 MiB/512 entries), at most
31 days, zero retries/redirects/pagination/watch/sync/poll/write/model/cloud/cost. Return no partial
snapshot. Explicit unknown upstream freshness; stable exact-source revisions for prepare/re-read.
Test HTTP error/size/deadline/cancel/re-enable, malformed/duplicate JSON, account/scope mismatch,
ownership, recurrence instance/exception/cancellation, timezone/DST/all-day dates, overlap,
restart, stale proposal and absence of private diagnostic output before any live acceptance.
Prepare current scope/setup/retention/rollback review for later exact owner decision.

Implemented Google read port/service factory with default-off token acquisition and no production
auth source, client settings or startup activation. Account/calendar/scopes/expiry checked before
network; verified-email GET precedes event page. No arbitrary endpoint selection, proxies,
redirects, pagination, cookie reuse, compressed data or raw errors. Bounded factory can enforce
the proposed initial 100-entry proof ceiling. Service disable propagates to adapter generation,
preventing event GET after an obsolete identity response. `calendar google-plan` exposes the
concrete inert proposal; [setup review](../../GOOGLE_CALENDAR_SETUP.md) records authority/data limits.
Frozen Google/local/reminder focused matrix passes **171 tests**, 11.81 s before final formatting;
new Google subset contains 83 tests. Exact complete-source verification follows below.

Exact frozen Google milestone source passes **2,145 tests**, three existing skips,
**86.86%** combined statement/branch coverage, 264.13 s in working checkout. Isolated
publication source passes **2,143 tests**, three existing skips, **86.81%**, 258.56 s.
Existing Starlette TestClient deprecation retained; two-test difference belongs to held
working source. Ruff format/lint and Mypy pass (184 source files). Root optional/base and
Garmin locks/sync/audits pass, with no dependency/lock change; frozen root installed package
inventory unchanged. PWA lifecycle/PCM **175**, desktop **72**, prototype **9** pass.

Fresh exact publication wheel installed into the separate hash-locked environment passes
synthetic read/prepare/disable, 25-hour all-day DST interval and inactive plan CLI. Four
synthetic HTTP requests, **zero real Google requests**, owner credentials, provider writes,
model calls or cost. Five source hashes frozen before complete suites; documentation alone
updated afterward. Reviewed **10 safe paths**, all **32 held paths** preserved, **613** source
files and current local links/anchors; history/staged/exact-source secret scans and whitespace
checks pass. Current evidence is under ignored `runtime/phase16/google/` plus prefixed
`google-working`/`google-isolated`/PWA gate receipts in `runtime/phase16/`.

Development corrections: synthetic HTTP responses initially used an already-consumed mock
body; corrected to actual asynchronous byte streams without weakening production parsing.
Oversize fixture IDs were shortened to avoid Windows temp-path limits. An initial helper-copy
shell quoting error was corrected using a file-backed script; only the subsequent nonempty
staged/exact-source scans count. No production source changed after the final freeze.

### Local foundation — prior verified work

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

Historical local-foundation blocker: source/provider question had no answer; no selected
owner `.ics` path or calendar provider/account/calendar/auth/read decision is available. No owner
source can be read or required live proof recorded without that input. Completed synthetic
implementation, recovery, release checks and prepared operator contract instead. Do not infer
Google selection from personal Gmail or inspect a connected calendar to guess. No Phase 17 work
started. Provider writes/invitations remain separately exact-approved future operations.
Current Google/primary selection supersedes that missing-choice blocker. Required new calendar
OAuth setup/grant and actual authorized read remain unavailable; provider selection does not
approve them. [Prepared review](../../GOOGLE_CALENDAR_SETUP.md) groups Calendar API/client,
two scopes, exact primary target and one <=7-day/100-entry proof. No external setup, new login,
grant, identity/calendar read or protected auth-store creation attempted. Gmail approval persists
within its existing email scope. Protected calendar login/storage/renewal remains a subsequent
implementation milestone; current source cannot activate a live calendar by itself.

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
Google adapter remains inactive without a trusted approved token source. Protected calendar
login/store/renewal and live CLI/proof implementation are not yet present; the inert plan
reports this explicitly. Google primary/account selection is settled; scope/setup authority
and actual authenticated read proof remain external requirements. Do not reuse Gmail auth or
connected-chat credentials to bridge that boundary. [Prepared setup](../../GOOGLE_CALENDAR_SETUP.md)
states scope breadth, data minimization and remaining implementation/recovery requirements.

## Publication and handoff

Local-foundation publication `1a1f7b6` passed exact-commit CI. Its task paths preserved all
32 held paths, including shared architecture/security and
email-resume changes. Ten application/test/ignore source hashes frozen before final full gates;
documentation alone updated afterward. Current architecture is unchanged; [calendar contract](../../CALENDAR.md)
records placement/lifecycle/recovery. Exact staged/publication agreement, root refs/push and
fresh exact-commit CI are separately checked during publication and retained in ignored receipt
plus final handoff. No phase completion or live provider acceptance inferred from publication.
Progress **14/19 primary receipts closed (~74%)**, unweighted management count;
mobile/physical acceptance remains unestablished. The Google milestone publishes only its ten
reviewed paths; source hashes, exact tested/publication tree, refs and fresh CI are separately
retained in the ignored Google publication receipt and final handoff. Next current phase:
**Continue Phase 16** with selected Google primary/same personal account, prepared setup
decision, protected-auth implementation and applicable live-read authority. Phase 15 remains
independently blocked; Phase 17 is not started by this report.
