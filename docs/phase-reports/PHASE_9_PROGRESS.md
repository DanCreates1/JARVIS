# Phase 9 Dedicated Server Migration Progress Report

Status: `in-progress`
Started: 2026-09-10
Updated: 2026-09-11
Active subphase: Phase 9A complete; Phase 9B next
Recommended Codex model: `gpt-6-astra`
Recommended reasoning: `ultra`
Session start / five-hour stop: 2026-09-10T23:12:03-04:00 / 2026-09-11T04:12:03-04:00

## Objective

Define local-only, split, and server-primary roles without activating remote deployment; establish
an exact single-owner map for mutable state and device effects; and add an authenticated,
downgrade-resistant version/capability negotiation contract behind the Phase 8 identity boundary.

## Baseline

- Git branch/HEAD: `main` at `4a1338d`, equal to `origin/main`.
- Worktree state and preserved unrelated changes: untracked
  `.codex_finish_jarvis_cleanup.ps1` belongs to the user and remains untouched.
- Relevant installed software/hardware/provider state: Windows; `uv 0.12.5`; Git 2.55.0;
  Gitleaks 8.30.1; Node 24.20.0. No Phase 9 credential environment variable is present.
- Existing tests and failures: focused Phase 8 identity/deployment suite has 31 passing tests. Its
  targeted invocation exits nonzero only because repository-wide 85% coverage cannot be measured
  from four selected files; this is not a product-test failure.
- Prior phase evidence: Phase 8 is complete at `4a1338d`; its final private deployment uses one
  Tailscale Serve HTTPS gateway, one loopback JARVIS process, immediate device/session revocation,
  and verified SQLite backup/restore. Multiple replicas and remote state remain prohibited.

## Acceptance checklist

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

## Decisions

- Decision: keep the executable runtime profile hard-locked to `local-only` during 9A.
- Reason: ownership and negotiation must be proven before any data transfer, remote writer, or
  second replica exists.
- Alternatives: activating split mode, adding PostgreSQL, or deploying a server now are rejected.
- Reversible later: Phase 9B may widen configuration only after backup/restore and cutover rehearsal.

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

## Blockers

- None for Phase 9A local implementation. Server purchase/deployment and migration remain outside
  this subphase and require later authority.

## Known limits and deferred scope

- State transfer, backup format changes, reconciliation, cutover, PostgreSQL, server deployment,
  multi-replica operation, and failover belong to 9B/9C.

## Recovery and rollback

- Keep runtime topology `local-only`; remove/disable the additive negotiation route to roll back
  9A. Existing Phase 8 identity and private phone deployment continue unchanged.

## Final handoff

- Final status: Phase 9A complete; Phase 9 remains in progress.
- Files changed: topology/protocol contracts, configuration/composition/diagnostics, signed API
  route and audit, benchmark, tests, ADR/runbook, architecture/security/setup/API/status docs.
- Next recommended phase: Phase 9B migration/backup/reconciliation. Do not activate split mode or
  a remote writer before verified backup/restore, shadow comparison, cutover, and rollback.
- Commit/push status if separately authorized: pending completed work and gates.
