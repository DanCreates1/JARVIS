# JARVIS Native Mobile Milestones

Status: superseded by the $0 phone PWA path in [PWA_GARMIN.md](PWA_GARMIN.md); native M2C
acceptance remains deferred, not passed. The milestones below remain historical planning context.
Updated: 2026-09-30

## Definition of done

**Mobile MVP complete** means an enrolled iPhone can securely send text to JARVIS, stream an
answer, view basic read-only Garmin data, recover from ordinary connection failures, and
disconnect cleanly.

Execution uses only the four milestones below. Existing M1/M2 reports remain historical evidence;
former M3–M9 and H1–H8 plans are not prerequisites.

## MVP 1 — Design and connection

**Objective**

Finish M2C live iPhone/Core connection and deliver a simple accessible shell with **Chat**,
**Garmin**, and **Settings** as the only primary surfaces.

**Deliverables**

- Complete the existing M2C private Tailscale HTTPS enrollment, signed-session, revocation,
  rotation, logout, restart, and lost-phone matrix.
- Small design system: color/type/spacing tokens, accessible controls, cards, forms, banners, empty
  states, and error presentation.
- Persistent three-surface navigation. Settings owns connection state, server identity summary,
  logout, disconnect, credential erase, and key rotation.
- Explicit loading, connected, offline, reconnecting, expired-session, permission-denied, and
  recoverable/unrecoverable error states.
- No unnecessary animation, nested navigation, telemetry, background permission, or new authority.

**Acceptance checks**

- Physical iPhone pairs to the exact enrolled HTTPS origin and can request signed Core status.
- Wi-Fi/cellular change, Tailscale off/on, Core restart, session expiry, logout/recreation,
  revocation, rotation, and local erase behave as specified in
  [M2C acceptance](MOBILE_M2C_ACCEPTANCE.md).
- All three surfaces are reachable in at most one primary navigation action; VoiceOver names every
  interactive control; Dynamic Type does not hide required controls.
- Offline and expired-session states never look connected and never queue privileged work.
- Mobile verification, relevant Core security tests, dependency audit, secret scan, and diff check
  pass.

**Security/privacy boundary**

Core remains loopback-bound behind tailnet-only HTTPS. Enrollment tickets never enter routes,
logs, screenshots, chat, or Git. Device seed stays in SecureStore; bearer session stays in memory.
Mobile cannot mint scopes or approvals.

**Owner-action blocker**

Owner must approve each fresh five-minute enrollment ticket and perform physical-iPhone steps.
Development build/signing needs separate approval, bundle identifier, Apple account, signing path,
and cost decision.

## MVP 2 — Chat

**Objective**

Provide dependable text conversation through the existing authenticated Core API while keeping
Core the only conversation, memory, routing, policy, and audit authority.

**Deliverables**

- Text composer with send, disabled/working states, keyboard-safe layout, and message list.
- Streamed assistant output through signed `/api/v1` requests and Core-owned SSE events.
- Core-backed conversation history across app restart; no second authoritative mobile history.
- Cancel active generation and retry a failed user message without duplicate conversation effects.
- Connection indicator plus actionable offline, timeout, auth-expired, revoked, rate-limited,
  server, and stream-interrupted errors.
- Required Core contract additions for native history/cancel remain versioned, scoped, bounded,
  audited, and compatible with the PWA.

**Acceptance checks**

- On a physical iPhone, 20 representative text turns preserve order and stream visible deltas; one
  conversation resumes after app and Core restart.
- Cancel stops visible generation and server work within a measured bound; retry is idempotent and
  produces no duplicate user turn.
- Stream interruption, session expiry, Core restart, and network loss recover without mixing
  conversations or another device's events.
- History pagination is bounded; empty/loading/error states are accessible; secrets and auth data
  never appear in UI diagnostics or logs.
- Contract, integration, replay, authorization, mobile UI, and reconnect tests pass.

**Security/privacy boundary**

Mobile sends user text only to the enrolled Core origin. It holds no provider credential, provider
SDK, model ID policy, memory authority, tool authority, or durable bearer token. Core applies its
existing privacy routing, model selection, permissions, audit, and retention rules.

**Owner-action blocker**

Owner must make the enrolled iPhone and private network available for final live acceptance. Any
test that sends private prompts or invokes a paid/configured provider requires separate explicit
authorization; public synthetic prompts remain default.

## MVP 3 — Garmin

**Objective**

Expose a small read-only Garmin summary through a provider-neutral Core adapter using
[`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect).

**Deliverables**

- Core-owned `HealthDataProvider`-style port, `python-garminconnect` adapter, normalized schemas,
  fake adapter, and dependency-removal test. Do not couple mobile or Core domain models to Garmin
  response shapes.
- Read only: daily steps; heart rate/resting heart rate; sleep; stress/Body Battery when available;
  recent activities.
- Garmin screen with per-section unavailable states, manual refresh, last successful sync time,
  stale marker, and disconnect/delete control.
- Interactive local login/MFA only. Garmin password and MFA value are not retained. Access and
  refresh tokens use a Core-owned protected local-secret facility, never mobile storage or the
  library's default token path. Current code inspection found security policy for Windows
  Credential Manager/DPAPI but no Garmin-ready implementation; identify and verify the facility
  before accepting a token.
- Timeouts, bounded retries with jitter, local rate limits, single-flight refresh, schema/size
  validation, token expiry/re-authentication, revocation/disconnect, deletion, and content-free
  sanitized audit records.
- Resolve upstream Python `>=3.12` versus JARVIS Python `>=3.11,<3.13` through a reviewed runtime
  decision before adding the dependency.
- Pin and audit a current version. Document that the MIT-licensed library is unofficial, uses
  Garmin web services, includes mutation APIs that JARVIS must not expose, and may break when
  Garmin changes private APIs.

**Acceptance checks**

- Mocked adapter tests cover complete, partial, absent, malformed, oversized, slow, rate-limited,
  auth-expired, and changed-upstream responses without network or real credentials.
- Core API returns only normalized read models and never exposes password, MFA, tokens, raw Garmin
  response, precise activity location, or library exception bodies.
- Manual refresh is rate-limited and deduplicated; last-sync advances only after validated success;
  stale cached data is visibly labeled.
- Disconnect removes Core tokens and cached Garmin data, blocks later reads, and produces only a
  sanitized audit reason. Account-side revocation limitations are explained.
- Dependency audit covers the pinned version; versions affected by known token-storage advisories
  are rejected.
- Optional live test reads only the five approved categories and records sanitized pass/fail, not
  health values.

**Security/privacy boundary**

Garmin data is private health data. It remains in Core's protected local boundary and is never
committed, logged, exported, placed in mobile durable storage, or sent to model providers. No
workout upload/scheduling/edit/delete, weigh-in, hydration, menstrual, nutrition, activity edit,
device mutation, or other Garmin write is reachable in MVP.

**Owner-action blocker**

Live account testing requires explicit owner authorization for that session plus interactive
credential and MFA entry in a trusted local prompt. No account creation, credential collection in
chat, or noninteractive environment-variable password.

## MVP 4 — Polish and release

**Objective**

Make the three-surface MVP reliable and accessible on a physical iPhone, then prepare an optional
development build without implying App Store release.

**Deliverables**

- Final visual consistency, accessible focus/order/labels, Dynamic Type, contrast, reduced motion,
  keyboard behavior, safe areas, and common iPhone sizes.
- Chat reconnect/restart/cancel/retry soak and basic startup, navigation, first-delta, and memory
  measurements.
- Garmin offline, expired-token, MFA, disconnect/delete, rate-limit, malformed-response, and API-
  change failure tests.
- Recovery notes for lost phone, revoked device, changed Core origin, failed key rotation, Garmin
  token exposure, and upstream breakage.
- Reproducible development-build checklist. App Store packaging, review, analytics, monetization,
  and release remain separate optional work.

**Acceptance checks**

- The complete mobile-MVP definition passes on a physical iPhone over Wi-Fi and cellular through
  the approved private HTTPS path.
- Three repeated app restarts and three Core/network interruptions recover without credential,
  conversation, event, or health-data crossover.
- No critical accessibility failure; measured performance is recorded with explicit thresholds
  before closure; mobile and repository release gates pass.
- Secret scan and artifact review find no credential, token, private Garmin data, screenshot,
  native build, signing material, or runtime database in Git.
- Disconnect cleanly revokes the JARVIS session/device as selected, clears local identity, removes
  Garmin access/data when selected, and leaves understandable recovery instructions.

**Security/privacy boundary**

Polish cannot weaken authentication, private-network routing, least privilege, privacy routing,
Garmin read-only enforcement, audit sanitization, or deletion. Signing secrets and device records
stay outside Git and chat.

**Owner-action blocker**

Owner must authorize development build/signing and choose the Apple account, bundle identifier,
registered device path, and any cost. App Store release requires a later, separate request.

## Deferred backlog

Voice, photos/files, push notifications, widgets, proactive features, phone sensors/context,
health analytics, wearable writes, direct watch communication, and the former broad M3–M9 and
H1–H8 work. None blocks mobile MVP.
