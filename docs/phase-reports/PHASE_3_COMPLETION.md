# Phase 3 Controlled Computer Access Completion Report

Status: `implemented-closeout-pending`

Started: 2026-08-22

Completed: 2026-08-26

Updated: 2026-08-31

Recommended Sol thinking: Ultra

## Objective

Deliver narrow, authorized Windows actions through deterministic typed tools, an approval-capable
permission policy, exact expiring one-use grants, a least-privilege broker, sanitized audit
receipts, postcondition verification, and bounded recovery. Do not expose arbitrary shell,
model-generated command strings, broad filesystem/application authority, implicit elevation, or
gesture-based approval for high-risk work.

## 2026-08-31 revalidation

Implementation, default-off authority, and historical separately authorized live evidence remain
intact. Current safe local gates pass. The program explicitly withholds authority to control real
applications/devices, so the live app-launch, volume, and media checks were not repeated. The
playbook therefore prevents a current `complete` claim.

- Broker/policy/Windows/failure/restart/recovery/adversarial suite: 314 passed, 1 skipped in
  2.76 seconds. The skip is the existing non-elevated Windows directory-symlink case.
- Fresh enforced benchmark: 700 permission/grant validations, p50/p95 0.130/0.215 ms, zero invalid
  false accepts; 250 fake broker dispatches, p50/p95 0.220/0.244 ms, zero duplicate effects; 24
  reversible production-handler move/rollback round trips, p50/p95 51.140/58.676 ms, zero
  unauthorized effects, failures, rollback failures, or destination remnants.
- The 2026-08-26 authorized live artifact was reinspected: three exact-approval broker actions
  passed then. It is historical evidence, not a claim that current real applications were
  controlled during this revalidation.
- RTK 0.45.0 now runs. Generated console shims remain blocked by Windows Smart App Control; allowed
  locked module entry points and independent exact-command CI evidence are both retained.
- Fresh ignored evidence: `runtime/phase3-revalidation-20260831-01/phase3-benchmark.json`.

## Baseline

- Git branch/HEAD: `main` at `7d32b93`, tracking `origin/main`.
- Worktree state and preserved unrelated changes: Phase 2 implementation and documentation are
  present as uncommitted tracked/untracked changes. They are prerequisite user work and will be
  preserved. No reset, checkout, commit, or push is authorized.
- Relevant installed software/hardware/provider state: Windows 11 Home `10.0.26200`; Intel
  i5-11400H; 16,888,967,168 bytes RAM; Python 3.11.16 via uv 0.12.5; Git 2.55.0; Gitleaks 8.30.1.
  Cloud credential variables inspected by name only are unset; Phase 3 does not require cloud.
- Existing tests and failures: no baseline failures. Locked sync, format, lint, strict mypy,
  140-test suite, 85.21% branch coverage, dependency audit, Gitleaks, diff check, and main doctor
  all pass before Phase 3 implementation.
- Prior phase evidence: Phase 1 implementation commit `d976506` contains typed tools, independent
  deny-by-default policy, SQLite audit foundations, CLI, and loopback browser interface. A formal
  Phase 1 completion report is absent. Phase 2 completion report is present and records local typed
  clap intent only; continuous listening remains hard-disabled and grants no action authority.

## Declared acceptance targets

- Permission/grant verification benchmark: at least 500 operations; warm p95 <= 25 ms; zero false
  accepts for expired, replayed, mutated, wrong-user, wrong-session, or wrong-action grants.
- Broker dispatch overhead, excluding OS action latency: at least 200 fake-adapter operations;
  warm p95 <= 50 ms; zero duplicate side effects under idempotent replay.
- Result/audit bounds: every tool timeout <= 30 seconds; structured result/audit payload <= 100 KiB;
  file operations default to one target and never exceed 100 MiB per operation.
- App/media/file live checks: 20+ bounded Windows samples with p50/p95, zero unauthorized effects,
  verified postconditions, and successful recovery for the reversible file action.
- Cancellation: cancellation before execution causes zero effects; cancellation during an effect
  either completes and reconciles or rolls back with an explicit partial/recovery receipt; a late
  cancellation cannot erase the receipt.
- Hands-free: unknown, ambiguous, replayed, or unconfigured intents do nothing. Gesture/acoustic
  input alone cannot approve Levels 2-4. Always-listening remains disabled.

## Acceptance checklist

### Functional deliverables

- [x] Permission Levels 0-4 have exact deterministic semantics independent of model confidence.
- [x] Trusted local approval surface is separate from model/chat content and displays exact effect,
  target, scope, expiry, recovery, and risk.
- [x] Expiring single-operation grant binds tool/version, canonical arguments, actor, session,
  policy version, nonce/idempotency key, approval identity, and time.
- [x] Broker accepts only registered action IDs and typed arguments; no shell strings, arbitrary
  executable paths, inherited secrets, implicit elevation, or dynamic policy changes.
- [x] Audit receipt covers proposal, approval/denial, dispatch, execution, verification, failure,
  cancellation, and rollback/recovery without retaining secrets or private file content.
- [x] App/app-group launch, volume/media, bounded clipboard/browser/status, read/search, and a first
  reversible file action use schemas, allowlists, timeouts, result caps, audit, and postconditions.
- [x] Printing has discovery/status and validated bounded job support, or remains disabled with an
  explicit external blocker and the phase stays incomplete.
- [x] Hands-free intents resolve only through an allowlisted typed mapping; gestures/audio never
  become paths, executable arguments, shell text, or high-risk approval.
- [x] API-first adapters are used; UI automation remains absent unless an isolated reviewed adapter
  is needed for a supported action.

### Failure, cancellation, restart, and recovery

- [x] Missing dependency/application/printer, timeout, cancellation, malformed adapter response,
  capacity loss, permission denial, duplicate/replay, and postcondition mismatch fail closed.
- [x] Approved-but-unconsumed grants survive restart only until expiry; consumed grants cannot be
  replayed after restart or across session/user boundaries.
- [x] Reversible file operation supports preview, target-set revalidation, idempotency, rollback or
  deterministic reconciliation, and no unexpected target expansion.
- [x] Audit-store failure prevents approval-required execution; receipt persistence survives normal
  restart and exposes recovery state after uncertain side effects.

### Privacy and security

- [x] Path traversal, alternate spelling/case, symlink/junction/reparse escape, TOCTOU target swap,
  argument injection, executable substitution, and environment-secret inheritance tests fail closed.
- [x] Prompt/tool-output/confused-deputy injection cannot register actions, lower risk, mutate an
  approval, select arbitrary targets, or authorize execution.
- [x] Stale, replayed, cross-user, cross-session, cross-tool, downgraded, and parameter-mutated
  grants are rejected and audited.
- [x] Sensitive clipboard/file/print content is never logged or disclosed to cloud routing.
- [x] Level 4 actions and unsupported Level 3 actions are disabled by default.

### Performance, target hardware, and operations

- [x] Declared broker/grant benchmarks meet sample-count and p50/p95 targets.
- [x] App launch, media/volume, and reversible file operation pass live Windows checks through the
  broker using disposable fixtures and no real user-data mutation.
- [x] Printer discovery/status and a safe local print fixture pass without sending private data or a
  physical job unless separately authorized.
- [x] Kill/cancel path stops pending actions and no action storm occurs under bounded intent replay.

### Documentation and release

- [x] Configuration, setup, architecture, security, permissions, audit viewing, recovery, and
  Windows limitations are documented without claiming unverified capability.
- [x] Migrations and clean-install/upgrade/restart behavior pass.
- [x] Full lock/sync/format/lint/type/test/vulnerability/secret/diff/doctor gates pass.

## Milestones

### Milestone 1 - Baseline, threat model, and contracts

- Status: complete
- Changes: mandatory references read; live Git/environment/hardware baseline captured; acceptance
  targets fixed before implementation.
- Evidence: Phase 3 playbook/reference review, Git/tool inventory, and complete pre-change release
  gate dated 2026-08-22.
- Remaining: none.

### Milestone 2 - Permission broker, grants, persistence, and audit

- Status: complete
- Changes: strict permission/tool metadata; canonical action/grant fingerprints; Levels 0–4 policy;
  authenticated local actor identity; trusted exact-phrase CLI approval; SQLite request, decision,
  grant, receipt, broker-event, control-intent, and sanitized append-only lifecycle migrations;
  transactional one-use claims; fixed local broker; coordinator; dual host gates and live policy
  fingerprint guard; CLI status/init/enable/disable/propose/pending/approve/execute/audit; enforced
  parallel/global/session concurrency; cancellation before claim; exact authority revalidation; and
  sequence-conflict-safe required audit persistence.
- Evidence: independent broker/coordinator/store/runtime/adversarial integration run: 78 passed.
  Concurrency covers global/session serialization, parallel overlap, zero-effect cancelled waiters,
  lock cleanup, and valid retry after a pre-claim rejection audit. Default-disabled bootstrap and
  live policy-change kill-switch tests pass.
- Remaining: none.

### Milestone 3 - Narrow Windows actions and hands-free mapping

- Status: complete
- Changes: fixed executable/app-group launch; Core Audio absolute volume; fixed global media keys;
  bounded Unicode clipboard; enrolled public-HTTPS browser targets; controlled filename search;
  printer discovery/status; controlled `.txt` Windows `TEXT` spooling; guarded same-volume file
  move/rollback; session/freshness/confidence/replay/rate-limited Level 1 hands-free proposal gate;
  cloud-provider schema filtering; Unicode-only clipboard rollback; print-source mutation guards;
  and bounded UTF-8 search result shapes.
- Evidence: independent Windows/actions/broker/adversarial run: 94 passed, 1 skipped. Real Windows
  rename tests pin the allowed root, every ancestor, source/destination parents, and exact source;
  source/parent/root swaps are blocked and leaf collisions never overwrite. Printing hard-link,
  offline/recall, clipboard legacy-format, maximum search-shape, and hands-free proposal-only tests
  pass. Read-only probes queried Core Audio and two installed printer queues without mutation/job.
- Remaining: none.

### Milestone 4 - Adversarial and real-target acceptance

- Status: complete
- Changes: dedicated hostile cross-layer suite; enforced benchmark for invalid grants, replay,
  broker dispatch, and real controlled-root move/rollback; explicit opt-in live Windows smoke
  harness for a disposable two-second app fixture, rounded current volume with mute unchanged, and
  one global media STOP input. The harness requires a separate exact operator acknowledgement,
  uses the production coordinator/broker/local-CLI approval path, records only sanitized evidence,
  and refuses existing/non-direct runtime work roots.
- Evidence: benchmark evidence at `runtime/phase3-benchmark-20260822-a5/phase3-benchmark.json`
  passes all thresholds: 700 exact authority checks, 250 fake dispatches, 24 real move/rollback
  round trips, zero false accepts/duplicates/escapes/unauthorized effects. Adversarial, broker,
  Windows, cancellation, failure, restart, and recovery suites are green. Harness safety/static
  suite: 6 passed. The separately authorized live run at
  `runtime/phase3-live-smoke-20260826-01/result.json` completed all three actions through the
  production coordinator, broker, and trusted local CLI approval path: the exact enrolled Python
  fixture launched and exited in 2.001 seconds; volume remained at 38% with zero scalar change and
  mute unchanged; and Windows accepted one media STOP key-down/key-up pair. All three receipts
  succeeded with passed postconditions and bounded sanitized results. Playback state is not
  observable through `SendInput` and is explicitly not claimed.
- Remaining: none.

### Milestone 5 - Release gate and closeout

- Status: complete
- Changes: controlled-access operator guide plus README, setup, architecture, security, hands-free,
  hardware, and technology-decision updates.
- Evidence: documentation distinguishes verified behavior, private authority state, sanitized
  operator audit, in-process non-elevated broker, native-call uncertainty, printer spool limits,
  absent Level 3/4/UI/shell/admin capability, and removal of private host tool schemas from cloud
  provider requests. Full release/security/doctor gate passes; completion documentation and roadmap
  status match the shipped default-disabled scope.
- Remaining: none.

## Decisions

- Decision: ship no Level 4 operation in Phase 3.
- Reason: the security model requires a dedicated separately privileged service and threat review;
  Phase 3 exit requires narrow normal-user actions, not administrative authority.
- Alternatives: always-elevated process or generic administrative command runner are prohibited.
- Reversible later: individually reviewed Level 4 action IDs can be added behind a separate service.

- Decision: use a trusted local operator surface for approval; chat/model content can only propose.
- Reason: an API caller or model cannot approve its own privileged request.
- Alternatives: conversational "yes" and hidden auto-approval do not establish trusted identity.
- Reversible later: authenticated enrolled-device approval can be added in Phase 8.

## Verification evidence

Current integrated release evidence (2026-08-31): local locked gate passes with 535 tests passed,
1 skipped, 85.24% coverage; 66 source files type-check; 148 files are formatted; lint, dependency
audit, Gitleaks, diff check, and doctor pass. Independent fresh Windows run `33467300560` passes
bootstrap and exact lock, sync, Ruff, mypy, pytest (535 passed, 1 skipped, 85.09%), pip-audit, and
complete-history Gitleaks commands. Current-host generated shims remain blocked by OS error 4551;
module equivalents pass.

Historical 2026-08-26 closeout evidence follows:

```text
uv lock --check --offline                           PASS: 115-package resolution current
uv sync --locked (fresh disposable environment)    PASS: 62 packages installed
uv run ruff format --check .                        PASS: 132 files
uv run ruff check .                                 PASS
uv run mypy src                                     PASS: 62 source files
uv run pytest --basetemp runtime/...                PASS: 494 passed, 1 skipped, 85.02% coverage
pip-audit --path .venv/Lib/site-packages            PASS: no known vulnerabilities
gitleaks detect --source . --redact --no-banner     PASS: 8 commits, no leaks (716.89 KB)
git diff --check                                    PASS
uv run jarvis doctor                                PASS: configuration/storage/actions/Ollama/catalog
```

On 2026-08-26, Windows Application Control rejected the project virtual-environment and WinGet
launcher shims with operating-system error 4551. This was an environment-policy restriction, not
a project failure. The locked gates ran through the allowed uv-managed CPython 3.11 interpreter
with the locked project site-packages, and a clean sync installed 62 packages into the ignored
disposable `runtime/phase3-sync-env-20260826` environment. The three tests that intentionally spawn
`sys.executable` used the installed non-junction Python path for that fixture only; no source change
or security check bypass was retained. Dependency audit targeted the locked project environment;
the allowed base interpreter's unrelated global packages were excluded.

The doctor run used `PYTHONIOENCODING=utf-8` because the RTK-captured Windows console advertised
`cp1252`; all diagnostic checks passed after the already-installed local Ollama service was started.
Pytest emitted one third-party Starlette `TestClient` deprecation warning; no project test failed.

## Benchmarks

- Samples: 700 permission/grant validations; 250 fake broker dispatches; 24 production-handler
  reversible move/rollback round trips.
- Cold/warm: 20 authority and 10 broker warm-up operations excluded from reported distribution;
  file round trips are real one-shot filesystem operations.
- p50: authority 0.135 ms; broker 0.226 ms; move round trip 54.984 ms.
- p95: authority 0.234 ms (target <=25); broker 0.278 ms (target <=50); move round trip 60.343 ms.
- Errors/failures: zero invalid-grant false accepts, valid-control failures, duplicate effects,
  unauthorized effects, postcondition failures, rollback failures, or destination remnants.
- Hardware/runtime/model/device versions: Windows build 10.0.26200, AMD64, Python 3.11.16; Phase 3
  uses Win32/Core Audio directly and does not invoke a model in benchmark loops.
- Relevant settings: network/media/audio/clipboard/printing/application launch all false for the
  enforced benchmark; only a caller-supplied new disposable `runtime/` controlled root was mutated.
- Live acceptance: one separately authorized run on 2026-08-26 completed three brokered actions.
  App launch latency was 36.942 ms; near-no-op volume latency was 23.551 ms; media STOP dispatch
  latency was 16.636 ms. The fixture completed, volume readback and mute invariants passed, and the
  input pair was accepted. Evidence contains no private content or absolute enrolled identifiers.

## Security and privacy

- Threats tested: traversal/alternate-stream/reparse/hard-link/TOCTOU paths, argument injection,
  executable substitution, prompt/runtime direct-effect attempts, stale/replayed/cross-identity/
  mutated/wrong-action grants, policy change, audit failure, duplicate claim, cancellation,
  postcondition/rollback failure, printer failure sanitization, and acoustic replay/high-risk mapping.
- Data boundaries: all Phase 3 execution is local. Cloud providers receive only public tool
  schemas; private/unknown schemas and host allowlist identifiers are removed before provider
  requests. A guessed private tool call is denied before policy or execution. Private arguments,
  results, file content, clipboard content, and print content stay local.
- Permissions/approvals: deny by default; exact trusted grant required where policy says so.
- Audit/retention/deletion: exact expiring authority is private SQLite enforcement state; separate
  bounded lifecycle views omit arguments/content/actors/fingerprints/results. Clipboard prior text
  is materialized only after exact approved dispatch and remains volatile. Removing the private
  database deletes action and conversation state together; backup/retention implications documented.
- Secret scan: final scan passed across 8 commits and 716.89 KB; no leaks found.

## Blockers

- Current live app-launch, near-no-op volume, and media checks require separate real-application/
  device authorization. The exact operator authorization supplied for 2026-08-26 does not carry
  forward automatically; that historical run remains evidence only for that date.
- Physical printing is not required: discovery/status and fake spool submission provide the safe
  fixture. No private or physical job will be sent without separate authorization.

## Known limits and deferred scope

- Level 4/admin, communications, purchases, credential/security changes, arbitrary shell, broad
  recursive file operations, remote approvals, and general UI automation remain unsupported.
- Always-listening acoustic control and Phase 7 gesture recognition remain disabled/deferred.
- Windows worker-thread native calls cannot always be forcibly stopped after dispatch. Terminal
  receipt must report unknown postcondition/manual recovery rather than claim zero effect.

## Recovery and rollback

- Disable Phase 3 actions through configuration, expire/revoke outstanding grants, inspect the
  sanitized audit trail, and use operation-specific rollback/reconciliation. Source changes remain
  uncommitted and can be reviewed independently; no destructive Git command will be used.

## Final handoff

- Final status: `implemented-closeout-pending`; current safe gates pass, but current live effects
  were correctly withheld.
- Files changed: Phase 3 broker, permissions, Windows adapters, hands-free mapping, migrations,
  configuration/CLI/runtime integration, acceptance scripts, tests, and documentation. Existing
  uncommitted Phase 2 work remains preserved.
- Next recommended action: repeat the bounded live smoke only with separate authorization; keep
  authority default-off. Phase 4 is independently current-complete.
- Commit/push status: Phase 1–4 implementation, CI hardening, and final evidence reconciliation are
  committed and pushed to `origin/main`; remote SHA verification is recorded in the final handoff.
