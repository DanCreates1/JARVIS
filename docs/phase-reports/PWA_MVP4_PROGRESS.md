# PWA MVP 4 — accessibility fixes

- Status: `in-progress`; M4A local accessibility implementation verified, physical/release gates open.
- Audit baseline: `ed4ee18`, shell v6; work started at `1f07d4c` after concurrent M3C evidence commit.
- Active subphase: M4A — reconnect readiness, text reflow, contrast and chat accessibility.
- Scope: synthetic browser/client checks; no live enrollment, revocation, Garmin reads or route changes.
- Preserve unrelated native package edits and concurrent `PWA_MVP3_PROGRESS.md` work.
- M3C physical-phone acceptance remains separate. MVP 4 is not complete.

## Acceptance

- [x] Authenticated transport readiness and one stream owner through synthetic offline/recovery/restart.
- [x] Desktop enlarged text, long identifiers, text spacing and 320–430 CSS px reflow.
- [x] Measured enabled text/boundary/focus contrast and 44px product touch targets.
- [x] Named keyboard-focusable chat history; retain earlier reading position and selection.
- [x] Deliberate completed/failed reply status; persistent recovery guidance. Spoken acceptance open.
- [x] Focused synthetic tests and Core repository gate; unrelated native audit hold isolated below.
- [ ] Physical Safari/Home Screen VoiceOver, larger text, zoom, external keyboard and touch.
- [ ] Chat cancel/retry/history/restart soak and measured performance thresholds.

## Evidence

2026-10-09 changes, shell `v7`:

- F1: network availability cannot enable protected controls. First successful authenticated poll
  establishes readiness. One generation-bound owner resumes offline/stalled polling, retries with
  bounded backoff and resubscribes on Core 404/409. Queued Web Locks cancel on logout/replacement.
  Session rejection clears volatile credentials/private views; enrolled key survives for renewal.
- F2/F3/F10: user-relative root font and inherited button fonts; wrapping headings/actions/device
  identifiers; adaptive metrics; visible focus; 44px minimum button dimensions. Logout text computes
  **5.7947:1**; enrollment boundary **4.9248:1** against input fill and **4.6004:1** against panel
  RGB. Focus outline exceeds 3:1 against tested fill/button colors. Panel alpha does not bring the
  measured input boundary below 3:1 over either dark background endpoint.
- F4/F5: named, explicitly focusable history; no forced scroll while reading earlier text or
  selecting history; append deltas retain a selection inside the active reply's text node. Named
  Jump to latest returns focus to history. Deltas do not trigger repeated
  speech; a polite completed answer status is deduplicated across HTTP/SSE completion. Failed and
  cancelled events have deliberate status. Steady keepalives do not rewrite live connection
  status. Real screen-reader speech remains unverified.
- F6: local five-minute freshness timer and resume evaluation; last-checked context stays visible
  during refresh/error. Logout clears timers/snapshot. Freshness evaluation alone makes no reads.
- F7/F8/F9: durable ticket-associated error/recovery and local/remote logout result; logout focuses
  ticket after local cleanup. Busy controls/regions and whole-connect failure handling. Headers
  and bodies are bounded: bootstrap/revocation 5s, normal/enrollment 10s, event poll 30s, Garmin 95s
  (Core child deadline 90s). No automatic login, enrollment, scope expansion or chat retry.
- Failed-send draft remains in page memory. An unconfirmed POST does not suppress a later
  authoritative streamed answer. A confirmed reply clears only its unchanged submitted draft;
  newer user edits survive. F11 cancel/retry/history controls remain separate work.

Verification:

- `rtk proxy node --test tests/pwa/garmin-lifecycle.test.cjs`: 43/43 pass. Covers success/rejected/
  stalled offline polls, repeated online events, deadlines, 401/403, Core subscription restart,
  queued/cancelled ownership, partial connection failures, stale-result guards, chat completion/
  lost acknowledgement, retained reading/draft state, freshness and logout result/focus.
- `rtk proxy node scripts/pwa-accessibility-check.cjs`: 24/24 geometry cases pass in Windows Edge
  154.0.4258.62. Widths 320/375/390/430/844/1280 CSS px, browser default font 16/32px, with/without
  WCAG text-spacing overrides. No measured section/page overflow; buttons inherit enlarged font
  and meet 44px targets within 0.01px geometry tolerance. Named Conversation log, Tab/Shift+Tab,
  Page Down scrolling, selection/history retention, Jump focus, logout focus and reduced motion pass.
- Browser default-font resize is desktop evidence. 320px viewport at a 1280px reference is a reflow
  simulation; actual browser 400% zoom, Safari text zoom and iOS larger text remain physical checks.
- Full `rtk uv run pytest --basetemp runtime/mvp4-fixes/pytest-20261009a`: **1439 passed, 3 skipped**,
  **85.59% coverage**; existing Starlette/httpx deprecation warning. Final focused PWA tests pass.
- Lock check/sync, Ruff format/lint, mypy, root pip-audit, Garmin sidecar pip-audit via
  `--path garmin_sync/.venv/Lib/site-packages`, Gitleaks history and diff checks pass. Attempted
  transient sidecar auditor installation hit workstation cache hardlink/copy permissions; auditing
  its installed site-packages with the locked root auditor succeeds without sidecar edits.
- Existing synthetic Phase 8C transport benchmark passes 100 reconnects/10,000 events with no
  duplicates/gaps/cross-session deliveries/offline effects or retained private state. Its existing
  limits remain p95 <25ms, RSS growth <50MiB and shell <256,000 bytes. Measured p95 was
  0.1406ms and RSS growth 0.660MiB; shell remains below 47,000 bytes. This is a transport regression
  check, not phone startup/navigation/first-delta/memory acceptance.
- `rtk proxy npm run verify` in `mobile/`: formatting/lint/types, 38 Jest tests, Expo Doctor 21/21
  and 1,109 dependency license records pass. Existing production audit fails: **15 moderate,
  45 high, 0 critical**. Exports were not reached. Native packages remain under the existing audit
  hold, unchanged and excluded from PWA publication; no force upgrades or audit weakening.

All generated JSON, screenshots, browser profiles and pytest work directories stay under ignored
`runtime/mvp4-fixes/`. Browser script serves synthetic static files on an isolated loopback port;
test-only hooks are appended by that server, absent from production assets. No Core/real identity,
Garmin account, production route, enrollment, live revocation or private health data was used.
`PWA_MVP3_PROGRESS.md` remains untouched at its concurrent `1f07d4c` checkpoint. Native candidate
SHA256 remains `a9bb3741e6b3066deb4adf8091189e35a6837d57be3ba48460e056d75b7d8342` for package.json
and `d0da737979bc3f2ba193939f7d16a6889d934173bfe9a0f8180a4286c1433cf9` for package-lock.json.

Publication includes only PWA source/tests/harness and MVP 4 architecture/setup/progress docs.
Staged Gitleaks finds no leaks. Mobile package candidates, concurrent MVP 3 report and all runtime
artifacts are excluded. Standing commit/push authority applies. Implementation commit `e091930`
was pushed to `main`; [CI run 38013362174](https://github.com/DanCreates1/JARVIS/actions/runs/38013362174)
passed Windows quality (lock/sync, formatting/lint/types, full tests and both Python audits) and
secret scan. Final follow-up preserves text selection inside actively streaming replies and adds
its real-browser regression; 43 lifecycle tests and all 24 desktop cases pass after that change.

Official implementation references checked 2026-10-09: [network availability](https://developer.mozilla.org/en-US/docs/Web/API/Window/online_event),
[queued/abortable Web Locks](https://developer.mozilla.org/en-US/docs/Web/API/LockManager/request),
[scroll-container keyboard access](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/overflow),
[text resize](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html),
[reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html),
[text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html),
[control contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html),
[status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html).

## Remaining gates and handoff

M4A local fixes are reviewable; **MVP 4 is not complete**. Physical Safari/Home Screen VoiceOver,
largest text, actual 400% zoom, landscape/safe areas/software keyboard, touch exploration and focus
during disabled-control transitions still need device evidence. F7/F9 recovery usability requires
slow-reading/spoken checks. F11 needs protocol-aware cancellation/retry and Core-backed history,
including uncertain commit outcome/session guards, before its phone soak. Record explicit phone
performance thresholds before measurements and milestone closure. M3C health-scoped phone
enrollment/revocation/Garmin recovery acceptance stays in its separate report and authority scope.

Estimated active PWA completion: **88%**; accepted phone chat/protected Core Garmin plus verified
M4A local accessibility fixes. Health-scoped physical acceptance, spoken/phone accessibility,
chat cancel/retry/history and performance/release gates remain open. Estimate is milestone-based,
not a measured test percentage.
