# Phase 8 Secure Phone/PWA Progress Report

Status: `in-progress`  
Started: 2026-09-09  
Updated: 2026-09-10  
Active subphase: Phase 8C — PWA/reconnect transport (next)
Recommended Codex model: `gpt-6-astra`  
Recommended reasoning: `ultra`  
Phase 8B session / five-hour stop: 2026-09-10T06:27:00-04:00 / 2026-09-10T11:27:00-04:00

## Objective

Build Phase 8B's deny-by-default trusted browser and approval boundary on the completed Phase 8A
device identity foundation. Add durable browser sessions, secure cookie and CSRF/origin controls,
strict CORS/CSP and bounded request/rate policy, and a remote approval surface that preserves exact
Phase 3 authority while forcing sensitive work back to the local host. Keep every listener
loopback-only; TLS/private-network deployment and phone/PWA UI remain later Phase 8 subphases.

## Baseline

- Git branch/HEAD at 8B start: `main` at `79f8738`; local HEAD equalled `origin/main`.
- Worktree state and preserved unrelated changes: untracked `.codex_finish_jarvis_cleanup.ps1`
  belongs to the user and remains untouched.
- Relevant installed software/hardware/provider state: Python 3.11 project managed by `uv 0.12.5`;
  FastAPI loopback server; Git 2.55.0; Gitleaks 8.30.1; Node 24.20.0. No remote listener is
  configured; trusted browser origins default empty.
- Existing tests and failures: Phase 8A closeout reported 827 passed, 2 skipped, 85.14% coverage.
  No Phase 8B baseline product failure was observed.
- Prior phase evidence: Phase 3 broker is complete except separately authorized live-effect
  revalidation. Phase 7 is complete. Existing web API refuses non-loopback binding.

## Acceptance checklist

### Phase 8B

- [x] Signed enrolled-device bootstrap issues only a durable, short-lived browser session.
- [x] Browser session cookie is `Secure`, `HttpOnly`, `SameSite=Strict`, host-only, and cleared on
  logout; CSRF material is separately bound by digest and never persisted in plaintext.
- [x] Exact configured HTTPS origin is required for browser bootstrap and every cookie-authenticated
  request; unsafe methods additionally require exact CSRF header proof.
- [x] Strict CORS has no wildcard or credential reflection; disallowed/null/duplicate origins fail
  closed and preflight is bounded.
- [x] API responses use strict CSP, anti-framing, no-sniff, referrer, permissions, HSTS, and
  no-store headers without breaking the legacy loopback-only page.
- [x] Header, query, body, and request-rate ceilings fail closed with generic responses and bounded
  in-memory limiter state.
- [x] Signed-API and browser session types are non-interchangeable; theft, CSRF, origin confusion,
  spoofing, expiry, rotation, revocation, restart, and concurrent-limit tests pass.
- [x] Remote approval binds exact host/device/session/action fingerprint and capabilities; Level 0-1
  may use an eligible enrolled device, while Levels 2-4 require the trusted local host and cannot be
  approved remotely.
- [x] Browser/auth/approval audit is content-free and contains no token, cookie, CSRF value,
  signature, public key, request body, action arguments, or private content.
- [x] Fixed abuse/performance thresholds, full release gates, documentation, recovery, and status
  evidence pass.

Frozen Phase 8B benchmark thresholds: 10,000 valid browser authentications and 10,000 invalid-CSRF
attempts; valid p95 <= 10 ms; zero valid failures; zero false accepts; RSS growth <= 50 MiB; browser
denial audit remains bounded by Phase 8A's per-device retention ceiling.

### Phase 8A (complete baseline)

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

### Phase 8B Milestone 1 — Browser threat model and contracts

- Status: complete
- Changes: typed browser credential/session-kind contracts, strict origin policy, frozen request and
  rate ceilings, exact remote approval rules, and pre-tuning benchmark thresholds.
- Evidence: unit tests cover origin confusion, limiter reset/bounds, configuration validation, exact
  fingerprint approval, risk ceiling, recent authentication, scope, session, and local escalation.

### Phase 8B Milestone 2 — Durable browser authentication

- Status: complete
- Changes: migration 010, signed browser bootstrap, type-separated cookie authentication, CSRF
  digest, expiry/revocation/rotation/restart behavior, and content-free audit.
- Evidence: integration/security tests verify digest-only persistence, restart, wrong-session-type,
  wrong device type/scope, stolen token, CSRF, device revocation, and secure cookie attributes.

### Phase 8B Milestone 3 — Web/API hardening and trusted approval

- Status: complete
- Changes: exact origin/CORS/preflight policy, hashed CSP, browser security headers, streamed body
  ceiling, bounded per-IP/identity limiter, diagnostics, and exact remote approval surface.
- Evidence: browser tests cover allowed/denied/null origins, cookie-without-origin denial, CSRF,
  CORS non-wildcard behavior, header/query/body/rate limits, logout, and no remote action route.

### Phase 8B Milestone 4 — Abuse/performance/recovery closeout

- Status: complete
- Changes: 20,000-case browser/CSRF benchmark, complete threat/recovery/configuration docs, patched
  audit environment dependency, and current repository status.
- Evidence: 844 passed, 2 skipped, 85.11% coverage; benchmark passed; dependency and secret scans
  clean; doctor confirms browser bootstrap disabled by default and listener loopback-only.

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
  a future step-up adapter.
- Reversible later: owned identity/request contracts allow a WebAuthn/OIDC credential adapter
  without weakening device, audience, scope, replay, or revocation checks.

- Decision: Phase 8A remains loopback-only and exposes no non-loopback/TLS listener.
- Reason: deployment/exposure requires separate owner authority and is Phase 8D scope.
- Alternatives: none within 8A.
- Reversible later: reviewed TLS/private-network gateway can be enabled behind the same API.

## Verification evidence

```text
ruff format --check .: 261 files formatted
ruff check .: passed
mypy src: 117 source files, no issues
targeted Phase 8A-8B suite: 35 passed
full pytest: 844 passed, 2 skipped, 85.11% coverage
uv lock --check: 119 packages resolved
pip-audit: no known vulnerabilities; setuptools 84.0.0 explicitly present in dev audit environment
gitleaks: 32 commits / ~3.72 MB scanned, no leaks
git diff --check: passed
jarvis doctor: ready; browser cookie bootstrap disabled without exact HTTPS origin; loopback
127.0.0.1:8765
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

Phase 8B browser benchmark:

- Samples: 10,000 valid cookie authentications and 10,000 invalid-CSRF attempts.
- p50: valid 0.6099 ms; abuse 0.9484 ms.
- p95: valid 1.0132 ms against <= 10 ms; abuse 1.3695 ms.
- Errors/failures: 0 valid failures; 0 false accepts.
- Resource/storage: 6.055 MiB RSS growth against <= 50 MiB; 1,048,576-byte SQLite database;
  exactly 1,000 retained device denial events against <= 1,000.
- Runtime/device: Windows laptop, Python 3.11.16, synthetic Ed25519 browser fixture; local warm
  verification, with restart behavior tested separately.

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
- Secret scan: Gitleaks passed across 32 commits and the worktree.

Phase 8B additions:

- Threats tested: cookie theft/type confusion, missing/wrong/duplicate CSRF, missing/null/hostile or
  suffix-confused Origin, wildcard/reflected CORS, malicious header/path/query/body size, brute-rate
  exhaustion, session restart/revocation, wrong device type/scope, stale remote authentication,
  cross-session approval, capability loss, risk-ceiling breach, and Level 2-4 remote approval.
- Data boundaries: cookie and CSRF plaintext returned once only; digest-only persistence; limiter
  uses client IP plus truncated device ID or cookie digest, never plaintext cookie/body/action data.
- Permissions/approvals: `approval.review` is explicit; exact phrase/fingerprint and same trusted
  identity required; Level 2-4 stay local; no remote execution route exists.
- Browser bootstrap default: disabled until exact HTTPS origin configuration; listener still
  loopback-only.

## Blockers

- None for safe local Phase 8A-8B implementation. Real phone, TLS, private-network deployment, and
  non-loopback exposure require later Phase 8D authority and are not attempted.

## Known limits and deferred scope

- Passkey/OIDC step-up remains optional future hardening; current browser bootstrap uses the enrolled
  device signature and a five-minute recent-auth window for low-risk approval only.
- PWA client, reconnect/resume, offline shell, notifications: Phase 8C.
- TLS/private topology, firewall/Tailscale deployment, real phone enrollment/revocation and scan:
  Phase 8D.

## Recovery and rollback

- Keep `JARVIS_WEB_HOST=127.0.0.1` and `JARVIS_TRUSTED_BROWSER_ORIGINS=[]` to disable browser
  bootstrap. Revoke a device to invalidate all API/browser sessions. Existing migration 010 is
  additive; rollback disables routes/configuration rather than deleting durable identity data.

## Final handoff

- Final status: Phase 8A-8B complete; Phase 8 overall remains in progress.
- Files changed: browser identity/policy contracts, migration 010, remote store/service, web
  middleware/routes, configuration/diagnostics, approval surface, tests, benchmark, dependency
  audit records, ADR, API/recovery/security/architecture/setup/status docs.
- Next recommended phase: Phase 8C PWA, product transport, reconnect/resume, offline shell, and
  notification controls.
- Commit/push status: standing repository authorization applies after final review; exact commit is
  reported at handoff.
