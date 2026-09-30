# JARVIS Master Roadmap

Status: active, mobile-MVP-first  
Updated: 2026-09-28  
Repository: `DanCreates1/JARVIS`, branch `main`

## Product target

Finish a small native iPhone client before expanding JARVIS further. The client has three primary
surfaces: **Chat**, **Garmin**, and **Settings**.

**Mobile MVP complete** means an enrolled iPhone can securely send text to JARVIS, stream an
answer, view basic read-only Garmin data, recover from ordinary connection failures, and
disconnect cleanly.

The four milestones are:

1. **MVP 1 — Design and connection:** finish live iPhone/Core acceptance and the accessible app
   shell.
2. **MVP 2 — Chat:** ship text chat, streamed answers, history, cancel, retry, and useful
   connection states.
3. **MVP 3 — Garmin:** add private, read-only health synchronization through JARVIS Core.
4. **MVP 4 — Polish and release:** pass physical-device, recovery, accessibility, and performance
   gates; build or sign only with explicit approval.

Exact milestone deliverables and gates live in [Native Mobile Milestones](MOBILE_PHASES.md).

## Product and security invariants

- JARVIS Core remains the sole authority, memory store, model router, permission boundary, and
  audit system. Mobile is a presentation and device-I/O client.
- Production remote access uses private-network HTTPS plus application authentication. Core stays
  loopback-bound behind the approved gateway. No public unauthenticated listener.
- Device keys are per-device, origin-bound, revocable, and stored in platform secure storage.
  Bearer sessions are short-lived and process-memory-only.
- Mobile receives no model-provider, Garmin, notification-provider, or server credential. It never
  contains model-selection or authorization logic.
- Model output, web content, Garmin responses, and client input are untrusted data. They cannot
  grant permissions or authorize effects.
- Sensitive or uncertain content routes locally. Cloud use remains configuration-driven,
  privacy-gated, and hard-capped at `$0` unless a later explicit decision changes that policy.
- Tools are typed, least-privilege, audited, bounded, and deny-by-default. No arbitrary model-to-
  shell path exists.
- Secrets, runtime databases, logs, recordings, screenshots, health data, model weights, and
  generated builds never enter Git.
- SQLite remains the default durable store. No service split or new database without measured need.

Architecture details remain in [JARVIS Architecture](JARVIS_ARCHITECTURE.md),
[Mobile Architecture](MOBILE_ARCHITECTURE.md), and [Security Model](SECURITY_MODEL.md).

## Current repository state

Historical implementation is preserved. This roadmap summarizes status; phase reports retain the
detailed evidence and must not be rewritten to fit the new product order.

| Track | Current truthful status | Evidence |
| --- | --- | --- |
| Phase 0 — repository baseline | Complete; continuous secret/reproducibility audit remains | [Rebuild plan](PHASE_0_REBUILD_PLAN.md) |
| Phase 1 — privacy-aware text core | Implemented, formally `blocked-external` on NVIDIA latency and local-cold revalidation | [Progress report](phase-reports/PHASE_1_PROGRESS.md) |
| Phase 2 — voice | Complete; continuous wake/clap remains disabled by default | [Completion report](phase-reports/PHASE_2_COMPLETION.md) |
| Phase 3 — controlled computer access | Implemented; authorized live closeout remains pending | [Completion report](phase-reports/PHASE_3_COMPLETION.md) |
| Phases 4–8 — memory, research, tasks, vision, secure PWA | Complete | [Phase reports](phase-reports/) |
| Phase 9 — server migration | Repository implementation complete; live deployment blocked on an authorized server | [Progress report](phase-reports/PHASE_9_PROGRESS.md) |
| Phase 10 — generic wearables | 10A boundary complete; former vendor work was deferred | [Progress report](phase-reports/PHASE_10_PROGRESS.md) |
| Phase 11 — advanced/proactive foundation | Complete, default-off, with no autonomous effect authority | [Completion report](phase-reports/PHASE_11_COMPLETION.md) |
| Native mobile M1 | Expo foundation, quality gate, and physical Expo Go smoke complete | [M1 report](phase-reports/MOBILE_M1_PROGRESS.md) |
| Native mobile M2 | Authentication, pairing, session lifecycle, and recoverable key rotation implemented; live enrollment/status/network/revoke/lost-phone checks passed; rotation, expiry, and native acceptance pending | [M2 report](phase-reports/MOBILE_M2_PROGRESS.md) |

Existing Core already provides versioned remote identity/session contracts, scoped authenticated
client APIs, SSE event transport, conversation persistence, model routing, memory, and audit. The
native app currently provides pairing, signed status, logout, credential erase, and key rotation;
it does not yet provide production chat or Garmin screens.

## Active execution path

### MVP 1 — Design and connection

Close existing M2C live acceptance, then replace the foundation screen with a simple accessible
three-surface shell. Show explicit loading, connected, offline, reconnecting, expired-session, and
error states. Avoid animation and navigation depth that do not support the MVP.

Owner action is required for fresh enrollment tickets, physical-iPhone actions, and any native
development build or signing decision. See [M2C acceptance](MOBILE_M2C_ACCEPTANCE.md).

### MVP 2 — Chat

Use the authenticated `/api/v1` boundary to send text and consume Core-owned streaming events.
Add history, cancel, retry, reconnect, and clear failures. Core alone owns conversation state,
routing, memory, policy, and audit. Do not copy provider SDKs, keys, or model logic into mobile.

### MVP 3 — Garmin

Integrate [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) behind a
provider-neutral Python adapter in Core. Initial data is read-only: daily steps, heart rate/resting
heart rate, sleep, stress/Body Battery when present, and recent activities. Mobile gets validated,
minimal view models plus manual refresh and last-sync time.

Current upstream facts verified 2026-09-28:

- upstream master reports version `0.3.16`, Python `>=3.12`, MIT licensing, active 2026 releases,
  credential/MFA login, locally cached refresh tokens, and more than 150 read/write methods;
- the client is explicitly unofficial and uses Garmin web services, so private endpoint or login
  changes can break it without notice;
- JARVIS currently supports Python `>=3.11,<3.13`; dependency isolation or a reviewed minimum-
  Python change is therefore an implementation gate;
- versions `<=0.3.4` had a high-severity token-file permission advisory, and later 0.3.10–0.3.11
  releases added further token-path, symlink, atomic-write, authentication, URL, logging, and
  request hardening. MVP must use a reviewed current version and a Core-owned protected
  local-secret facility, not expose or directly trust the library's default token file. Current
  inspection found the Windows Credential Manager/DPAPI policy but no Garmin-ready implementation;
  that facility must be identified and verified before any token is accepted.

Garmin data is private health data. Credentials, MFA values, tokens, raw responses, locations, and
health data never enter logs, Git, mobile storage, audit payloads, or model-provider requests.
Live testing requires explicit owner authorization and interactive credential/MFA entry.

### MVP 4 — Polish and release

Run physical-iPhone acceptance; chat reconnect/restart; Garmin offline, token-expiry, MFA,
disconnect, and upstream-change failures; accessibility; and basic performance checks. Development
build and signing require explicit owner approval. App Store work is separate and optional.

## Release gates

Every milestone must pass its focused tests plus relevant repository gates. Before mobile MVP
closure:

- enrollment, signed sessions, revocation, rotation, logout, reconnect, and lost-phone behavior
  fail closed;
- chat streaming, cancellation, retry, history, Core restart, and network transitions pass on a
  physical iPhone;
- Garmin adapter tests use mocks by default; schemas reject malformed or oversized data; timeouts,
  bounded retries, local rate limits, disconnect, token deletion, and sanitized audit pass;
- accessibility labels, Dynamic Type, contrast, focus/order, reduced-motion behavior, and common
  screen sizes pass;
- `uv` lock/sync, format, lint, type, tests, dependency audit, Gitleaks, mobile verification, and
  `git diff --check` pass or any unrelated pre-existing failure is isolated and reported;
- no secret, token, private health data, generated build, or unrelated work enters the commit.

## Deferred backlog

Not required for mobile MVP: voice; photos/files; push notifications; widgets; proactive features;
phone sensors/context; health analytics; wearable writes; direct watch communication; Meta glasses;
smart-home work; custom voice; fine-tuning; larger local models; PostgreSQL/Redis/microservices;
multi-GPU serving; the former broad M3–M9 and H1–H8 mobile/health plans. Reconsider only after the
four MVP milestones pass and the owner explicitly reprioritizes them.

## Next milestone

**MVP 1 — Design and connection.** Resume M2C live iPhone/Core acceptance. Do not start a fresh
ticket, development build, signing, paid service, deployment, or credential flow without its
required owner approval.
