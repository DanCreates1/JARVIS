# F12 — Chat / Garmin / Settings navigation

Status: **complete — bounded implementation and automated verification**, 2026-10-16.
Baseline: `0d77f8c`, F11 shell v8. Result: dependency-free shell **v9**.
Evidence: [F12 completion](phase-reports/PWA_F12_COMPLETION.md). Physical/MVP acceptance is not claimed.

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

## Implemented behavior

Chat opens by default. Persistent links select `#/chat`, `#/garmin` or `#/settings`; browser
back/forward restores the selected surface. Invalid fragments become Chat. Only the public view
fragment persists in browser history, whose state is null. No draft/transcript/health data or
request identifiers enter navigation storage. Reload keeps a valid view selection and retains
the existing explicit connection flow.

Inactive containers use `hidden`; one link carries `aria-current="page"`. Deliberate selection
and back/forward focus the visible heading; startup does not move focus. Navigation wraps with
enlarged text and scrolls normally in short viewports. Connection status remains shared.

The same DOM/session/stream/request/conversation continues across views. Hidden replies retain
reading position or follow-latest intent. Selecting Garmin performs no fetch; the existing scoped
connection bootstrap and explicit Refresh Garmin behavior remain. Logout exposes Settings,
clears private state in every view and avoids moving focus to a hidden ticket if the user navigated
away during cleanup. Back/forward cannot restore cleared private content.

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

Exit evidence: **73 lifecycle tests**, **72 desktop layout cases**, six short-viewport focus cases,
actual browser history/keyboard/accessibility checks, **1,464 passed / 3 optional skips** at
**85.67%** coverage, and unchanged security/audit/transport gates. Manual phone checks remain
**skipped by owner; unverified**. No further phase queued; M3C and native audit holds remain separate.
