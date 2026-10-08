# PWA MVP 3 — Garmin integration and acceptance

- Status: `blocked-external` — M3A local preparation complete; M3B needs fresh authority
- Started: 2026-10-07
- Updated: 2026-10-08
- Active subphase: M3B — protected-session setup and sanitized Core read, awaiting owner authority
- Recommended Codex model/reasoning: `gpt-6-astra`, `xhigh`
- Current session stop: 2026-10-08T21:15:00-04:00 (conservative five-hour ceiling)

## Objective

Connect the owner's existing Garmin session to the protected Core bridge, then prove scoped
read-only PWA refresh and recovery on the physical iPhone. M3A static compatibility review is
complete. M3B resumes with local execution preparation; no fresh source/import/read authority,
login/MFA, enrollment, revocation or private HTTPS route change has been granted.

## Baseline

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
- [ ] M3B: fresh owner authority for selected token import or interactive login/MFA.
- [x] M3B: prepare a flags-only Core evidence command; live execution remains gated.
- [ ] M3B: sanitized Core summary from protected session; no private values in evidence.
- [ ] M3C: fresh owner authority for one-use browser ticket adding `client.health.read`, risk 1.
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

Pending fresh owner authority. Prefer explicit offline import after synthetic validation.
Expired/revoked tokens require separate authority for Garmin login/MFA. No automatic fallback.

2026-10-08 local preparation:

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

### M3C — health-scoped phone acceptance

Pending fresh enrollment authority and physical-device evidence. Existing PWA enrollments cannot
gain `client.health.read` implicitly. Do not run the Phase 8D launcher against an unowned route.

## Security and privacy

Treat tokens as credential material and Garmin responses as untrusted private health data.
Import must preserve source files, perform no network request, and store only in Windows
Credential Locker. Core and phone receive bounded health views, never credential material.
Synthetic fixtures only; no live values or user session contents enter Git or cloud chat.

## Verification evidence

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

Fresh owner authority required before actual token import, login/MFA, enrollment ticket creation,
or revocation. Static schema compatibility is not proof of actual token validity or acceptance.
Native M2C remains deferred under the existing $0/no-Mac constraint. No MVP 4 work authorized.

Estimated active PWA completion: **80%**. Basis: accepted phone chat/connection, implemented Garmin
panel/API and standalone report; protected session and physical-phone Garmin/recovery remain.
