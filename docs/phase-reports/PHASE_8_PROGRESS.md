# Phase 8 Secure Phone/PWA Progress Report

Status: `in-progress`
Started: 2026-09-09
Updated: 2026-09-10
Active subphase: Phase 8D — private-network/TLS and real-phone validation
Recommended Codex model: `gpt-5.6-terra`
Recommended reasoning: `high`
Phase 8C session / five-hour stop: 2026-09-10T08:31:56-04:00 / 2026-09-10T13:31:56-04:00

## Objective

Build Phase 8C's installable, responsive PWA and scoped product transport on the completed Phase
8A-8B identity/browser boundary. Add deterministic enrollment/session handling, resumable ordered
chat/task/device subscriptions, offline-safe shell behavior, explicit private-notification controls,
and complete logout cleanup. Keep every listener loopback-only; TLS/private-network deployment and
real-phone validation remain Phase 8D.

## Baseline

- Git branch/HEAD at 8C start: `main` at `bbbc9ce`; local HEAD equalled `origin/main`.
- Worktree state and preserved unrelated changes: untracked `.codex_finish_jarvis_cleanup.ps1`
  belongs to the user and remains untouched.
- Relevant installed software/hardware/provider state: Python 3.11 project managed by `uv 0.12.5`;
  FastAPI loopback server; Git 2.55.0; Gitleaks 8.30.1; Node 24.20.0. No remote listener is
  configured; trusted browser origins default empty.
- Existing tests and failures: Phase 8B closeout reported 844 passed, 2 skipped, 85.11% coverage.
  Seventeen targeted Phase 8A-8B tests passed at the 8C baseline; no product failure was observed.
- Prior phase evidence: Phase 3 broker is complete except separately authorized live-effect
  revalidation. Phase 7 is complete. Existing web API refuses non-loopback binding.

## Acceptance checklist

### Phase 8C

- [x] Installable responsive PWA shell works without caching API responses, private content, or
  credentials; offline mode exposes shell/status/logout only and cannot queue effects.
- [x] Browser client creates and stores a non-exportable per-device Ed25519 key, completes exact
  local-ticket enrollment, and obtains only the approved browser scopes.
- [x] Authenticated `/api/v1` product routes expose bounded chat, task status, device status, and
  desired event subscriptions without weakening Phase 8B scope/origin/CSRF/rate enforcement.
- [x] Ordered event envelopes have opaque subscription IDs and monotonic cursors; reconnect resumes
  after the acknowledged cursor without duplicates, gaps, cross-device/session leakage, or zombies.
- [x] Network flaps, response loss, duplicate/out-of-order frames, cursor expiry, session expiry,
  revocation, restart, and multi-tab ownership fail safely and visibly.
- [x] Logout revokes the browser session and clears CSRF, device key, cursor, subscriptions,
  notification state, cached shell state, and service-worker/cache ownership.
- [x] Notifications are opt-in, local to the PWA, generic by default, and never place message/task
  content in notification text, tags, URLs, persistent cache, or audit.
- [x] Keyboard/screen-reader/accessibility behavior, fixed reconnect/resource benchmark, full release
  gates, documentation, recovery, and status evidence pass.

Frozen Phase 8C targets: 10,000 ordered synthetic event frames across at least 100 reconnects;
zero duplicates, gaps, cross-session deliveries, offline effects, or retained private payloads;
event-resume p95 <= 25 ms; shell asset total <= 250 KiB; RSS growth <= 50 MiB; bounded server/client
cursor and subscription state.

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

### Phase 8C Milestone 1 — PWA state and transport contracts

- Status: complete
- Changes: frozen acceptance/resource targets; typed event, subscription, cursor, request-id, expiry,
  ownership, topic, payload, retention, and capacity contracts.
- Evidence: unit tests cover ordered bounded resume, 100 concurrent publishers, cursor expiry,
  cross-session denial, oversize rejection, wait cancellation, zombie state, session expiry, and
  request-cache capacity/idempotency.
- Remaining: none for Phase 8C.

### Phase 8C Milestone 2 — Scoped product API and reconnect stream

- Status: complete
- Changes: authenticated status/task/chat/subscription/event routes with exact host/scope checks,
  bounded finite SSE pages, monotonic cursors, response-loss idempotency, and logout purge.
- Evidence: synthetic Ed25519 browser integration covers enrollment, cookie/CSRF bootstrap, exact
  scopes, task/status minimization, chat retry, once-only events, resume keepalive, session purge,
  and post-logout denial.
- Remaining: none for Phase 8C.

### Phase 8C Milestone 3 — Installable offline-safe client

- Status: complete
- Changes: installable responsive shell, exact five-asset service-worker allowlist, Web Crypto
  Ed25519 enrollment/signing, IndexedDB non-exportable key, memory-only CSRF, session cursors,
  navigator-lock tab ownership, generic opt-in notifications, offline-safe controls, and full local
  cleanup even when server revocation is unavailable.
- Evidence: package/static tests enforce CSP, no inline script, no `localStorage`, shell ceiling,
  no API cache path, and packaged assets. Real Chromium pass at 390x844 exposed labelled controls,
  heading/list/log semantics, readable responsive layout, and zero console warnings/errors.
- Remaining: real-phone installation belongs to Phase 8D.

### Phase 8C Milestone 4 — Abuse/performance/recovery closeout

- Status: complete
- Changes: deterministic 10,000-frame/100-reconnect benchmark, PWA doctor check, packaged-wheel
  verification, ADR, security/architecture/API/setup/recovery/status documentation, and full gates.
- Evidence: 856 passed, 2 skipped, 85.09% coverage; benchmark passed all frozen thresholds; Ruff,
  mypy, lock/sync, build, pip-audit, Gitleaks, Node syntax, `git diff --check`, and doctor passed.
- Remaining: Phase 8D authority and physical network/phone evidence.

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

- Decision: Use finite, cursor-addressed SSE pages over a bounded process-local event hub.
- Reason: browser reconnect can explicitly acknowledge one monotonic cursor while subscription,
  payload, expiry, and ownership state stay simple, inspectable, session-bound, and purgeable.
- Alternatives: WebSocket multiplexing and durable private-content queues rejected for Phase 8C;
  both increase state and recovery risk without improving the required loopback client.
- Reversible later: the owned event envelope and cursor contract can sit over a durable broker if a
  later phase establishes an encrypted retention policy.

- Decision: Cache only five immutable public shell assets; keep the private key as a non-exportable
  IndexedDB `CryptoKey`, CSRF in memory, and cursor/notification choices in tab session storage.
- Reason: offline rendering needs no user content, API response, session secret, or effect queue.
- Alternatives: cache-all/runtime caching and persistent bearer/CSRF storage rejected.
- Reversible later: cache version and shell files can evolve without changing API data boundaries.

## Verification evidence

```text
ruff format --check .: 268 files formatted
ruff check .: passed
mypy src: 119 source files, no issues
targeted Phase 8C suite: 20 passed
full pytest: 856 passed, 2 skipped, 85.09% coverage
uv lock --check: 119 packages resolved
uv sync --locked: 68 packages checked
wheel/sdist build: passed; all six shell assets present in wheel
Node syntax: app.js and sw.js passed
pip-audit: no known vulnerabilities
gitleaks: full history and worktree / ~3.81 MB scanned, no leaks
git diff --check: passed
jarvis doctor: ready; PWA shell 22,189 bytes; browser bootstrap disabled without exact HTTPS origin;
loopback 127.0.0.1:8765
```

Phase 8C revalidated 2026-09-10 against the completed worktree. Real Chromium at 390x844 rendered
the offline shell with accessible labels/landmarks and no console warning/error. Non-loopback bind,
TLS gateway, firewall changes, private-network exposure, and physical-phone actions were not
attempted because they are Phase 8D and require separate authority.

Revalidated 2026-09-10 at `eb53075`: the full suite again passed with 844 tests, 2 skips, and
85.11% coverage; Ruff, mypy, pip-audit, Gitleaks, `git diff --check`, and `jarvis doctor` passed.
The repeated 20,000-case Phase 8B benchmark had zero valid failures and zero false accepts, valid
p50/p95 0.6849/0.9487 ms, abuse p50/p95 1.2314/2.4253 ms, 5.703 MiB RSS growth, and exactly 1,000
retained denial events.

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

Phase 8C PWA/reconnect benchmark:

- Samples: 10,000 ordered event frames over 100 fresh reconnect subscriptions, 100 events each.
- p50/p95 resume: 0.0335/0.0578 ms; p95 target <= 25 ms.
- Errors/failures: 0 duplicates, gaps, cross-session deliveries, or offline effects.
- Resource/storage: 0.617 MiB RSS growth against <= 50 MiB; 22,189-byte packaged shell against
  <= 250 KiB; 0 retained subscriptions/private request results after session clear.
- Runtime/device: Windows laptop, Python 3.11.16, synthetic browser contexts; real Chromium shell
  layout separately checked at a 390x844 phone viewport.

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

Phase 8C additions:

- Threats tested: duplicate/concurrent/out-of-order frames, expired/lost cursor, response retry,
  subscription/session ownership confusion, capacity exhaustion, oversized event/result, waiter
  cancellation, zombie publication, logout retention, hostile topic scope, and offline effect queue.
- Data boundaries: five public shell assets only in Cache Storage; API/chat/task/device content is
  never cached; private event/request buffers are fixed-size, expire no later than the browser
  session, and are erased on logout/restart.
- Browser secrets: private Ed25519 key is generated non-exportable in IndexedDB; CSRF is memory-only;
  secure HttpOnly session cookie remains unreadable to JavaScript; logout requests server revocation
  then clears key, cursors, notification choice, service worker, and shell caches locally.
- Notifications: explicit browser permission only; fixed generic title/body; no chat/task content,
  identifier, deep link, or persistent notification payload.
- Listener/execution boundary: web bind remains `127.0.0.1`; service worker has an exact shell-path
  allowlist; offline UI never queues chat or effects; remote voice remains disabled.

## Blockers

- None for safe local Phase 8A-8C implementation. Real phone, TLS, private-network deployment, and
  non-loopback exposure require later Phase 8D authority and are not attempted.

## Known limits and deferred scope

- Passkey/OIDC step-up remains optional future hardening; current browser bootstrap uses the enrolled
  device signature and a five-minute recent-auth window for low-risk approval only.
- Persistent push notifications and remote voice are not part of Phase 8C.
- Process restart intentionally drops private event deltas and idempotency results; client creates a
  fresh session/subscription and refreshes durable status instead of recovering cached content.
- Offline logout erases all browser-held state immediately; server cookie/session can only be
  revoked after connectivity returns and otherwise expires within its 15-minute TTL.
- TLS/private topology, firewall/Tailscale deployment, real phone enrollment/revocation and scan:
  Phase 8D.

## Recovery and rollback

- Keep `JARVIS_WEB_HOST=127.0.0.1` and `JARVIS_TRUSTED_BROWSER_ORIGINS=[]` to disable browser
  bootstrap. Revoke a device to invalidate all API/browser sessions. In the PWA, **Logout and erase
  this device** removes the browser key, cursor, notification choice, service worker, and cache even
  while offline. Restarting JARVIS clears every process-local event/idempotency buffer. Existing
  migration 010 is additive; rollback disables routes/configuration rather than deleting durable
  identity data.

## Final handoff

- Final status: Phase 8A-8C complete; Phase 8 overall remains in progress.
- Files changed: PWA shell/service worker, bounded event hub, remote scope/context contracts,
  authenticated product routes, diagnostics/package data, tests, benchmark, ADR, and
  API/recovery/security/architecture/setup/status documentation.
- Next recommended phase: Phase 8D private-network/TLS deployment and real-phone enrollment,
  install, reconnect, revocation, loss, and security-scan validation.
- Phase 8C implementation commit is recorded in Git history and the final handoff; Phase 8B
  baseline `bbbc9ce` was synchronized with `origin/main` before this implementation.
