# PWA MVP 3 — Garmin integration and acceptance

- Status: `in-progress` — M3A/M3B complete; M3C phone acceptance pending
- Started: 2026-10-07
- Updated: 2026-10-09
- Active subphase: M3C — health-scoped enrollment decision and physical-iPhone acceptance
- Recommended Codex model/reasoning: `gpt-6-astra`, `xhigh`
- Current session stop: 2026-10-09T23:00:00-04:00 (conservative five-hour ceiling)

## Objective

Connect the owner's existing Garmin session to the protected Core bridge, then prove scoped
read-only PWA refresh and recovery on the physical iPhone. M3A static compatibility review is
complete. Requested M3B saved-session import/read is covered by the owner's 2026-10-08 simplified
confirmation policy. Protected import and live Core evidence passed on 2026-10-08. New login/MFA, enrollment,
revocation or private HTTPS route changes need confirmation if not already explicitly approved.

## Historical M3A baseline

- Branch/HEAD: `main` at `7186da8`, tracking `origin/main`.
- Observed worktree differs from the stated clean baseline: `mobile/package.json` and
  `mobile/package-lock.json` contain existing dependency updates. Preserve them; unrelated native
  dependency changes are outside M3A review and publication.
- Core: Python 3.11.9. Isolated bridge: Python 3.12.14, locked `garminconnect==0.3.16`,
  `keyring==25.7.0`. Local standalone connector source: 0.3.17, separate Python 3.14.7 environment.
- Phase 8 historical physical-iPhone chat/install/enrollment/reconnect evidence remains intact.
  Standalone report evidence does not prove a protected Core session or phone Garmin acceptance.
- No real tokens, health reports, account identifiers, or Credential Locker entries were opened.
  Standard `jarvis doctor` opened local runtime stores for installation diagnostics; no stored
  conversation or health content was inspected.
- Default `uv` cache access denied in sandbox; a checkout-local ignored cache allows lock checking.

## Acceptance checklist

- [x] M3A: compare 0.3.17 saved-session schema with pinned 0.3.16 bridge and record sources.
- [x] M3A: prepare offline, explicit-file, bounded import with synthetic tests; execute no import.
- [x] M3A: remove ambient token-store/Python overrides from bridge execution.
- [x] M3A: prevent late Garmin responses from rendering after logout or re-enrollment.
- [x] M3A: focused and applicable repository quality/security gates pass.
- [x] M3B: requested saved-session import/read covered by simplified confirmation policy.
- [x] M3B: obtain exact existing local JSON source path and perform protected import.
- [x] M3B: prepare and execute a flags-only Core evidence command.
- [x] M3B: sanitized Core summary from protected session; no private values in evidence.
- [ ] M3C: recorded owner authority for initial/recovery browser tickets adding `client.health.read`, risk 1; reuse that approval within its scope.
- [ ] M3C: physical-iPhone Wi-Fi/cellular, refresh, stale/error, reconnect/restart, logout/revocation.
- [ ] MVP 3 closure: full repository/sidecar security gates and CI pass.

## Milestones

### M3A — review and local preparation

Complete after local gates. Both upstream versions
serialize `di_token`, `di_refresh_token`, `di_client_id`.
Do not use `Garmin.login(path)` as a compatibility probe or importer: it can contact Garmin,
refresh authentication, read profile/settings, and write back to the source store.

- Added strict offline import, explicit local paths, reparse/size/identity checks, duplicate/schema
  rejection, and existing-session refusal. Source remains unchanged; no actual import executed.
- Core bridge now uses `-I`/minimal child environment, null-device `NETRC`, saved-session Requests
  `trust_env=False`, suppressed vendor logging, token rotation persistence after failed reads,
  rate-limit stopping and allowlisted activity types/timestamps with generic names.
- Service timeout/cancellation kills/reaps the child; malformed output errors suppress private
  exception chaining. Existing 300-second cache/60-second throttle remain tested.
- PWA clears health synchronously on logout/new connection/active 401, aborts obsolete fetches,
  and guards result/error rendering by session and request generation. Old/invalid/future timestamps
  and refresh errors retaining metrics carry explicit stale labels. Shell cache is `v5`.
- CI installs the same pinned Node.js 24.20.0 used locally so lifecycle tests execute.

Static sources:
[0.3.16 client](https://github.com/cyberjunky/python-garminconnect/blob/c3c1c0d66579696e3843cba20f985c66069140b9/garminconnect/client.py),
[0.3.17 client](https://github.com/cyberjunky/python-garminconnect/blob/218e72ca5459e014435fc2d94fd18bd601fa0c14/garminconnect/client.py),
[Requests netrc authentication](https://requests.readthedocs.io/en/latest/user/authentication/#netrc-authentication),
[Python isolated mode](https://docs.python.org/3.12/using/cmdline.html#cmdoption-I),
[Windows drive classification](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getdrivetypew).

### M3B — protected session and Core summary

Complete on 2026-10-08. The single saved-session JSON found in the local standalone connector's
default token directory was selected explicitly for the reviewed offline importer. Requested
saved-session import/read and normal renewal needed no additional approval. Core now owns the
protected session; do not repeat import or refresh the independent source copy. Expired/revoked
tokens require confirmation for new Garmin login/MFA if not already approved. No automatic fallback.

2026-10-08 live M3B acceptance:

- Resumed `main` at `6adc5cf938e190304abfa1a1063bba20bd6f21ed`; both existing native package
  edits remained untouched. No competing Core/standalone reader was running.
- Located the single local source by filename/metadata, without printing its contents. The
  explicit-file importer succeeded into the empty Windows Credential Locker, offline. Source
  size and displayed last-write time remained unchanged. No new login/MFA was needed.
- Ran exactly one `scripts/garmin_core_check.py --read` call with normal Windows/network access.
  Result: `status=pass`, `schema_valid=true`, `fresh=true`, `activity_bound=true`; all six
  availability flags were true: steps, resting heart rate, sleep, stress, Body Battery, activities.
  Evidence contains no health values, dates, activity names, account identifiers, or tokens.
- This accepts the protected Core service path. It does not accept a health-scoped phone request
  or the physical-iPhone Wi-Fi/cellular/recovery matrix. M3C remains open.
- No Garmin source was deleted, no token revoked, no browser ticket issued, and no private route
  changed. Historical preparation evidence below remains historical, not a current blocker.

Current M3B closure verification, 2026-10-08:

| Check | Evidence |
| --- | --- |
| Core / sidecar lock check and locked sync | Passed; 119/20 resolved and 69/16 installed packages; no dependency changes |
| Ruff format / lint | Passed; 408 formatted files |
| Mypy | Passed; 164 source files |
| Core / sidecar strict dependency audits | No known vulnerabilities |
| Full repository gate | 1,439 passed / 3 existing optional skips; 85.59% coverage; 138.61s |
| Gitleaks history | Passed; 89 commits, no leaks |
| Local `jarvis doctor` | Passed; existing loopback/private defaults retained |
| Native package preservation | Both pre-existing file hashes unchanged; excluded from this publication |

The existing Starlette/httpx deprecation warning remains. The PWA Node lifecycle test ran in the
full gate. Normal Windows access was used for protected import, live saved-session read, process
inventory and full tests; no Windows security policy changed. The existing private Serve route
matches its exact ownership marker, HTTPS authority and sole loopback backend; Funnel is disabled.
No Serve configuration was changed. Current CI evidence is recorded after safe documentation
publication; full MVP 3 closure still requires M3C.

2026-10-08 local preparation before the confirmation-policy change:

- Resumed Desktop `main` at `33943e8589d96334d5afbdaeff829877004d12ad`; M3A gates and CI
  passed per owner handoff. Two pre-existing native package edits remain unchanged and excluded.
- Reviewed bridge/service execution with an independent read-only review. No source token,
  Locker entry, account identifier or health value was opened. Exact absolute JSON source and
  fresh import/read authority were requested; no dependent operation has run.
- Added `scripts/garmin_core_check.py`: explicit `--read`, exactly one Core service call,
  no private values or exceptions in output, no report files, no login/import/enrollment fallback.
  Emits only schema/freshness/activity-bound booleans and category availability. Pass requires
  today, a timezone-aware nonfuture fetch no older than 300 seconds, and an available category.
  Partial/empty sections cannot be represented as complete health coverage.
- Saved-session authentication may read Garmin profile/settings and rotate protected tokens;
  requested authority explicitly includes those operations. Six health methods remain the fixed
  allowlist. No standalone 14-category report or health-scoped browser request is used in M3B.
- Core/standalone readers must be stopped before import/check. No concurrent-import guarantee is
  added; Core remains sole session owner afterward. Login/MFA and M3C enrollment stay gated.

Local verification for this preparation:

| Check | Evidence |
| --- | --- |
| Core / sidecar lock and locked sync | Passed; 119/69 and 20/16 resolved/installed packages checked |
| New flags-only helper | 25 synthetic cases passed; no real service, sockets or credentials |
| Import / bridge / service / API scope | 104 synthetic cases passed |
| Ruff format / lint | Passed; 408 formatted files |
| Mypy | Passed; 164 source files |
| Core / sidecar dependency audit | No known vulnerabilities |
| Gitleaks history | Passed; 87 commits, no leaks |
| Full repository gate | 1,439 passed / 3 existing optional skips; 85.59% coverage; 102.89s |

Node.js 24.20.0 remains installed; real PWA lifecycle tests ran in the full gate. The existing
Starlette/httpx deprecation warning remains. Initial helper harness socket guards also blocked
Windows asyncio's local socketpair; synthetic immediate-coroutine execution removes that OS
dependency without allowing real service/network calls. The first sandbox Core focused run stalled
on Windows asyncio and was stopped; all 104 unchanged focused cases passed with normal OS access.
Sidecar interpreter checks and public PyPI audits likewise required sandbox escalation. No Windows
security policy or gate was weakened. No live Garmin operation has run; M3B remains blocked.

Full verification command (strict flags and unchanged 85% coverage threshold):

```powershell
rtk uv --cache-dir runtime/uv-cache-mvp3 run python -m pytest -q --basetemp runtime/pytest-m3b-full-20261008-a -o cache_dir=runtime/pytest-cache-m3b-full -o 'addopts=--strict-config --strict-markers --cov=jarvis --cov-report=term:skip-covered --cov-fail-under=85'
```

Safe preparation source is covered by standing commit/push authority. Native package edits remain
excluded. A new preparation commit's CI is a separate remote gate, never inferred from local tests.

2026-10-08 confirmation-policy update:

- Owner removed routine authorization prompts and retained confirmation only for important actions.
  Updated root instructions, playbook and active M3B documentation. This supersedes the previous
  per-session import/read gate above; it does not erase prior verification evidence.
- Requested M3B work includes selected-file offline import into an empty protected store, bounded
  Core reads, incidental authentication profile/settings reads and normal same-account renewal.
  Missing exact source path is an information request. No token contents should be provided in chat.
- `--read` remains an explicit live-command selector; helper help no longer asks for approval.
  Software authentication, scope enforcement, privacy filtering and protected storage are unchanged.
- New login/MFA, replacing/revoking tokens, enrollment/scopes, costs, destructive actions,
  deployment and private disclosure beyond the intended service remain important decisions when
  not already approved. Do not repeat completed M3A preparation while awaiting a source path.
- Safe preparation `c9e39c6d9abe76aa0e871987852ebfa93b3af09d` was published and
  [CI run 37841774497](https://github.com/DanCreates1/JARVIS/actions/runs/37841774497) passed.
  No live Garmin import/read has run. Two native package edits remain preserved.
- Policy/CLI wording verification: 25 existing synthetic helper cases passed in 0.31s; Ruff
  format/lint and whitespace passed. Independent source review found no material contradiction
  or application security change. No broader local suite rerun was needed for documentation and
  message-only changes; the prior full gate above remains accurately dated evidence.

### M3C — health-scoped phone acceptance

Pending fresh enrollment authority and physical-device evidence. Existing PWA enrollments cannot
gain `client.health.read` implicitly. Do not run the Phase 8D launcher against an unowned route.

2026-10-08 preparation: resumed loopback Core behind the verified existing owned private route,
without changing Serve. Local and private-HTTPS `/app/` checks passed; a real unauthenticated
Garmin API request was denied; the listener remains loopback-only. The exact eight-scope,
risk-ceiling-1 ticket command and bounded physical-phone matrix are in [PWA_GARMIN.md](../PWA_GARMIN.md).
One grouped enrollment/phone-key-erase/new-test-revocation/recovery decision was requested;
no ticket was minted and no device/scope record changed. Phone acceptance remains unexecuted.

2026-10-08 M3C continuation at `7c73e60512fca60203107f44be8973bb1ede02de`:

- Verified the prior chat's grouped decision remained unanswered. The current owner request asks
  to resolve it; the same initial/recovery ticket, prior-phone-key erase, same-iPhone enrollment
  and first-new-test-device revocation decision remains pending. No approval is inferred from
  elapsed time, a handoff prompt, or the request to finish. No ticket was minted or device changed.
- Read-only SQLite scope metadata shows zero active browser records with `client.health.read`.
  No names, IDs, public keys, session credentials, tickets, or health values were output.
- Current existing route ownership, sole loopback listener, disabled Funnel, and local/private
  HTTPS `/app/` checks passed. The exact `/api/v1/client/garmin` route denied an unauthenticated
  request. Serve configuration and ownership marker were preserved.
- [Baseline CI 37866951256](https://github.com/DanCreates1/JARVIS/actions/runs/37866951256)
  passed both jobs at the exact baseline SHA. This evidence does not cover subsequent repairs.
- Both existing native package edits remain preserved. Their independent production audit still
  fails (15 moderate / 45 high / zero critical); the existing native publication hold applies.
  They remain excluded from PWA publication and do not substitute for PWA acceptance.
- Repaired the actual pending-network logout path before acceptance: local key and health/device/
  task/chat views clear without awaiting Core; ticket/composer fields also clear. Session generation
  guards prevent obsolete bootstrap, subscription, status, tasks, SSE, chat, notification and
  startup continuations from restoring cleared state. Reconnect aborts the old stream and shows
  `Connecting`/`Connection failed` instead of preserving a misleading `Connected` indicator.
- Replacement enrollment/connection waits for previous identity writes, local cache/worker cleanup,
  bounded remote DELETE and stale-bootstrap CSRF cleanup. Each network attempt has a five-second
  deadline; a bootstrap body followed by revocation can require two bounded attempts. This keeps
  a late successful cookie/site-data-clearing response ahead of replacement credentials. Server
  CSRF/cookie/site-data behavior remains unchanged. Shell cache and asset references advance to `v6`.
- Offline local erase does not establish remote revocation when bootstrap's cookie was accepted but
  its CSRF body was unavailable. Session expiry or separately approved exact-device revocation is
  still required for that server boundary. The physical matrix must verify the actual iPhone behavior.
- Independent source review and 24 real Node synthetic lifecycle cases passed. Focused PWA API/
  browser identity checks passed: 7 tests, one existing Starlette/httpx warning, 1.51s. The new cases
  exercise unresolved DELETE, delayed response bodies, replacement serialization, timeout/abort,
  late UI restoration and failed reconnect. They contain synthetic data only.

Physical evidence remains distinct from synthetic/local checks:

| Physical iPhone gate | Result | Evidence required |
| --- | --- | --- |
| Device/runtime identification | Not reported | iPhone model, iOS version, Home Screen PWA/Safari, shell version; no device/account identifier |
| Initial health-scoped enrollment | Not run | Approved exact eight scopes, risk 1; enrollment/session lifecycle flags |
| Wi-Fi Garmin and public-fixture chat | Not run | Owner pass/fail; bounded sections and at most three activities |
| Cellular Garmin and public-fixture chat | Not run | Owner pass/fail with Tailscale connected |
| Network loss and stale/error presentation | Not run | Owner pass/fail; no queued offline chat |
| Tailscale recovery | Not run | Owner pass/fail after reconnect and explicit refresh |
| Core restart with same phone identity | Not run | Owner pass/fail; existing private Serve route retained |
| New test device revocation | Not run | Next explicit protected refresh denies and clears health within 5 seconds |
| Offline logout | Not run | Owner pass/fail; health/identity UI and local key cleared without Core response |
| Recovery enrollment and final refresh/chat | Not run | Recovery ticket issued only when phone ready; owner pass/fail and lifecycle flags |

No screenshot, private health value, account identifier, ticket or credential belongs in evidence.
Desktop/browser simulation and Core lifecycle metadata cannot prove these physical-phone rows.

Current M3C local release verification, 2026-10-08:

| Check | Evidence |
| --- | --- |
| Core / sidecar lock check and locked sync | Passed; 119/69 and 20/16 resolved/checked packages |
| Ruff format / lint | Passed; 408 formatted files |
| Mypy | Passed; 164 source files |
| Core / sidecar strict dependency audits | No known vulnerabilities |
| Node lifecycle / focused PWA API and security | 24 / 7 passed; synthetic fixtures only |
| Full repository gate | 1,439 passed / 3 existing optional skips / one existing warning; 85.59% coverage; 95.81s |
| Gitleaks history / whitespace | Passed; 90 baseline commits, no leaks |
| Local `jarvis doctor` | All checks passed; loopback defaults retained |
| Existing private HTTPS assets | Shell, script and worker serve matching `v6`; no route changes |
| Native package preservation | Existing hashes retained; both files excluded from publication |

Full gate used locked Python 3.11.9 and Node.js 24.20.0 with unchanged strict markers/configuration
and 85% coverage threshold. Fresh ignored workspace basetemp was verified before use:

```powershell
rtk uv --cache-dir runtime/uv-cache-mvp3 run python -m pytest -q --basetemp runtime/pytest-m3c-full-20261008-a -o cache_dir=runtime/pytest-cache-m3c-full -o 'addopts=--strict-config --strict-markers --cov=jarvis --cov-report=term:skip-covered --cov-fail-under=85'
```

Normal Windows/network access resolved sandbox Python discovery, asyncio, audit DNS and `uv`
trampoline path failures; no gate or OS policy was weakened. No source token discovery/import,
live Garmin service check, enrollment or revocation was repeated. Safe recovery source is covered
by standing commit/push authority; new publication CI is a separate gate, reported after push.
MVP 3 remains incomplete until the physical rows pass after the pending owner decision.

2026-10-09 M3C evidence continuation at `ed4ee18f3bcc30868a1f021b6629fd0cb1441801`:

- Local HEAD, tracking `origin/main`, and the live upstream `main` ref match the recovery repair.
  [CI run 37878722474](https://github.com/DanCreates1/JARVIS/actions/runs/37878722474)
  completed successfully at that exact SHA; both Windows quality and secret-scan jobs passed.
  The dated local full-suite evidence above remains 1,439 passed, three existing optional skips,
  and 85.59% coverage. No application source changed during this continuation.
- Read the prior M3C chat's owner messages and pending grouped decision. No approval answer or
  physical-phone result was found. Surfaced that same initial/recovery ticket, prior-phone-key
  erase, same-iPhone enrollment and first-new-test-device revocation decision for resolution.
  Do not mint either ticket until approved and the phone is ready; recovery uses its own later
  five-minute window. Do not infer approval from this finish request or an unanswered question.
- Both unrelated native package candidates retain their original SHA-256 hashes:
  `mobile/package.json`: `a9bb3741e6b3066deb4adf8091189e35a6837d57be3ba48460e056d75b7d8342`;
  `mobile/package-lock.json`: `d0da737979bc3f2ba193939f7d16a6889d934173bfe9a0f8180a4286c1433cf9`.
  Their existing native audit/publication hold remains; neither is part of PWA staging or CI.
- Initial read-only readiness check found the exact owned Serve route and marker intact,
  Tailscale online, matching private HTTPS authority, Funnel disabled, and no backend listener.
  Resumed only Core with its reviewed exact origin and loopback port. Windows PowerShell refused
  the ignored local `.ps1` before execution; running the reviewed startup commands directly left
  execution policy unchanged. Diagnostics passed before startup. The sole listener is
  `127.0.0.1:8765`; local/private HTTPS shell, script and worker serve matching `v6`; an
  unauthenticated request to `/api/v1/client/garmin` is denied. No launcher Run/Stop action,
  Serve route change, firewall change or new exposure occurred.
- Fresh read-only SQLite metadata reports zero active unexpired health-scoped browsers and zero
  pending unexpired health tickets. Only counts were returned; no names, IDs, keys, credential
  hashes or stored content were output. Existing route readiness proves no physical-phone row.
- Prepared direct owner-terminal ticket handoff: after approval and phone readiness, use a
  separate interactive no-profile PowerShell window and `rtk proxy uv` with child-only
  `RTK_TEE=0`, `RTK_RECALL=0`, `RTK_TELEMETRY_DISABLED=1`. Do not capture ticket stdout in tool
  output, files, transcripts, clipboard automation or chat. Current PowerShell transcription
  policies are disabled. No ticket window was opened or ticket minted. Separate-window behavior
  is documented by [Microsoft](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/start-process?view=powershell-5.1);
  installed RTK 0.45.0 raw-output suppression is verified in its
  [tagged source](https://github.com/rtk-ai/rtk/blob/v0.45.0/src/core/tee.rs).
- Physical matrix rows above remain unexecuted. Model/iOS/runtime details and owner pass/fail
  observations are still missing. No ticket, key, device record or Garmin session was changed,
  no source was rediscovered/reimported, and no live health value was opened for this audit.

This continuation changes only the progress report. The current whitespace and secret gates
cover that documentation checkpoint; the full application gate above and exact-SHA CI remain
dated baseline evidence. MVP 3 stays incomplete pending the grouped approval and physical matrix.

## Security and privacy

Treat tokens as credential material and Garmin responses as untrusted private health data.
Import must preserve source files, perform no network request, and store only in Windows
Credential Locker. Core and phone receive bounded health views, never credential material.
Synthetic fixtures only; no live values or user session contents enter Git or cloud chat.

## Historical M3A verification evidence

All commands use RTK. Core tooling uses ignored `--cache-dir runtime/uv-cache-mvp3`; module
entry points use the locked environment. Sidecar interpreter query and Windows asyncio test
initialization required sandbox escalation; no security policy changed.

| Check | Evidence |
| --- | --- |
| Core lock check / locked sync | Passed; 119 resolved / 69 installed packages checked |
| Sidecar lock check / locked sync | Passed; 20 resolved / 16 installed packages checked |
| Ruff format / lint | Passed; 406 formatted files |
| Mypy | Passed; 164 source files |
| Synthetic import tests | 77 passed; sockets, DNS, Garmin/keyring imports and real credentials forbidden |
| Bridge/report/import focused tests | 102 passed before final netrc regression added |
| Service tests | 11 passed, including cancellation/cache/throttle/output privacy |
| Real PWA script lifecycle | 8 Node cases passed; pytest wrapper and PWA API integration passed |
| Core and sidecar dependency audits | No known vulnerabilities |
| Gitleaks history / whitespace | Passed; 85 commits, no leaks |
| Local `jarvis doctor` | Passed; existing loopback/private defaults retained |
| First full repository test run | 1,413 passed / 3 skipped / 1 failed; 85.54% coverage; 125.40s |
| Final full repository test run | 1,414 passed / 3 skipped; 85.59% coverage; 110.71s |

The sole first full-run failure was the unchanged proactivity CLI minimum-one-minute snooze
test. Isolated rerun passed; investigation identified independent CLI/store clock samples crossing
a clock tick. A synthetic 50ms delay reproduced `Snooze denied. snooze must be at least 60 seconds`.
Minimal repair passes one CLI timestamp to the existing store API for both deadline and validation;
strict store bounds remain unchanged. The existing CLI regression advances the store clock by one
second and failed before repair, then passed with 14 focused CLI/runner tests. Full gate rerun
passed. The three existing optional platform/dependency skips remain; the Node lifecycle test
executed. FastAPI's existing Starlette/httpx deprecation warning remains. Live Garmin and phone
gates remain unexecuted; MVP 3 is not complete.

Full verification command (same strict flags and 85% threshold as repository configuration):

```powershell
rtk uv --cache-dir runtime/uv-cache-mvp3 run python -m pytest -q --basetemp runtime/pytest-mvp3-full-final-193bd -o cache_dir=runtime/pytest-cache-mvp3-full-final -o 'addopts=--strict-config --strict-markers --cov=jarvis --cov-report=term:skip-covered --cov-fail-under=85'
```

Published safe source at `cdd98321ce4253684b6958eb88342fafcd38ca1b` under standing authorization;
local HEAD, `origin/main`, and live upstream ref matched. Existing native package changes remain
uncommitted. Five report-only Markdown hard-break spaces were missed by the initial staged
whitespace gate and corrected in a follow-up documentation commit, with raw Git diagnostics and
the complete baseline-to-final whitespace check verified. Application code and full test evidence
are unchanged. CI result is a separate remote gate, not inferred from local success.

## Recovery and known limits

Import requires a single operator with Core and standalone readers stopped. Manifest check/write
is not an atomic cross-process exclusion mechanism. Refused/corrupt input does not alter the
source or previous protected session. Pre-publication vault write failures roll back new chunks;
cleanup deletion failures can leave unreferenced chunks and are not claimed fully recovered.
After a successful import, use Core as the sole session owner; independently refreshed file/Locker
copies may diverge. Disconnect/removal, source deletion and Garmin-side revocation require fresh
authority. Native mobile dependency edits remain preserved and excluded from M3A publication.

## Blockers and handoff

M3B protected import and live Core acceptance passed; source-path work is finished. M3C needs a
concrete health-read enrollment decision and physical-iPhone evidence. Important login/MFA,
enrollment and revocation actions require confirmation if not already approved.
Native M2C remains deferred under the existing $0/no-Mac constraint. No MVP 4 work authorized.

Estimated active PWA completion: **85%**. Basis: accepted phone chat/connection and protected live
Core Garmin summary; health-scoped physical-phone Garmin/recovery and final polish remain.
