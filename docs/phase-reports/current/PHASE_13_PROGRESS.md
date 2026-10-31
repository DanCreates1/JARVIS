# Phase 13 — Controlled Windows actions

- Status: `blocked-external`
- Started / updated: 2026-10-31
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: `gpt-6-astra` / `ultra` (recommendation only)
- Session baseline / five-hour stop: 2026-10-31T12:49:34-04:00 / 2026-10-31T17:49:34-04:00

## Objective and scope

Small explicit `controlled-windows` host-policy action set: enrolled application launch,
absolute master volume, fixed media keys, and one reversible controlled-root file move.
Reuse existing CLI proposal, trusted-local exact review, expiring one-use broker grants,
postconditions, durable receipts and guarded rollback. Add discoverable typed catalog and
explicit pending-grant cancellation. CLI is the selected action surface; remote chat gets no
new action-control scope. Existing PWA/text profiles stay unchanged.

Exclude clipboard, browser navigation, app groups, printing, shutdown, deletion, security/admin
changes, communications, arbitrary shell, general UI automation and hands-free activation from
this selected set. Legacy handlers remain available only through existing legacy configuration.
No owner policy, enrollment, credential, service or production feature activation.

## Baseline and preservation

- `main` at `17e84bc`; prerequisite Phase 7 complete; Phase 12 complete.
- 28 held paths copied/hashed in ignored `runtime/phase13/baseline/`; preserve original held
  native/provider edits. Shared-file task hunks must be recomposed against published source.
- Read full execution/master, architecture, security, Legacy Phase 3 receipt and hands-free
  contract. Legacy Phase 3 current live app/audio/media acceptance remains open.
- Accepted `prototype-text`, current locks, Wikimedia `authentication_required`, legacy NVIDIA
  latency debt and native dependency publication hold remain unchanged.

## Acceptance checklist

Frozen before implementation/current measurement:

- [x] Exact selected action set excludes stale clipboard/browser/printer/app-group/hands-free
  configuration; both existing host gates and Levels 0–4 semantics remain enforced.
- [x] Catalog shows fixed input schemas, risk, approval, timeout and recovery contracts without
  proposing/approving/executing effects. Preview safely displays terminal/markup/bidi input.
- [x] Current invalid input/injection, actor/session, policy mutation, target swap, replay/race,
  cancellation, timeout, unavailable adapter, audit failure, restart and recovery matrix passes.
  No duplicate/unauthorized effects, blind replay, shell or model authority.
- [x] Permission benchmark >=500 samples, warm p95 <=25 ms; fake broker >=200, warm p95 <=50 ms;
  >=24 reversible Windows file round trips with verified recovery; zero failures/escapes/remnants.
  Existing <=30 s action deadlines, <=100 KiB results/audit, <=100 MiB single-file ceiling retained.
- [ ] Current separately owner-authorized live smoke: one enrolled disposable two-second Python
  app fixture, one rounded-current-volume write (<=0.6 percentage-point scalar change, mute
  unchanged), one global media STOP pair. Exact broker receipts and postconditions; no playback
  claim. Prepare concrete review before requesting authority; historical authorization is not
  reused. Phone checks **skipped by owner; unverified**.
- [x] Full applicable working/isolated quality/security/release gates, >=85% coverage, locked
  base/optional/sidecar audits; starting optional environment restored; recovery/setup docs.
- [ ] Reviewed task-only publication, held-state proof, exact HEAD/tracking/remote agreement
  and fresh exact CI. No private/generated/runtime data published.

## Milestone log

- Baseline recorded; selected workflow and unchanged numeric gates frozen above.
- Current official Microsoft SendInput and Endpoint Volume Controls documentation checked.
  Input acceptance proves inserted events only; endpoint/exclusive-mode limits retained.
- Restricted policy registrations, typed CLI catalog, same-identity atomic grant cancellation,
  visibly escaped previews and exact local target details implemented. Existing dual switches,
  trusted approval phrase, bounded handlers and remote-scope boundary preserved.
- Found and repaired a durable-authority gap: full-policy guard was process-local while durable
  grants bound only the editable version label. Authority now includes the full validated policy
  hash; restart after a manual edit denies old grants. Obsolete pending requests fail before
  prompting. Unchanged-policy CLI approval/execute across fresh runtimes still works.
- Final review reproduced another exact-binding gap: generic canonical JSON normalized Unicode
  fixed argv, merging distinct code-point inputs into one policy hash. Policy authority now hashes
  deterministic exact validated JSON without Unicode normalization. Exact local target previews
  also preserve code points. Static collision and same-process/restart mutation regressions pass.
  Official Microsoft filename contracts confirm opaque Windows code points.
- Exact app preview reads executable/fixed argv/digest from the hash-bound host policy at review.
  An initial attempt to copy argv into canonical preconditions failed the existing minimization
  test; that approach was removed. Existing raw-argv exclusion test remains unchanged and passes.
  File preview shows controlled root/size/digest. Escape, newline, bidi and Rich markup input
  cannot conceal or rewrite preview fields.
- Initial action/security/CLI/Windows/store matrix: **185 passed, 1 existing skip**, 19.49 s.
  Initial selected-workflow matrix had nine cases, including real guarded Windows CLI file move,
  separate approval/execute, restart/replay rejection, revoked/foreign/claimed grant denial,
  concurrent cancellation, stale optional configuration and obsolete-policy review.
  A nine-case rerun passed after strengthening the fixture to forbid native media at the
  handler boundary; this new selected-workflow matrix dispatches no app/audio/media effect.
  Full suites retain existing bounded Python launch/termination primitive tests and read-only
  printer probes under routine test authority. Those do not satisfy current brokered live smoke.
- Reused unchanged broker/guarded-file benchmark passes: 700 authority checks, 250 fake dispatches,
  24 real Windows move/rollback rounds, no false accepts/duplicates/escapes/failed recovery/remnants.
  Working p50/p95: authority 0.151/0.283 ms, fake broker 0.256/0.478 ms, files 61.772/80.894 ms.
  Fresh isolated p50/p95: authority 0.249/0.489 ms, broker 0.350/0.595 ms, files 95.572/106.486 ms.
  Selected registry/current actual CLI workflow is tested separately from this reusable benchmark.
- Base and restored optional root audits and Garmin sidecar strict audit pass. Exact original
  97-package optional inventory restored after locked base sync; locks unchanged.
  All eight desktop browser profiles and 173 PWA/PCM checks pass; PWA assets unchanged.
- Empty-state prototype doctor passes all fourteen checks without loading owner data or running
  inference. Independent official CPython 3.11 bootstrap passes in a fresh isolated environment,
  with no install/model flags or OS-policy override.
- Failed attempts retained: wrong test expectations for consumed-grant replay and denied receipts
  corrected to existing contracts; fixture enrollment now uses an actual synthetic file identity.
  Windows PowerShell script policy rejected bootstrap; normal PowerShell 7 accepts it. Its first
  environment replacement hit in-use native files because isolated tests were active; a separate
  fresh environment passed bootstrap and publication gates were repeated there. No policy bypass.
- A working full-suite attempt hit Windows `WinError 5` on a disposable voice-settings atomic
  rename. Fresh-path voice suite passes 16 tests; unchanged full gate rerun uses a new ignored
  runtime basetemp. Failure is retained, not suppressed or counted as a pass.
- First exact implementation CI `41223399481` failed seven new identity-dependent tests because
  its Windows runner is elevated. Production correctly refused native authority. Policy/store
  tests now use an explicit synthetic actor port. Native CLI acceptance uses the real current
  token: non-elevated laptop verifies move/restart/replay; an elevated runner must deny before
  creating the authority database. A forced-elevation regression verifies runtime and CLI denial.
  Production elevation guards are unchanged; no skip, gate bypass or native positive claim on CI.
  The first failed CI log stays ignored under `runtime/phase13/implementation-ci-failure.log`.
- Final selected workflow has **13 cases** after adding exact-Unicode binding and native denial
  regressions. Current focused broker/coordinator/selected-workflow checks pass **61 tests**.
  The full suite includes the expanded **189-case** action/security/CLI/Windows/store selection
  with its one existing platform skip. Native positive file acceptance is current on this
  non-elevated laptop; elevated native admission is a denial test, never a positive effect pass.
- Final Unicode/CI corrections require repeated full working/isolated gates. Earlier passing
  runs remain historical attempts; two superseded concurrent runs were stopped before completion
  when contention slowed them. Final gates run serially on new verified ignored basetemp roots.

## Decisions, authority and blockers

Routine isolated repository fixtures and automated verification are authorized. Current live
app/audio/media smoke needs exact separate owner authority after preparation. Prepared command
and exact effect limits are in [Controlled Windows](../../CONTROLLED_WINDOWS.md#current-live-acceptance-boundary).
Only that acceptance remains external after repository gates. Historical 2026-08-26 permission
is not reused. No new production policy, enrollment, credential, scope, printer or phone operation.

## Verification and measurements

Raw artifacts remain ignored under `runtime/phase13/`. Working runtime CPython 3.11.9;
fresh publication bootstrap CPython 3.11.9; first isolated environment CPython 3.11.16;
uv 0.12.15, Node 24.20.0, Windows build 26300. No live model, media or audio measurement claimed.
Published-source review excludes all held provider/native changes and preserves the published
Groq contract; isolated full-suite count therefore includes one additional legacy provider test.

| Gate | Working source | Isolated publication source |
| --- | --- | --- |
| Strict full tests / >=85% branch coverage | 1719 passed / 3 existing skips; 86.41%; 191.48 s | 1720 passed / 3 existing skips; 86.32%; 203.93 s |
| Format / lint / Mypy | Pass; 172 source files | Pass; 172 source files |
| Root base / restored optional / sidecar audits | All clean | Clean base; same unchanged audited sidecar lock |
| Current action/CLI/security selection | 189 cases / 1 existing skip included in full suite | Included in full suite |
| Final selected workflow / native admission | 13 cases pass; actual non-elevated file workflow and forced elevated denial | Same final source; native token remains real for CLI admission |
| PWA lifecycle / PCM | 173 pass | 173 pass |
| Desktop browser profile regression | All eight profiles pass | Assets identical; profile code unchanged |
| Synthetic empty-state doctor | All fourteen checks pass | Fresh official-Python bootstrap passes |
| Current grant/broker/file benchmark | All fixed thresholds pass | All fixed thresholds pass |

Retained Starlette TestClient deprecation and three platform/capability skips. No skipped gate
is treated as a new physical pass. Final exact policy/preview implementation and test harness
are included in both repeated full gates above. Exact CI runs the final source independently
after publication. Earlier passing runs are not substituted for these final results.

## Known limits, recovery and deferred scope

Use policy disable to invalidate outstanding authority. Native calls already dispatched can be
uncertain; record unknown/manual recovery and never retry blindly. Guarded file/volume rollback
must not overwrite newer user changes. Physical/native/mobile MVP/production acceptance remains
unestablished.

## Publication and handoff

Task-only publication source: 20 reviewed paths, three shared-file hunks recomposed independently
of 28 held paths. All other published source remains identical to baseline HEAD. Locks, prototype
launcher/corpora, PWA assets and held provider/native work preserved. Current link/source/history
secret and whitespace checks pass; exact commit/tracking/remote and fresh CI are checked after
publication and recorded in the handoff. No unsafe/runtime/private artifact is staged.

Phase remains **blocked-external** only on missing current exact live-effect authority. Selected
implementation and automated repository work are ready; no exit credit granted for historical
effect evidence. Prepared live smoke awaits the single grouped owner decision described above.
Do not start Phase 14 or enable owner actions merely because code is published.

Progress: **12/19 primary receipts closed (~63%)**,
unweighted management count, not code/effort or mobile MVP acceptance. Continue current Phase 13
until all applicable exit gates pass; Phase 14 not started.
