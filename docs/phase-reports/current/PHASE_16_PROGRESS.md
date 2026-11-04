# Phase 16 — Calendar and reminders

- Status: `blocked-external`
- Started / updated: 2026-11-01 / 2026-11-04
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: gpt-6-astra / ultra (recommendation only)
- Session start / five-hour stop: 2026-11-04 17:47 / 2026-11-04 22:47 America/Toronto

## Objective and scope

Inspect bounded events, detect conflicts, prepare unsent changes and reuse existing
owner-authored foreground reminder policy. Phase 7 dependency is complete. Phase 15
is independently blocked; no email access is required. Read historical expansion J,
security, execution protocol, full roadmap and current architecture before implementation.
Local foundation used an explicit `.ics` source; owner now selected Google primary calendar.
No ambient account discovery, automatic provider acquisition, provider mutation, invitations,
background worker, client scopes or model tools. Live acquisition requires applicable approval.

## Baseline and preservation

Baseline `fc0a54f`, branch `main`. Existing dirty provider/native/documentation changes
remain held, including shared architecture/security files. Snapshot exact bytes before edits.
Original initiation clock 2026-11-01 19:33, five-hour stop 2026-11-02 00:33 America/Toronto;
current resumption is recorded above and in the milestone log.
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

### Protected foreground auth preparation — 2026-11-04

Resume baseline `57b0709`, `main`; all 32 held paths and installed package inventory frozen
under ignored `runtime/phase16/auth/`. First captured clock 17:47 America/Toronto; five-hour
stop 22:47. Setup, new grant and private live read remain unapproved. This milestone implements
inactive local entry points and synthetic verification only; it grants no external authority.

Frozen acceptance before measurement: exact account/client/primary/two-scope protected grant;
separate Windows Credential Manager namespace; volatile access tokens; create refuses replacement;
foreground renewal refuses scope expansion/refresh-token rotation; local deletion rechecked before
cached use and after renewal. Adapt the published reviewed Gmail PKCE/loopback/token transport and
protected-secret protocol without changing or importing held Gmail credentials. Callback bounded
to 180 seconds, eight requests/four active handlers, strict state/Host/path/issuer/body validation;
token and verified-email responses <=16 KiB with five-second deadlines, no redirects/retries/proxies.
Verify exact account before persistence. No event acquisition during login.

Initial proof validates whole-second <=7-day window before client/store access, configures <=100
entries, and makes one identity GET plus one event GET within the existing five-second deadline
including foreground renewal. Prepare one unsent cancellation from the volatile observed snapshot,
without reacquisition; empty calendar reports preparation unavailable honestly. Only counts/booleans
leave the command. Synthetic matrix must cover denial/default-off, hostile callbacks, malformed
client/token/store/identity, scope/account/calendar binding, restart/deletion/rotation/cancellation,
Windows synthetic-only storage, full auth/read/prepare composition and private-output exclusion.
Full working/isolated gates and exact publication are recorded below; live acceptance stays pending.

Implemented explicit `google-auth`, `google-disconnect` and `google-proof`; normal runtime and
service factory stay default-off. Calendar-owned auth adapts published reviewed Gmail protocol
code so no held Gmail source/store must be changed or imported. Distinct grant namespace and
primary/two-scope blob binding, bounded login/renewal, no replacement/rotation and pre-access
CLI confirmations pass the synthetic matrix. Login performs no event read. Proof reuses one
volatile observed snapshot for conflict counting and unsent preparation; empty inventory reports
read success with preparation unavailable rather than claiming full acceptance.

Final focused matrix **288 pass**, 20.69 s. Frozen working source **2,263 pass**, three existing
skips, **86.89%** combined statement/branch coverage, 274.71 s. Initial isolated source based on
`57b0709` also passes **2,261**, three skips, **86.85%**, 273.56 s, but is superseded for publication
by a new exact-source run after concurrent Gmail publication `3acf8a4`. That independent commit
contains four Gmail compatibility/setup/report paths; no Calendar source changed. Original held
snapshot has 30 byte/deletion-identical paths and two separately edited Gmail docs. All original
held paths stay outside this Calendar patch; no native/provider/configuration edit is swept in.
Current root package inventory is restored exactly after locked base sync/audit and optional-extra
sync/audit. No dependency or lock changes. Final isolated publication source based on `3acf8a4`:
**2,264 pass**, three existing skips, **86.85%** combined coverage, 237.57 s. Working/isolated
count difference belongs to preserved held source; no test, assertion or floor waived. Existing
Starlette TestClient deprecation retained. Final installed-wheel smoke, Ruff/Mypy/audit and
isolated PWA **175**, desktop **72**, prototype **9** gates pass again. Frozen Calendar code
unchanged; documentation alone updated after these suites.

Reviewed 14 safe paths, nine frozen code/test hashes, 150 local links/anchors and 618 exact source
files. Built/installed publication wheel matches frozen Calendar source. Actual Windows synthetic
auth/storage/renewal/read/prepare/deletion smoke passes: five mocked transport requests, exact
create refuses replacement, cached acquisition denies deleted grant, synthetic credential removed.
**Zero real Google requests**, owner credentials, provider mutations, model calls or spend.
Ruff format/lint/Mypy (187 source files), root optional/base and Garmin locks/sync/audits, PWA
lifecycle/PCM **175**, desktop **72**, prototype **9**, history/exact-source secret scans pass.

Development receipts: first focused run caught the obsolete `login_implemented=false` plan
assertion; updated it to implemented-but-inactive. Hash-required wheel dependency install initially
inherited an unpinned root constraint (`filelock>=4.2.1`); reinstalling the exact hash-pinned exported
lock with `uv --no-config pip install --require-hashes` succeeds, without modifying locks or package
versions. Initial prototype wrapper lost a PowerShell environment-variable assignment; file-backed
explicit environment rerun passes all nine prototype cases. Review intentionally rejected a moved
HEAD before staging; created a new isolated worktree at `3acf8a4`, preserving the old tested source.
Dependent missing-directory scan failures receive no pass credit; subsequent nonempty exact-source
scan passes. Initial isolated prototype helper also used a missing relative evidence-helper path;
absolute helper-path correction passes nine cases. Existing CRLF/LF checkout differences explain
raw non-task source byte differences; all 430 non-held source/test/script paths match after newline
normalization, and all nine task code/test hashes match exactly. No production assertion, coverage
threshold or security/approval boundary weakened.

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

Initial frozen Google milestone source passes **2,145 tests**, three existing skips,
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

Post-review bound correction supersedes the initial Google source receipt: conservative
whole-second rounding could otherwise widen a fractional 31-day query by one second. A shared
query-window validator now enforces the original 31-day ceiling **before token acquisition**;
invalid rounded windows make zero credential/provider calls. Initial live proof will require
whole-second endpoints and <=7 days. Frozen final v2 focused matrix: **172 pass**, 11.98 s.
Final exact isolated source: **2,144 pass**, three existing skips, **86.81%**, 257.13 s.
Final working source: **2,146 pass**, three existing skips, **86.86%**, 225.93 s.
Ruff format/lint/Mypy and rebuilt/installed exact-wheel synthetic smoke pass again; PWA,
dependency and lock source remain identical to their passing receipts above.

The first v2 working run had 2,145 passes plus one unrelated `WinError 5` during atomic replace
of a synthetic voice-settings fixture. No Calendar assertion failed. A fresh ignored absolute
basetemp passes all 18 voice diagnostics, then the complete working gate passes in a separate
new ignored directory. No voice source, assertion, permission policy, coverage floor or gate
was changed or skipped. Failed-run evidence remains retained and is not a full pass.
Final source hashes use `tested-source.json`; `tested-source-v1.json` preserves earlier hashes.
Final coverage logs are `google-working-v2-fresh` / `google-isolated-v2` and corresponding
`working-coverage-v2-fresh.json` / `isolated-coverage-v2.json`. Documentation updated only after
final tests. Prepared read/renewal approval remains pending; no auth or live activity occurred.

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
grant persistence/renewal or identity/calendar read is authorized yet. The prepared review explicitly
includes distinct protected Windows refresh-grant storage and bounded foreground same-account
renewal; no background use, token replacement or scope expansion.
No owner grant, identity/calendar read or owner protected auth-store creation attempted. Gmail
approval persists within its existing email scope. Protected Calendar login/storage/renewal and
aggregate proof are now implemented for explicit trusted-local use, with synthetic-only testing;
normal runtime/bootstrap remains inactive. Approval is still required for external setup, new
consent/protected owner-grant creation and the selected live read. This follows root AGENTS.md's
consequential-action policy, not a routine repository permission gate. No Phase 17 work started.

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
login/store/foreground renewal and live CLI/proof implementation are present; no real invocation
or production configuration is inferred. Google primary/account selection is settled; scope/setup authority
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
mobile/physical acceptance remains unestablished. Original Google read-adapter milestone published
ten reviewed paths; the 2026-11-04 protected-auth milestone contains 14 reviewed paths. Source
hashes, exact tested/publication tree, refs and fresh CI are separately retained in ignored
`runtime/phase16/auth/` receipts and final handoff. No live/provider/phase completion inferred.
Next current phase:
**Continue Phase 16** with selected Google primary/same personal account, prepared setup
decision, actual protected auth and applicable live-read authority. Phase 15 remains
independently blocked; Phase 17 is not started by this report.
