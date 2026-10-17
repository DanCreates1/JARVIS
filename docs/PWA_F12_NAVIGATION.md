# F12 — Chat / Garmin / Settings navigation

Status: **planned; next development**, queued by owner reprioritization on 2026-10-16.
Baseline application: F11 shell v8; development plan has no application implementation yet.

## Problem and result

The current PWA places enrollment, chat, Garmin, tasks and device controls on one long page.
The existing roadmap calls for three primary surfaces. Build persistent Chat / Garmin / Settings
navigation so daily conversation is immediately accessible and connection/device controls have
a dedicated home.

## Bounded scope

- Chat: existing conversation selector/history, composer, streaming, cancel/retry and task status.
- Garmin: existing read-only summary, freshness/error states and approved manual refresh behavior.
- Settings: existing enrollment/connect, device status and logout controls; visible connection
  state remains available across surfaces.
- Accessible navigation, selection/focus state, browser back/forward behavior and narrow/wide
  layouts. Retain one client session, stream owner, pending request and conversation across views.
- Prefer current dependency-free HTML/CSS/JavaScript. No new dependencies or framework required.

## Boundaries and verification

Navigation grants no authority and must not create a session, enrollment, chat submission,
notification permission, health request or logout effect merely by selecting a surface. Preserve
existing scope checks, explicit actions, no transcript/draft persistence, API-cache exclusion,
session isolation and logout clearing. Persist at most a non-sensitive view selection if needed.
No credential, route, health-scope, deployment or native package changes are included.

Inspect actual state and applicable repository instructions before implementing. Extend existing
real-script lifecycle checks for navigation during streaming/retry, obsolete responses, logout,
offline transitions and focus/back navigation. Run appropriate automated desktop layout and
repository quality/security gates; preserve evidence. Update public shell/worker versions together
when assets change, using existing cache lifecycle.

Manual phone checks are **skipped by owner; unverified** and cannot block development or generate
phone-check questions. Do not claim physical acceptance from automated evidence. M3C access
decisions and held native package candidates remain separate.

## Exit and handoff

All three surfaces work through existing Core contracts, navigation preserves in-flight ownership,
automated regressions/security checks pass and documentation matches behavior. Publish safe source
under standing authorization. Stop at F12's boundary; no unrelated feature expansion.
