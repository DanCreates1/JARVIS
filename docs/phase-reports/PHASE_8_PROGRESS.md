# Phase 8 Secure Phone/PWA Progress Report

Status: `in-progress`  
Started: 2026-09-09  
Updated: 2026-09-10  
Active subphase: Phase 8B — trusted approval/web hardening  
Recommended Codex model: `gpt-6-astra`  
Recommended reasoning: `ultra`  
Session start / five-hour stop: 2026-09-09T23:33:32-04:00 / 2026-09-10T04:33:32-04:00

## Objective

Ship the deny-by-default Phase 8A identity boundary: versioned API/event contracts, unique
asymmetric device identities, locally authorized one-time enrollment, device-bound short-lived
sessions, proof-of-possession key rotation, immediate revocation, replay protection, scoped
authorization, durable sanitized audit, and restart-safe recovery. Keep every listener loopback-only;
TLS/private-network deployment and phone/PWA UI remain later Phase 8 subphases.

## Baseline

- Git branch/HEAD: `main` at `b9fa115`; local HEAD equals `origin/main`.
- Worktree state and preserved unrelated changes: untracked `.codex_finish_jarvis_cleanup.ps1`
  belongs to the user and remains untouched.
- Relevant installed software/hardware/provider state: Python 3.11 project managed by `uv 0.12.5`;
  FastAPI loopback server; Git 2.55.0; Gitleaks 8.30.1; Node 24.20.0. No remote listener or remote
  identity dependency is configured.
- Existing tests and failures: Phase 7 closeout reports 808 passed, 2 skipped, 85.34% coverage.
  Current Phase 8A targeted and release gates remain to be run.
- Prior phase evidence: Phase 3 broker is complete except separately authorized live-effect
  revalidation. Phase 7 is complete. Existing web API refuses non-loopback binding.

## Acceptance checklist

- [x] Versioned owned API and event subscription contracts expose only explicit scopes.
- [x] Unique Ed25519 device public keys; no shared API key or stored device private key.
- [x] One-time, expiring, locally created enrollment challenge with exact approved scope/risk.
- [x] Short-lived opaque sessions store only token digests and bind host/device/key/audience/scope.
- [x] Every protected request signs method, authority, raw path/query, body digest, date, nonce,
  audience, device, key version, and session token digest context.
- [x] Atomic nonce consumption rejects replay across concurrency and process restart.
- [x] Key rotation proves old and new key possession, increments version, and revokes old sessions.
- [x] Device revocation immediately blocks requests and revokes every session.
- [x] Invalid token type/audience/device/key/scope, expiry, skew, malformed signature, and restart
  fail closed without secret or cross-device leakage.
- [x] Enrollment/session/revocation/rotation/denial audit is append-only, bounded, and content-free.
- [x] Authentication p95 <= 10 ms for at least 10,000 local verifications; zero false accepts in
  at least 10,000 mixed abuse attempts; bounded memory growth <= 50 MiB.
- [x] Migration, recovery, API/ADR/security/setup documentation, and dependency/license records.
- [x] Full release, vulnerability, secret, Git, and doctor gates pass.

## Milestones

### Milestone 1 — Threat model and owned contracts

- Status: complete
- Changes: acceptance thresholds, owned models, exact scopes, canonical signature profile, and
  generic external error boundary.
- Evidence: RFC 9421 request-component coverage, official `cryptography` Ed25519 guidance, NIST
  session-cookie guidance, and Python `secrets` guidance reviewed on 2026-09-09.
- Remaining: none for Phase 8A.

### Milestone 2 — Durable identity lifecycle

- Status: complete
- Changes: migration 009; enrollment, device, session, nonce, and audit stores; Ed25519 enrollment;
  hashed sessions; restart-safe replay; rotation and local revocation.
- Evidence: integration tests cover one-use challenge, stored hashes, process restart, 20-way nonce
  race, expiry/skew, key change, session invalidation, and device revocation.
- Remaining: browser credential storage belongs to Phase 8B/8C.

### Milestone 3 — Versioned API authentication middleware

- Status: complete
- Changes: authenticated `/api/v1` identity routes, strict route scope, signed raw request target,
  1 MiB body bound, one-header rule, generic no-store failures, CLI administration, diagnostics.
- Evidence: API tests cover enrollment/session/identity/events/logout, token type, query tamper,
  replay, scope expansion, and secret-free device-only audit.
- Remaining: Phase 8B web/origin/rate/approval hardening; Phase 8C product routes/client.

### Milestone 4 — Abuse/performance/recovery closeout

- Status: complete for 8A
- Changes: security suite, fixed 20,000-attempt benchmark, denial retention, recovery/API/ADR/setup
  documentation, current dependency resolution.
- Evidence: 827 passed, 2 skipped, 85.14% coverage; benchmark passed all frozen thresholds; dependency
  audit and Gitleaks clean; doctor confirms loopback-only identity availability.
- Remaining: Phase 8B-8D and real-phone/network evidence.

## Decisions

- Decision: Use Ed25519 proof-of-possession credentials and server-side hashed opaque sessions.
- Reason: unique asymmetric device identity avoids shared secrets; signed requests remain bound to
  the enrolled key while session tokens are never stored in plaintext.
- Alternatives: shared HMAC API keys rejected; full WebAuthn/OIDC and browser passkeys belong with
  the Phase 8B trusted web surface.
- Reversible later: owned identity/request contracts allow a WebAuthn/OIDC credential adapter
  without weakening device, audience, scope, replay, or revocation checks.

- Decision: Phase 8A remains loopback-only and exposes no non-loopback/TLS listener.
- Reason: deployment/exposure requires separate owner authority and is Phase 8D scope.
- Alternatives: none within 8A.
- Reversible later: reviewed TLS/private-network gateway can be enabled behind the same API.

## Verification evidence

```text
ruff format --check .: 254 files formatted
ruff check src tests scripts: passed
mypy src: 115 source files, no issues
targeted Phase 8A/CLI/diagnostic suite: 44 passed
full pytest: 827 passed, 2 skipped, 85.14% coverage
uv lock --check: 119 packages resolved
pip-audit: no known vulnerabilities
gitleaks: 31 commits / ~3.56 MB scanned, no leaks
git diff --check: passed
jarvis doctor: ready; remote API identity PASS; loopback 127.0.0.1:8765
```

## Benchmarks

- Samples: 10,000 valid signed requests and 10,000 invalid-signature abuse requests.
- Cold/warm: local warm verification; restart behavior tested separately.
- p50: valid 0.9975 ms; abuse 1.4192 ms.
- p95: valid 1.5130 ms; abuse 1.9847 ms; valid target <= 10 ms.
- Errors/failures: 0 valid failures; 0 false accepts.
- Resource growth: 4.285 MiB RSS against <= 50 MiB; 3,739,648-byte SQLite database; exactly 1,000
  retained device denial events against <= 1,000.
- Hardware/runtime/model/device versions: Windows laptop, Python 3.11.16; synthetic Ed25519 device
  fixtures only in 8A.
- Relevant settings: 15-minute session TTL, 5-minute enrollment TTL, 60-second clock skew,
  audience `jarvis-api`, exact known scopes; thresholds fixed before implementation.

## Security and privacy

- Threats tested: replay, concurrent replay, restart replay, stolen token without matching device key,
  query/body/component tamper, wrong token type/audience/device/key/scope, scope expansion,
  rotation/revocation, expiry/skew, invalid enrollment proof, malformed canonical inputs, and audit
  mutation/retention.
- Data boundaries: public keys, token/challenge digests, content-free lifecycle metadata only.
- Permissions/approvals: enrollment creation is local trusted host work; model/chat cannot enroll,
  rotate, revoke, choose scopes, or create sessions.
- Audit/retention/deletion: update-protected lifecycle audit; denial events capped at 1,000 per
  device/enrollment; expired nonces removed during atomic consumption; token/challenge plaintext is
  never persisted.
- Secret scan: Gitleaks passed across 31 commits and the worktree.

## Blockers

- None for safe local Phase 8A implementation. Real phone, TLS, private-network deployment, and
  non-loopback exposure require later Phase 8D authority and are not attempted.

## Known limits and deferred scope

- Passkey/OIDC host authentication, browser cookies, trusted remote approvals, CSRF/CORS/CSP/rate
  hardening: Phase 8B.
- PWA client, reconnect/resume, offline shell, notifications: Phase 8C.
- TLS/private topology, firewall/Tailscale deployment, real phone enrollment/revocation and scan:
  Phase 8D.

## Recovery and rollback

- Keep `JARVIS_WEB_HOST=127.0.0.1`. Revoke a device to invalidate all sessions. Remove the Phase 8A
  API composition wiring to return to local legacy API; existing Phase 1–7 schemas remain intact.

## Final handoff

- Final status: Phase 8A complete; Phase 8 overall remains in progress.
- Files changed: remote identity package, migration, runtime/web/CLI/diagnostics integration, tests,
  benchmark, lock/dependency records, ADR, API/recovery/security/architecture/setup/status docs.
- Next recommended phase: Phase 8B trusted approval/web hardening.
- Commit/push status: standing repository authorization applies after final review; exact commit is
  reported at handoff.
