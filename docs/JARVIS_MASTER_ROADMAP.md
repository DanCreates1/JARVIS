# JARVIS Master Roadmap

Status: active, mobile-MVP-first  
Updated: 2026-10-16
Repository: `DanCreates1/JARVIS`, branch `main`

## Product target

Finish a small iPhone client using the existing Home Screen PWA before expanding JARVIS further.
The client has three primary surfaces: **Chat**, **Garmin**, and **Settings**.

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
| Agentic expansion A–I — context through email | G published; E/H/K baselines complete; IA local email read/prepare complete, aggregate I `blocked-external` pending IB provider/credential/private-read authority; Phase C Wikimedia `authentication_required` unchanged | [Phase I progress](phase-reports/PHASE_I_PROGRESS.md) |
| Phase 9 — server migration | Repository implementation complete; live deployment blocked on an authorized server | [Progress report](phase-reports/PHASE_9_PROGRESS.md) |
| Phase 10 — generic wearables | 10A boundary complete; former vendor work was deferred | [Progress report](phase-reports/PHASE_10_PROGRESS.md) |
| Phase 11 — advanced/proactive foundation | Complete, default-off, with no autonomous effect authority | [Completion report](phase-reports/PHASE_11_COMPLETION.md) |
| Native mobile M1 | Expo foundation, quality gate, and physical Expo Go smoke complete | [M1 report](phase-reports/MOBILE_M1_PROGRESS.md) |
| Native mobile M2 | Authentication, pairing, session lifecycle, and recoverable key rotation implemented; live enrollment/status/network/revoke/lost-phone checks, Expo Go rotation, and post-expiry recovery passed; native acceptance pending | [M2 report](phase-reports/MOBILE_M2_PROGRESS.md) |

Existing Core already provides versioned remote identity/session contracts, scoped authenticated
client APIs, SSE event transport, conversation persistence, model routing, memory, and audit. The
native app currently provides pairing, signed status, logout, credential erase, and key rotation;
it does not yet provide production chat or Garmin screens.

## Active execution path

The active $0 phone goal is the existing Home Screen PWA with JARVIS chat and a read-only Garmin
panel. See [PWA Garmin](PWA_GARMIN.md). Native M2C build acceptance remains open and deferred:
the owner has no Mac or paid Apple Developer membership. The native MVP sections below are retained
as historical plans, not prerequisites for the PWA goal.

The owner's standalone Garmin connector is organized locally and its saved-session batch report
passed a live read on 2026-10-05. See [connector and report evidence](GARMIN_CONNECTOR.md).
That standalone report did not establish a protected Core session or physical-iPhone Garmin
acceptance. M3A verifies saved-session compatibility, offline import, subprocess isolation,
rotation/error recovery and logout-safe PWA rendering. M3B passed on 2026-10-08: protected offline
import and one flags-only live Core check succeeded, with fresh validated data and all six category
availability flags true. Core now owns the protected session. Requested saved-session reads/renewal
need no repeated permission. M3C health-scoped phone enrollment and physical-device acceptance
remain; see [PWA MVP 3 progress](phase-reports/PWA_MVP3_PROGRESS.md).

M3C continuation adds shell `v6` recovery repairs: immediate local logout erase, bounded remote
cleanup before replacement enrollment, and guards against obsolete bootstrap/status/task/chat/
event responses. Synthetic lifecycle evidence passes; physical-iPhone rows remain unexecuted.
No health-scoped ticket or test revocation was performed while the grouped owner decision is pending.
Both unrelated native package candidates remain preserved and excluded under their audit hold.

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
  initial inspection found the Windows Credential Manager/DPAPI policy. The current isolated
  bridge implements chunked Windows Credential Locker storage, with synthetic import/rollback
  checks. Real protected session and bounded Core acceptance passed on 2026-10-08.

Garmin data is private health data. Credentials, MFA values, tokens, raw responses, locations, and
health data never enter logs, Git, mobile storage, audit payloads, or model-provider requests.
Requested saved-session reads follow the root Codex confirmation policy without additional
permission prompts. New credential login/MFA needs confirmation if not already approved and
interactive entry in a trusted local terminal.

### MVP 4 — Polish and release

Authorized accessibility fixes started 2026-10-09. M4A shell `v7` separates network availability
from authenticated stream readiness, preserves chat reading position, announces completed replies,
reflows enlarged text and improves contrast/targets. Synthetic lifecycle and desktop checks pass;
physical VoiceOver/Safari, full zoom, chat cancel/retry/history and performance acceptance remain.
See [MVP 4 progress](phase-reports/PWA_MVP4_PROGRESS.md). M3C phone Garmin acceptance remains
separate; native package candidates stay unchanged under their dependency-audit hold.

2026-10-10 M4A continuation at `5384121`: owner reports phone available later. Physical
accessibility remains `blocked-external`; [M4A acceptance](PWA_M4A_ACCESSIBILITY_ACCEPTANCE.md)
records separate Safari/Home Screen rows and a separate actual desktop 400% browser-zoom gate.
Preparation does not close either physical acceptance or MVP 4. No application assets changed.

2026-10-12 M4A resumption at `2cb1f96`, shell `v7`: owner confirmed phone available now.
Physical acceptance is `in-progress`; metadata, loaded phone version and separate Safari/Home
Screen observations remain pending. No phone row is accepted from availability or desktop evidence.
Existing loopback Core resumed without route changes. Separate actual desktop 400% browser zoom
passes on the bounded synthetic Edge shell; phone speech/text/zoom checks remain open.

2026-10-13 M4A continuation: bounded Safari A1 names/headings/order/unavailable-state observation
passed; phone script/worker verification and Home Screen acceptance remain open. Owner stopped
remaining phone checks during larger-text preparation; no further phone questions queued.
Unexecuted checks remain unverified, A10 blocked without keyboard. This deferral does not complete
M4A or MVP 4. Later chat cancel/retry/Core-backed history and performance work remain planned;
none started in this M4A session. Native package edits and MVP 3 report remain preserved.

Owner subsequently resumed phone checks on 2026-10-13, requesting compact batches. Safari largest
accessibility-text growth and rotation/empty-ticket keyboard layout passed; 200% website zoom
component passed. Subsequent Home Screen names/readiness/streaming/selection/Jump focus, largest
text, rotation/Message keyboard, pinch/iOS magnification and safe touch/Reduce Motion passed.
Safari highest offered website zoom, pinch/iOS magnification and safe shell touch/Reduce Motion
also worked; maximum website percentage remains unreported. Usual settings restoration was part
of the final batch reported all worked. Full phone assets, Safari authenticated checks, error/
failure cases and external-keyboard acceptance remain open. No blanket physical pass or
M4A/MVP 4 closure; M3C remains separate.

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

2026-10-16 continuation at `473347e`: owner reports Home Screen **Connected; fixed the problem**
and general **yes all good** to bundled status/Send/new-control checks. Exact original-request
outcome and individual controls remain unitemized; no physical retry gate accepted. Current
private host/v8 assets remain verified. Core metadata finds 4 active chat-only browser enrollments
and 10 completed host receipts; aggregate counts cannot identify the original request or prove
phone continuity. Owner reports both idle reopenings and three-history-control VoiceOver batch
pass, with same saved conversation and no duplicate answer; no unresolved indicator reported.
Final VoiceOver reconnect/readiness-ordering/focus batch subsequently owner-reported passing;
conditional-control presence/absence remains unitemized. Explicit online reload/full phone
assets and exact original terminal status unverified separately. F11-P0 remains partial; P1
observed batches pass with conditional-availability limitation. Held mobile edits preserved,
M3C separate.

2026-10-16 continuation at `5a5bed2`: owner reports **Enrollment completed** after the supplied
chat-only ticket command. Current read-only host checks pass online Tailscale, exact existing
private route, one loopback Core listener, matching v8 assets and unauthenticated **401** responses.
Core metadata now shows **3 active unexpired browser enrollments**, all exact seven chat scopes,
no health scope; repaired schema intact, zero running host receipts. Current phone connection,
Send/Retry/draft state, exact enrolled surface and original-request identity continuity remain
unconfirmed. No new Send/Retry requested before these observations; no history transfer inferred.
F11-P0/P1 remain open; held mobile edits unchanged and M3C separate.

2026-10-16 continuation at `5ef5c36`: owner reports **Connect existing device → Connection
failed**. Host checks find Tailscale **NoState**, offline, empty Serve configuration and stopped
Core. Starting the existing Tailscale app restores its saved profile and exact prior private route;
reviewed local Core launcher restores one loopback listener. No login, enrollment, profile switch
or route edits. All four private/loopback v8 assets match source; repaired schema and both chat-only
browser enrollments remain present. Original-request Retry, Send state, exact phone surface,
two reopenings and VoiceOver remain pending. Held mobile edits and M3C stay separate.

2026-10-15: initiated [F11 physical acceptance](PWA_F11_PHYSICAL_ACCEPTANCE.md) at `4fa75e3`,
shell **v8**, with compact owner batches and phone performance budgets frozen before samples.
Fresh 63 lifecycle/24 desktop cases and existing private-route readiness pass. Full physical rows
remain pending. M3C grouped decision, remaining M4A cases and phone
performance stay open. Held native dependency files remain unchanged and excluded from publication.
The full local gate found an immediate-cancellation settlement race; fixed with a delayed-storage
regression, cancellation-safe audit rollback and 34 focused storage/Core/API/transport passes.
Final local release gate passes **1,459 tests / 3 optional skips**, **85.65% coverage**, with
format/lint/types, root/sidecar audits and secret scans clear. On the owner's phone-ready return,
Core was already stopped; patched Core was started on the verified existing private route.
Initial trusted read-only Core metadata confirmed one active browser with exactly the prior seven
scopes and no health scope; corrected the circular pre-Connect wording check for fresh startup.
Continuation at `22d50db` records owner-reported **Connected**, **Send enabled** and one public
request/reply. Fresh aggregate metadata finds two active browsers, both chat-only, no health scope
and risk ceiling at most 1. No ticket/identity details retained or enrollment mutation performed
in this continuation. Phone metadata/current runtime, retained-key continuity and full F11 rows
remain pending; M3C stays separate. Source publication `a0b60fb` CI passed.
Continuation at `55be543` records iPhone 15 Pro/iOS 27.0.1, Wi-Fi, portrait, normal text/zoom,
VoiceOver off and no external keyboard; exact surface remains unresolved. Owner reports Send
blocked by an unconfirmed outcome, with Core finding no accepted request. Live schema lacks
sequence columns and deletion safeguard from early applied migration 017; synthetic reproduction
confirms insertion failure. Transactional startup repair and named insert columns pass 26 focused
Core/API checks. Full release and actual phone recovery evidence are tracked in MVP 4 progress;
P0/P1 reopen/VoiceOver acceptance stays open. Held native files and M3C remain separate.

2026-10-14: owner authorized F11 implementation despite pending physical M3C/M4A gates. Shell
**v8** adds working Core cancellation, immutable-ID safe retry, device-owned durable history and
reconnect/session isolation. See [F11 contract](PWA_F11_CHAT.md) and
[verified execution](phase-reports/PWA_MVP4_PROGRESS.md). Physical v8 soak, new-control accessibility
and measured phone performance remain open. Native SDK patch mismatches were repaired locally;
38 tests, Doctor 21/21 and both exports pass, but production audit remains 60 findings with
unpatched upstream advisories. Native candidates retain their publication hold. Estimated PWA
completion **92%**, based on implemented/automated milestones, not physical acceptance percentage.

**MVP 3 / M3C — health-scoped phone acceptance.** M3A/M3B are complete: protected import and
fresh live Core Garmin evidence passed. Do not repeat source discovery/import. M3C needs a
pending grouped health-scope enrollment/recovery decision and physical-phone evidence; reload current shell `v8` before new acceptance.
Local recovery repairs and their synthetic evidence do not close the physical gate. Important new enrollment, login/MFA, credential changes,
signing, paid services and deployment need confirmation only when not already explicitly approved.
Native M2C remains deferred.
