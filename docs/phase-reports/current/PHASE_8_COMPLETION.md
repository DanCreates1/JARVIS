# Phase 8 — Private Garmin workspace

- Status: `complete`
- Started / updated: 2026-10-27 / 2026-10-27
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: `gpt-6-astra` / `ultra` for identity/authority decisions
  (recommendation only; no UI model change claimed)
- Session start / five-hour stop: 2026-10-27T20:35:00-04:00 / 2026-10-28T01:35:00-04:00

## Objective and scope

Useful read-only Garmin workspace in the existing laptop Core/PWA. Reuse protected Windows
Credential Locker session, Python 3.12 bridge, six allowlisted reads and normalized presentation.
Add explicit `private-garmin` capability profile extending daily local text, with Garmin view
and existing exact health-scope enforcement. No second runtime/router/store or model health input.
Standard profile retains its prior scoped foundation; `prototype-text` and `daily-text` remain
text only. No reimport, new login/MFA, scope/enrollment, background polling, provider health write,
deployment or physical-phone request. Actual dependency: completed Phase 7.

## Baseline and preservation

- `main`, HEAD `79e769301fda2145f47db6e314c576d01826c0ea`.
- 28 held dirty/untracked paths captured with bytes/deletion state and hashes under ignored
  `runtime/phase8/baseline/`; initial installed package versions captured before sync.
- Native manifests and provider removal/HTTP-error edits remain held and excluded from publication.
  Shared bootstrap/config/docs require isolated task hunks over HEAD. Preserve original prototype
  prompts, launcher and frozen corpus; no lock upgrade planned.
- Prior protected live Core proof: 2026-10-08, legacy M3B. M3C health enrollment and physical rows
  are not current prerequisites; phone checks **skipped by owner; unverified**. Historical reports
  remain unchanged. No current live validity inferred from that old receipt.
- Reviewed Phase Execution, full master roadmap, architecture decision, all three Phase 8 references,
  authority/security rules and current bridge/service/PWA/tests. Installed uv 0.12.15, Node 24.20.0,
  Gitleaks 8.30.1; exact Python/dependency versions to be revalidated.

## Acceptance checklist

Frozen before implementation/live reads:

- [x] Explicit profile: local-only daily text plus Garmin; other optional integrations disabled.
  Text profiles reject health API even with a synthetic health-scoped identity. No implicit scopes.
- [x] Six read allowlist, at most three generic activities, numeric/date/schema validation;
  credentials/raw responses/locations/free text excluded; no health model/cloud/history/cache input.
- [x] Child stdout capped at 8,192 bytes while reading, 90-second total deadline, kill/reap on
  overflow/timeout/cancellation; bounded concurrent read coalescing and restart starts empty.
- [x] Five-minute memory cache and one-minute upstream refresh throttle; failed refresh cannot
  relabel retained data as fresh. Day rollover, old/naive/future timestamps and unavailable fields
  are explicit. No background health polling or automatic login/import fallback.
- [x] Synthetic lifecycle matrix: partial/empty/invalid/rate-limited reads, same-account rotation
  retained after category/profile failure, disconnect, malformed vault, timeout/cancel/retry,
  duplicate/concurrent reads, scope/host/origin/auth denial, logout/reconnect/late response erasure,
  client persistence exclusions and private-output suppression.
- [x] One bounded current live Core check through protected saved session after competing-reader
  inventory, using existing flags-only helper. Require valid schema, today, aware nonfuture fetch
  <=300 seconds, <=3 activities and >=1 available category. No live values retained. Actual token
  renewal need not occur to fabricate evidence; synthetic rotation proof stays distinct.
- [x] Updated capability/setup/freshness/disconnect/recovery documentation. Live disconnect is
  excluded; synthetic protected-store deletion only, actual deletion remains consequential.
- [x] Full protocol gates: locks/sync, format/lint/types, pytest >=85%, audits including restored
  extras and sidecar, PWA/PCM/accessibility standard + prototype + daily + Garmin, secret/whitespace/
  document links, isolated publication source and held/baseline preservation, safe commit/push and
  exact remote/fresh CI verification.

## Milestone log

- Baseline and contracts reviewed; preservation snapshot complete. Found unbounded child
  `communicate()` buffering before length validation, mutable cached model, and retained-cache
  freshness ambiguity after refresh failure. Implement bounded transport and explicit presentation.
- Implemented explicit profile/launcher; text profiles deny health endpoint. Frozen immutable
  summaries, strict schema/date checks, duplicate-field rejection, bounded streaming child output,
  kill/reap, failed-cache invalidation, activity endpoint availability, day-rollover stale state
  and immediate 403 value erasure. Original text prompts/launchers untouched.
- Current live Core read passed on 2026-10-27, after process inventory found zero competing
  Core/standalone readers. One `scripts/garmin_core_check.py --read` invocation: `status=pass`,
  `schema_valid=true`, `fresh=true`, `activity_bound=true`, all six category-presence flags true.
  Tool wall time 6.59 seconds includes wrapper/startup, below child 90-second limit; one sample
  provides no latency distribution. No values/account IDs/token state retained; no reimport/login/
  enrollment/disconnect. Whether token rotation occurred is intentionally not observed.
- Root audit initially failed on `msgpack==1.2.1`, `CVE-2026-114613` (pip-audit/cachecontrol
  development transitive dependency). Applied narrow `uv lock --upgrade-package msgpack==1.2.3`;
  no other locked package changed. Current base, restored-extra and sidecar audits pass without
  suppressions. All 97 starting package names restored; only msgpack version differs intentionally.
- Review extended failed-cache invalidation to missing bridge/interpreter files and distinguishes
  malformed activity arrays from successful empty arrays. Final focused bridge/service gate:
  46 passed. An initial working full gate passed 1,580 tests / three existing skips, 86.00% coverage
  in 157.85 s; final source fixes require fresh complete gates, not substitution of that old pass.
- Isolated publication setup uses exact approved PSF Python 3.11.9 and existing bridge Python
  3.12.14, no downloads. Initial exported full run had fixture setup errors: missing parent for
  nested `--basetemp` caused `FileNotFoundError: [WinError 3]`. Reproduced first error directly;
  shorter verified new ignored runtime basetemp fixes it. No application policy/test weakened.
  Stopped intermediate exported run after final review changed source; it earns no acceptance.
- Final live Core check on the isolated publication source passed the same schema/freshness/
  activity bound and all six presence flags after another zero-competing-reader inventory.
  Final invocation wall time 4.13 s includes inventory/wrapper; not a latency percentile. This is
  the second bounded live call, justified by final-source verification after transport/cache review.
  Both calls pass; no unfavorable sample omitted. Protected session reused, no credential state
  observed or emitted. Exact `open-garmin.cmd doctor` passes against a new empty synthetic store;
  no owner store or route loaded. No extra live health read occurs during doctor.
- Concurrent final full runs each exposed one unrelated failure: working email parser's 50 ms
  timeout elapsed before its child capture (`children == []`), and exported voice fixture hit
  transient `PermissionError: [WinError 5]` replacing synthetic settings. Both exact tests pass
  together in focused verification (2 passed, 0.29 s). Re-run full gates serially in new verified
  ignored runtime basetemps per owner policy. No production deadline, test or OS policy changed;
  concurrent failing runs are retained as failures, not closure evidence.

## Decisions, authority and blockers

Saved-session read, incidental profile/settings and normal same-account renewal are covered by
standing owner policy. No reimport/source discovery needed. Synthetic fixture identities use only
disposable stores; production scopes and access stay unchanged. No external blocker established.

## Verification and measurements

Official pinned Garmin client, keyring, Python subprocess and Requests netrc documents rechecked
on 2026-10-27. Installed bridge source retains three-field `dumps`/`loads`, session attributes and
saved-session path. Python 3.11.9 Core / 3.12.14 bridge; garminconnect 0.3.16, keyring 25.7.0,
requests 2.34.2, curl_cffi 0.16.3 and ua-generator 2.1.6 unchanged. Root and sidecar locks/sync pass.

Focused Python matrix initially 163 passed, then extended with read allowlist/availability/restart/
API-denial cases. Latest targeted Core/API run 34 passed. PWA/PCM now 154 + 7 cases passing.
Desktop Edge: standard 72, prototype 9, daily 9, private Garmin 13 passing. New profile exercises
explicit synthetic HTTP refresh, partial values, named accessibility heading, 320/1280 reflow and
logout clearing. Browser default-font/geometry/AX evidence is not physical Safari or spoken screen
reader acceptance. Final local release evidence follows; implementation publication and fresh CI
also pass below. Documentation closure receives its own exact-SHA CI check in the closing reply.

| Final local gate | Working checkout | Isolated publication source |
| --- | --- | --- |
| Root lock / locked copy sync / base audit | Pass | Pass |
| Voice/vision extras restored, installed audit | 97 starting package names; only msgpack patched | Same locked extras; audit pass |
| Sidecar lock / locked copy sync / installed audit | Pass; lock unchanged | Pass; same Python/dependencies |
| Ruff format / lint / Mypy | Pass; 169 typed source files | Pass; 169 typed source files |
| Complete serial pytest, unchanged 85% floor | 1,583 passed / 3 skipped; 86.01%; 146.08 s | 1,584 passed / 3 skipped; 85.99%; 147.98 s |
| PWA lifecycle / PCM | 154 + 7 passed | 154 + 7 passed |
| Standard / prototype / daily / Garmin desktop | 72 / 9 / 9 / 13 passed | 72 / 9 / 9 / 13 passed |
| Exact Garmin launcher doctor, empty synthetic store | Same launcher source | Pass; installed qwen3:1.7b reachable |
| Local links/anchors before closure rename | 223 pass | 223 pass |
| Full-history / exact publication-source secret scan | 130 starting commits, clean | 554 source files, clean; no runtime/environments |

All strict audits report zero known vulnerabilities; no suppressions. Existing three platform/
capability skips and Starlette test-client warning remain. One extra published test and different
coverage denominator come from preserved original provider code/tests outside held removal.
Both complete suites ran serially after exact focused failures passed, without editing those tests.
Those code/lock gates describe the initial publication. The post-closure stress repair below
requires fresh complete gates; earlier passes are not substituted.

### Post-closure large-output stress repair

During final CI follow-up, a new synthetic 2,000,000-byte worker exposed a cleanup defect in the
new bounded reader: output rejection killed the child but waited before draining its paused pipe.
The 9,000-byte test had not filled the pipe. Independent five-second watchdog expired and emitted
closed-loop transport warnings; no real Garmin session/data was involved in that failed probe.

Repair discards remaining stdout in fixed 4,096-byte chunks after kill, then reaps. It never
accumulates discarded bytes or exposes them. Real-child regressions now test both 9,000 and
2,000,000 bytes with unchanged five-second watchdog and 90-second Core child deadline; 25 service
cases pass, including timeout/cancel, both large-output paths and no private diagnostic text.
The independent 2 MB probe now settles without warnings. No timeout or acceptance limit weakened.

Third bounded live Core read on the repaired isolated source passes schema/freshness/activity
bound and all six category-presence flags. No values or credentials emitted; no reimport/login/
enrollment/revocation. Same unchanged pinned sidecar and protected session, no competing live reader
started by this work. Static format/lint/types and fresh serial full suites pass in both checkouts.
Repair publication and fresh CI also pass below. Initial publication/closure receipts above remain
historical, not substitutes for acceptance of this later repair.

| Repaired source gate | Working | Isolated publication |
| --- | --- | --- |
| Full pytest, unchanged 85% floor | 1,584 passed / 3 skipped; 86.02%; 135.49 s | 1,585 passed / 3 skipped; 85.97%; 134.74 s |
| Ruff format / lint / Mypy | Pass; 169 typed files | Pass; 169 typed files |
| Installed root and sidecar audits | Zero known vulnerabilities | Zero known vulnerabilities |
| PWA/PCM | 154 + 7 passed | Full suite executes same lifecycle wrapper; source unchanged |

Concurrent audit-cache writes emitted performance-only Windows cache permission warnings; both
strict installed audits completed with zero vulnerabilities. No OS policy or audit rule changed.

Security repair sources: [upstream advisory](https://github.com/msgpack/msgpack-python/security/advisories/GHSA-j586-36cw-2gc2),
[fixed release](https://github.com/msgpack/msgpack-python/releases/tag/v1.2.3). Advisory provider
version ranges differ; strict audit of installed locked 1.2.1 failed, so use patched 1.2.3 rather
than suppressing or downgrading the audit. Starting lock plan changed only for this discovered gate.

## Known limits, recovery and deferred scope

Unofficial Garmin web client can become unavailable. No medical interpretation, health write,
native/physical/mobile MVP/production acceptance. Phone checks **skipped by owner; unverified**.
Native dependency publication hold remains. Local disconnect cannot revoke Garmin-side access;
disconnect cannot erase another tab's memory synchronously, so bounded refresh/freshness applies.

## Publication and handoff

Reviewed task source spans 27 paths. Five shared files are clean three-way task merges over
`79e7693`; recomposing the held starting hunks reproduces the current worktree exactly after line
ending normalization. Other 23 held paths retain exact hashes/deletion state. Native manifests in
the export equal starting HEAD, not held working candidates. Original system/text/daily prompts,
both text launchers and original/expanded corpora remain unchanged. No runtime data, tokens, raw
live values, model weights, screenshots, logs or generated artifacts are publication inputs.

Published implementation `1cbaf5fb1d282062e6df58cb679db97403972f1a`; committed tree equals reviewed
export `09421ff9d730085467f8458a1ef6e55c588186e4`. Local HEAD, tracking `origin/main` and live
upstream matched. [Fresh CI 40613362830](https://github.com/DanCreates1/JARVIS/actions/runs/40613362830)
passes Windows quality job `122570026468` and secret job `122570026821` at that exact SHA.
Post-publication history scan passes 131 commits; only the 28 original held paths remain dirty,
all five shared held hunks recompose correctly, and index is clean.

Initial `fdf2667` receipt/status/link closeout changed documentation only; its
[fresh CI 40613936587](https://github.com/DanCreates1/JARVIS/actions/runs/40613936587) passed.
The later pipe cleanup repair passed new application gates and was published as
`861b06c5643e2d6157591a54db99394caade8431`, tree `f89890c651626b834d7cd7bde07c833863916bf3`.
HEAD, tracking and live remote matched. [Fresh repair CI 40615225872](https://github.com/DanCreates1/JARVIS/actions/runs/40615225872)
passes Windows quality job `122576028343` and secret job `122576028015` at that exact SHA.
History scan passes 133 commits. Held-path recomposition/hash/deletion proof passes again;
only the original 28 held paths remain dirty, index clean. This final receipt/status closeout
changes documentation only, with application/test/lock bytes identical to the repaired gate.
Final commit/tracking/live remote and its
own fresh CI are checked separately after push and reported in the closing reply; implementation
CI is not substituted for that later commit. Standing safe publication authority applies.

No deployment, signing, scope grant, production enrollment, new login, import, token revocation,
live disconnect or phone request occurred. Current phase completion covers protected Core and
automated scoped PWA projection. Real owner health-scoped browser/physical acceptance remains
unestablished; phone checks **skipped by owner; unverified**. Native/provider publication holds stay.

Progress: **8/19 primary receipts closed (~42%)**, unweighted management count, not code/effort or
mobile MVP acceptance. Next current phase: **Phase 9 — Files and attachments**; actual prerequisite
Phase 7 is complete. Handoff does not start it or add integration/scope/deployment authority.
