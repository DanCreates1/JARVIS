# ADR 0003: Phase 8C PWA and resumable private transport

Status: accepted  
Date: 2026-09-10

## Context

Phase 8A-8B provide device proof, durable browser sessions, exact Origin/CSRF/CORS/CSP checks, and
low-risk approval rules. Phase 8C needs an installable client and reconnect behavior without
opening a listener, caching private data, creating an offline effect queue, or coupling the client
to a future Phase 8D network topology.

## Decision

- Serve a dependency-free same-origin PWA at `/app/`; package all assets with the Python wheel.
- Cache only the five fixed shell assets. Never intercept or cache `/api/*`.
- Generate Ed25519 through Web Crypto with `extractable=false`. Persist the non-exportable private
  `CryptoKey` in dedicated IndexedDB; export only the public key for Phase 8A enrollment.
- Keep the one-time CSRF value only in page memory. Keep payload-free cursor/subscription state in
  per-tab `sessionStorage`. Do not use browser local storage.
- Add separate chat/task/status scopes. `events.read` alone cannot subscribe to a product topic.
- Use finite SSE pages over a bounded session-owned process-memory buffer. Events have monotonically
  increasing cursors; stale/gapped cursors require refresh and resubscription.
- Bind request retry records and subscriptions to exact host/device/browser-session identity. Clear
  them at logout and no later than session expiry.
- Use generic opt-in non-persistent notifications. Do not include message/task content or links.
- Ship no remote voice upload, push service, action/task execution, remote approval, or offline
  mutation queue.

## Security and failure properties

- Browser cookie, CSRF, scope, Origin, rate, and body controls remain Phase 8B-owned middleware.
- Cross-session subscription access returns the same unavailable result as a missing subscription.
- Buffers cap at 256 events and 256 KiB/subscription, four subscriptions/session, 64
  subscriptions/process, 64 KiB/event, 128 cached request results of 128 KiB each, and one-hour
  maximum retention bounded further by session expiry.
- Process restart deliberately discards private event buffers. Durable conversation/task state is
  canonical; the client creates a clean subscription instead of guessing missing frames.
- Offline UI disables mutation and queues nothing. Online logout revokes server state and returns
  `Clear-Site-Data`; the client also erases key, cursors, notification state, caches, and worker.
- Offline local erase cannot revoke an unreachable server or directly delete an HttpOnly cookie.
  The session expires within 15 minutes; local device revocation remains lost-phone recovery.

## Alternatives rejected

- Durable database storage for chat deltas: unnecessary private-content retention.
- Shared WebSocket broadcaster: harder restart/backpressure/ownership behavior without benefit for
  one local Phase 8D replica.
- Background Sync/offline outbox: could replay stale actions after context or authority changes.
- Browser local storage for key/token/CSRF: exportable/script-readable long-lived secret storage.
- Content-rich notifications: lock-screen disclosure.
- Third-party PWA framework/CDN: avoidable supply-chain and offline-version surface.

## Standards checked

- [W3C Web Cryptography Level 2](https://www.w3.org/TR/webcrypto-2/) defines Ed25519 signing and
  generated public-key extractability while the private key follows `extractable=false`.
- [W3C Service Workers](https://www.w3.org/TR/service-workers/) requires secure contexts and defines
  origin-isolated script-controlled Cache Storage.
- [WHATWG Notifications](https://notifications.spec.whatwg.org/) defines explicit permission and
  non-persistent notification behavior.

## Consequences

Phase 8C can be fully tested on loopback/synthetic HTTPS without authorizing network exposure.
Phase 8D must provide reviewed TLS/private networking, firewall/Tailscale policy, a real phone,
external listener scan, revocation proof, and deployment rollback before Phase 8 completes.
