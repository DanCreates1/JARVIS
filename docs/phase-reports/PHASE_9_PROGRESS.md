# Phase 9 Dedicated Server Migration Progress Report

Status: `in-progress`
Started: 2026-09-10
Updated: 2026-09-11
Active subphase: Phase 9B complete — Phase 9C deployment/resilience next
Recommended Codex model: `gpt-6-astra`
Recommended reasoning: `ultra`
Session start / five-hour stop: 2026-09-11T08:22:50-04:00 / 2026-09-11T13:22:50-04:00

## Objective

Add a reversible, encrypted SQLite state-transfer workflow bound to the Phase 9A topology manifest.
Prove no-overwrite backup/restore, logical shadow equality, exclusive cutover evidence, source-drift
denial, and rollback rehearsal without activating a remote server or second writer.

## Baseline

- Git branch/HEAD: `main` at `efdadda`, equal to `origin/main`.
- Worktree state and preserved unrelated changes: untracked
  `.codex_finish_jarvis_cleanup.ps1` belongs to the user and remains untouched.
- Relevant installed software/hardware/provider state: Windows; Python 3.11.9; SQLite 3.45.1;
  `cryptography` 50.0.1; `uv 0.12.5`; Git 2.55.0; Gitleaks 8.30.1; Node 24.20.0. No Phase 9
  migration key is configured or read from the environment.
- Existing tests and failures: focused Phase 8 identity plus Phase 9A topology suite passes 28
  tests with one dependency deprecation warning and no product failure.
- Prior phase evidence: Phase 8 is complete at `4a1338d`; Phase 9A is complete at `efdadda`. The
  final private deployment uses one
  Tailscale Serve HTTPS gateway, one loopback JARVIS process, immediate device/session revocation,
  and verified SQLite backup/restore. Multiple replicas and remote state remain prohibited.

## Acceptance checklist

### Phase 9B

- [x] A versioned encrypted migration bundle uses a caller-supplied 256-bit key, a unique nonce,
  authenticated metadata, key ID separation, online SQLite snapshotting, and exclusive creation.
- [x] Restore authenticates before use, never overwrites a path, checks database SHA-256,
  `integrity_check`, `foreign_key_check`, exact migrations/schema, and logical table fingerprints.
- [x] Shadow comparison proves exact logical equality while tolerating non-semantic SQLite layout;
  source drift, schema drift, corruption, wrong key, truncation, and topology mismatch fail closed.
- [x] Cutover/rollback receipts bind one owner, topology digest/epoch, source/target fingerprints,
  monotonic sequence, and previous receipt; no operation mutates the live source database.
- [x] Interruption, duplicate, ordering, stale writer, lock contention, disk/write failure,
  corruption, schema mismatch, partition-equivalent stale state, and rollback tests pass.
- [x] Fixed benchmark rehearses at least 100 backup/restore/shadow/cutover/rollback cycles with zero
  false accepts/data mismatches; backup/restore/shadow/cutover p95 targets are frozen before tuning.
- [x] Migration, RPO/RTO, key handling, recovery, architecture/security/setup, API, status, and
  phase-report documentation match implementation.
- [x] Full lock/sync, Ruff, mypy, pytest/coverage, dependency audit, Gitleaks, doctor, build, and Git
  whitespace gates pass.

Frozen Phase 9B targets: 100 complete local rehearsals; zero overwrite, unauthenticated restore,
logical mismatch, stale cutover, owner ambiguity, or accepted corruption; 64 MiB fixture database;
backup p95 <= 2,000 ms, restore p95 <= 2,000 ms, shadow comparison p95 <= 1,000 ms, cutover or
rollback receipt p95 <= 100 ms, recovery point objective of the accepted snapshot, operator-driven
recovery time objective <= 15 minutes, and benchmark RSS growth <= 100 MiB.

### Phase 9A

- [x] Local-only, split, and server-primary topology manifests have explicit node roles and exactly
  one owner for every mutable state/effect domain.
- [x] Shipped runtime remains local-only and refuses split/server-primary activation.
- [x] Authenticated protocol negotiation binds exact host/device/session/audience, topology digest,
  minimum version, offered/required capabilities, and configured node ownership.
- [x] Unsupported/stale/downgraded/mismatched/replayed/revoked negotiations fail closed; network
  loss has an explicit local-only fallback policy and never changes state ownership.
- [x] Capability grants are the intersection of protocol support, configured node allowance, and
  authenticated scope; a peer cannot self-add capability or ownership.
- [x] Fixed benchmark runs 10,000 valid negotiations and 10,000 downgrade/abuse negotiations with
  zero valid failures, zero false accepts, valid p95 <= 10 ms, and RSS growth <= 50 MiB.
- [x] ADR, topology/architecture/security/setup/API documentation, recovery behavior, and Phase 9
  report match implementation.
- [x] Full lock/sync, Ruff, mypy, pytest/coverage, dependency audit, Gitleaks, doctor, build, and Git
  whitespace gates pass.

## Milestones

### Phase 9A Milestone 1 — measured boundary, threat model, and topology ownership

- Status: complete
- Changes: baseline and frozen acceptance targets recorded; immutable profile/node/role/ownership/
  network-loss models and builders added with exact coverage and role-compatible owner validation.
- Evidence: Phase 8 final topology and focused identity/deployment tests inspected; current Tailscale
  Serve identity/capability guidance, RFC 9421 downgrade guidance, and NIST zero-trust service
  identity guidance reviewed on 2026-09-10.
- Remaining: none for 9A Milestone 1.

### Phase 9A Milestone 2 — authenticated version/capability protocol

- Status: complete
- Changes: added signed `ProtocolHello`, bounded version/capability intersection, session-expiring
  result, `topology.negotiate` scope, authenticated `/api/v1/topology/negotiate`, composition-root
  local manifest, content-free success/denial audit, and doctor visibility.
- Evidence: unit/security/integration tests cover exact identity/topology binding, highest-common
  version, required/optional capabilities, replay, stale signature, revoked/session middleware,
  digest/epoch/profile/host/device/session mismatch, unknown node, owner injection, scope loss, and
  offline fallback. Targeted 35-test identity/topology suite passed.
- Remaining: none for 9A Milestone 2.

### Phase 9A Milestone 3 — benchmark, recovery, and closeout

- Status: complete
- Changes: fixed benchmark, ADR, topology runbook, API/security/architecture/setup/configuration,
  roadmap/playbook/overview, recovery, and phase evidence added.
- Evidence: benchmark passed 20,000 cases; full suite passed 907 tests with 2 skips and 85.12%
  coverage. Lock/sync, Ruff, mypy, pip-audit, Gitleaks, build, doctor, and Git whitespace passed.
- Remaining: Phase 9B migration/backup/reconciliation; no 9A work remains.

### Phase 9B Milestone 1 — state classification, encrypted backup, and verified restore

- Status: complete
- Changes: classified all eight durable shared-state domains into one online SQLite snapshot; added
  versioned private manifests, caller-supplied key IDs, HKDF-separated AES-256-GCM bundles,
  exclusive destinations, and authenticated restore with current migration/schema/integrity/
  foreign-key/logical-fingerprint verification.
- Evidence: SQLite online-backup/integrity/foreign-key guidance, Python SQLite backup API,
  `cryptography` AES-GCM guidance, and NIST backup/key-management guidance reviewed on 2026-09-11;
  unit/security/full-suite gates cover wrong key, tamper, truncation, unsafe key path, schema drift,
  foreign-key corruption, topology mismatch, duplicate destination, and interrupted output.
- Remaining: none for 9B Milestone 1.

### Phase 9B Milestone 2 — shadow comparison, cutover fencing, and rollback

- Status: complete
- Changes: added layout-independent schema/table/row fingerprints, exact shadow comparison,
  dual-database writer locking, accepted-snapshot drift denial, and canonical chained cutover and
  rollback receipts with monotonically advancing topology epochs.
- Evidence: tests prove stale source, mismatched target, lock contention, receipt tamper, wrong
  predecessor/order, one-owner topology, and post-shadow stale-writer attempts fail closed; source
  and target database bytes remain unchanged by transition receipt creation.
- Remaining: none for 9B Milestone 2.

### Phase 9B Milestone 3 — benchmark, operations documentation, and closeout

- Status: complete
- Changes: added a fixed 100-cycle plus 64 MiB capacity benchmark, recovery runbook and CLI,
  architecture/security/setup/status updates, diagnostic boundary, adversarial tests, and package
  verification.
- Evidence: benchmark and every frozen threshold passed; 927 tests passed with 2 intentional skips
  and 85.02% coverage; dependency, secret, formatting, lint, type, doctor, build, and whitespace
  gates passed.
- Remaining: Phase 9C deployment/resilience; no 9B work remains.

## Decisions

- Decision: keep the executable runtime profile hard-locked to `local-only` during 9A.
- Reason: ownership and negotiation must be proven before any data transfer, remote writer, or
  second replica exists.
- Alternatives: activating split mode, adding PostgreSQL, or deploying a server now are rejected.
- Reversible later: Phase 9C may widen configuration only when deployment enforcement and chaos
  gates are complete.

- Decision: keep the migration workflow operator-driven and receipts non-authoritative in 9B.
- Reason: encryption and data equality do not prove deployment health, network fencing, or process
  ownership; automatic activation would create split-brain risk before 9C.
- Alternatives: automatic cutover, a second writer, PostgreSQL, and a server daemon are rejected.
- Reversible later: Phase 9C can enforce an accepted chained receipt as part of a tested deployment
  state machine.

- Decision: retain Phase 8 Ed25519 signed requests plus private TLS as the peer/server
  authentication envelope; negotiate only inside that authenticated session.
- Reason: transport membership or forwarded identity headers alone do not grant JARVIS authority.
- Alternatives: unsigned discovery, tailnet membership as authorization, and caller-declared
  capabilities are rejected.
- Reversible later: a dedicated mTLS/SPIFFE adapter may implement the same owned negotiation port.

## Verification evidence

```text
uv run pytest -q tests/unit/test_phase8_private_deployment.py
  tests/integration/test_phase8_remote_identity.py
  tests/integration/test_phase8_remote_web.py
  tests/security/test_phase8_remote_identity_security.py
31 tests passed; targeted command hit repository-wide coverage fail-under because only four files
were selected.

uv lock --check: 119 packages resolved
uv sync --locked: 68 packages checked
uv run ruff format --check .: 279 files already formatted
uv run ruff check .: passed
uv run mypy src: 121 source files, no issues
uv run pytest: 907 passed, 2 skipped, 85.12% coverage
uv run pip-audit: no known vulnerabilities
gitleaks detect --source . --redact --no-banner: 36 commits / ~3.98 MB, no leaks
uv build: wheel and source distribution passed; wheel contains jarvis/remote/topology.py
git diff --check: passed
uv run jarvis doctor: ready; local-only, one node, 11 owners, protocol 1.0, no remote writer

Phase 9B final gates, 2026-09-11:
uv lock --check: 119 packages resolved
uv sync --locked: 68 packages checked
uv run ruff format --check .: 286 files already formatted
uv run ruff check .: passed
uv run mypy src: 122 source files, no issues
uv run pytest: 927 passed, 2 skipped, 85.02% coverage, one dependency deprecation warning
uv run pip-audit: no known vulnerabilities
gitleaks detect --source . --redact --no-banner: 37 commits / ~4.07 MB, no leaks
uv build: source distribution and wheel passed; wheel contains jarvis/remote/migration.py
git diff --check: passed
uv run jarvis doctor: ready; migration boundary PASS, local-only, no key or remote writer enabled
```

## Benchmarks

- Samples: frozen at 10,000 valid plus 10,000 downgrade/abuse negotiations.
- Cold/warm: in-process warm contract benchmark; restart/authentication behavior tested separately.
- p50: valid 0.0558 ms; downgrade/abuse 0.0254 ms.
- p95: valid 0.0969 ms against <= 10 ms; downgrade/abuse 0.0291 ms.
- Errors/failures: zero valid failures; zero false accepts.
- Hardware/runtime/model/device versions: Windows laptop; Python 3.11 locked environment;
  synthetic authenticated service/laptop peers for 9A.
- Relevant settings: protocol `1.0`; exact topology digest; local-only runtime; no migration,
  remote writer, extra replica, or new database.
- Resource growth: 1.102 MiB RSS against <= 50 MiB.

### Phase 9B migration rehearsal

- Samples: 100 full backup/restore/shadow/cutover/rollback cycles, 100 corrupted-tag restore
  attempts, and one 64 MiB payload-capacity fixture producing a 69,890,048-byte database.
- Cold/warm: local operator rehearsal in one fixed process; every cycle uses fresh paths and a
  unique encrypted bundle nonce.
- p50: backup 33.107 ms; restore 21.878 ms; shadow 25.944 ms; cutover plus rollback 47.447 ms.
- p95: backup 40.480 ms against <= 2,000 ms; restore 25.292 ms against <= 2,000 ms; shadow
  28.726 ms against <= 1,000 ms; cutover plus rollback 52.138 ms against <= 100 ms.
- Errors/failures: zero operation failures, zero data mismatches, zero false accepts; all 100
  corrupted bundles rejected.
- Hardware/runtime/model/device versions: Windows laptop; Python 3.11.9; SQLite 3.45.1; local
  deterministic migration workflow with no model/provider call.
- Relevant settings: 256-bit test key held outside the bundle; HKDF-SHA256 per-bundle derivation;
  AES-256-GCM; remote manifest epoch 7 and local rollback epoch 8; no runtime topology activation.
- Resource growth: 9.180 MiB RSS against <= 100 MiB.

## Security and privacy

- Threats tested: stale/skew/revoke/replay, wrong host/device/session/audience, unknown node,
  topology digest mismatch, version downgrade/mismatch, capability escalation, owner substitution,
  duplicate fields, oversize input, and fallback abuse.
- Data boundaries: negotiation contains identifiers, versions, capability names, digests, and
  content-free outcomes only; no prompt, user content, credential, key, or private state.
- Permissions/approvals: exact `topology.negotiate` scope required; model/chat cannot enroll a peer,
  choose ownership, grant capability, or change runtime topology.
- Audit/retention/deletion: content-free success/denial events in existing bounded Phase 8
  identity audit; no new mutable data schema in 9A.
- Secret scan: Gitleaks passed across 36 commits and the worktree.

### Phase 9B additions

- Threats tested: wrong key/key ID, ciphertext/tag tamper, truncation, malformed/oversize input,
  symlink key file, topology/owner/epoch mismatch, duplicate path, stale snapshot/writer, lock
  contention, schema/migration drift, foreign-key corruption, receipt tamper/order, simulated disk
  failure, and partition-equivalent stale state.
- Data boundaries: bundle metadata and the SQLite snapshot are authenticated and encrypted together;
  only content-free operation IDs, digests, byte counts, topology references, and result codes leave
  the private manifest. Database contents and migration keys never enter logs or receipts.
- Permissions/approvals: a separate operator-held 256-bit key is mandatory; migration commands do
  not enable a server, change `Settings`, mutate the live database, or grant runtime ownership.
- Audit/retention/deletion: receipts are immutable no-overwrite evidence. Operators retain or delete
  bundles, restored databases, keys, and receipts under the documented recovery policy.
- Secret scan: Gitleaks passed across 37 commits and the worktree; tests also confirm a private
  marker and the migration key are absent from bundle-visible bytes.

## Blockers

- None for Phase 9B local implementation. Server purchase/deployment remains outside this subphase
  and requires Phase 9C execution authority.

## Known limits and deferred scope

- Receipts prove a safe transition candidate but do not activate topology. Server deployment,
  pinned packaging, TLS/key rotation automation, health/telemetry, network chaos, offline parity,
  PostgreSQL, multi-replica operation, and failover remain Phase 9C or later scope.
- RPO is the exact accepted snapshot, not later source writes. RTO <= 15 minutes is an operator
  objective supported by the fast local rehearsal, not a production-server measurement.

## Recovery and rollback

- Keep runtime topology `local-only`; remove/disable the additive negotiation route to roll back
  9A. Existing Phase 8 identity and private phone deployment continue unchanged.
- Phase 9B recovery: stop writers, restore the authenticated bundle to a new path, run exact shadow
  comparison, create a cutover receipt only while both writer locks hold, and retain the source.
  Roll back by restoring the accepted state to a new local path and creating a chained rollback
  receipt under a higher-epoch local-only manifest. Never reuse a nonce/key pair, overwrite a
  destination, or treat a receipt as automatic authority.

## Final handoff

- Final status: Phase 9A and Phase 9B complete; aggregate Phase 9 remains in progress.
- Files changed: encrypted migration contracts/workflow and CLI, recovery diagnostics, fixed
  benchmark, unit/security tests, migration runbook, and architecture/security/setup/status docs.
- Next recommended phase: Phase 9C deployment/resilience. Do not activate split mode or a remote
  writer until pinned deployment, receipt enforcement, health, chaos, offline, and rollback gates
  pass.
- Commit/push status: authorized by standing repository instruction; final gated Phase 9B change
  set is committed and pushed to configured `origin/main` after this report is finalized.
