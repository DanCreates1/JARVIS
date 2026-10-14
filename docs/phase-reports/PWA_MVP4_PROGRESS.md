# PWA MVP 4 — accessibility fixes

- Status: `in-progress`; M4A local implementation verified; Safari A1/A7/A9/A11 and Home Screen A1/A3/A4/A5/A7/A8/A9/A11 observed passes; remaining physical/release gates open.
- Audit baseline: `ed4ee18`, shell v6; work started at `1f07d4c` after concurrent M3C evidence commit.
- Active subphase: M4A — reconnect readiness, text reflow, contrast and chat accessibility.
- Scope: synthetic browser/client checks and physical Safari/Home Screen accessibility acceptance
  using existing identity/public text only; no live enrollment, revocation, Garmin reads or route changes.
- Preserve unrelated native package edits and concurrent `PWA_MVP3_PROGRESS.md` work.
- M3C physical-phone acceptance remains separate. MVP 4 is not complete.

2026-10-10 resumption: `main` at `5384121`, shell `v7`; owner reports **phone available later**.
M4A physical acceptance is `blocked-external`; aggregate MVP 4 stays `in-progress`. Preparation:
freeze separate Safari/Home Screen steps and sanitized results in
[M4A acceptance](../PWA_M4A_ACCESSIBILITY_ACCEPTANCE.md), refresh local supporting checks, run
applicable publication gates, preserve native edits and MVP 3 report. No new application change
or physical pass is planned without observed device evidence.

2026-10-12 resumption: `main` at `2cb1f96`, shell `v7`; owner confirmed **phone available now**.
M4A physical acceptance is `in-progress`; owner reports **iPhone 15 Pro, iOS 27.0.1** and a connected
Home Screen app. Preliminary label observations are recorded; settings, phone-loaded version and
complete Safari/Home Screen accessibility acceptance remain pending. Availability closes the phone-unavailable blocker, not an acceptance
row. Use the existing matrix; M3C acceptance stays separate.

## Acceptance

- [x] Authenticated transport readiness and one stream owner through synthetic offline/recovery/restart.
- [x] Desktop enlarged text, long identifiers, text spacing and 320–430 CSS px reflow.
- [x] Measured enabled text/boundary/focus contrast and 44px product touch targets.
- [x] Named keyboard-focusable chat history; retain earlier reading position and selection.
- [x] Deliberate completed/failed reply status; persistent recovery guidance. Spoken acceptance open.
- [x] Focused synthetic tests and Core repository gate; unrelated native audit hold isolated below.
- [x] Separate actual desktop browser 400% zoom gate on the bounded synthetic shell.
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

2026-10-09 verification checkpoint at `e4133b41ba4884d593b5a27f70fab9fa6a6b6398`:

- Local HEAD, tracking `origin/main`, and live upstream `main` match the final M4A implementation.
  [CI run 38013672136](https://github.com/DanCreates1/JARVIS/actions/runs/38013672136) passed
  both Windows quality and secret-scan jobs at that exact SHA, including the full test gate,
  root/sidecar locked setup and dependency audits. This closes the previously unrecorded CI
  result for the streamed-selection follow-up; physical MVP 4 acceptance remains open.
- Fresh local reruns pass all **43 lifecycle tests** and **24 desktop geometry cases**. Keyboard,
  named history, reading/selection retention, focus and reduced motion checks pass. Contrast
  remains 5.7947:1 for Logout text, 4.9248:1 for input boundary against fill, and 4.6004:1
  against panel RGB. Generated evidence remains under ignored `runtime/mvp4-fixes/`.
- No additional application change was needed for the requested F1-F5 priorities. This checkpoint
  updates only this report. Native package candidate hashes above remain unchanged; concurrent
  `PWA_MVP3_PROGRESS.md` content remains untouched. No physical-device evidence, enrollment,
  revocation, Garmin read or route change is claimed.

2026-10-10 M4A physical-acceptance preparation at baseline `5384121`:

- Owner reports **phone available later**. No physical-device check was run; iPhone/iOS, keyboard
  availability and phone-loaded shell version remain unknown. The new
  [M4A acceptance matrix](../PWA_M4A_ACCESSIBILITY_ACCEPTANCE.md) freezes separate Safari/Home
  Screen steps and pending result rows for speech, enlarged text, zoom, focus, touch and recovery.
  Actual desktop browser 400% zoom stays separate from viewport emulation and phone magnification.
- Application assets remain shell `v7`, byte-for-byte unchanged. Fresh local evidence passes
  **43/43 lifecycle tests** and **24/24 desktop geometry cases**, now on Windows Edge
  **155.0.4283.45**. Named history, keyboard/focus, reading/selection retention and reduced motion
  checks pass. Contrast remains Logout text **5.7947:1**, input boundary/fill **4.9248:1**,
  input boundary/panel **4.6004:1**. These are desktop results, not spoken Safari acceptance.
- `rtk uv run pytest --basetemp runtime/mvp4-fixes/pytest-20261010-m4a`: **1,439 passed,
  3 skipped**, **85.59% coverage**, **105.43s**; one existing warning. Root and Garmin sidecar
  lock checks/locked sync pass; Ruff format/lint (410 files), mypy (164 source files), root
  pip-audit and sidecar audit through `--path garmin_sync/.venv/Lib/site-packages` pass.
  Gitleaks history scans 95 commits with no leaks; local documentation links and diff checks pass.
- Standard `jarvis doctor` initially hit console `OSError: [Errno 22] Invalid argument` using
  `cp1252` output. The same CLI succeeds through a Node subprocess with process-only
  `PYTHONIOENCODING=utf-8`; no repository/environment configuration changed. This is installation
  diagnostics under default settings, not private-route or phone readiness evidence.
- Baseline local HEAD, tracking ref and live upstream `main` match
  `53841218d616a6d09c172cec7ed29537afef023b`.
  [CI run 38016337629](https://github.com/DanCreates1/JARVIS/actions/runs/38016337629) succeeds
  at that exact SHA: Windows quality and secret scan, including both Python dependency audits.
  This is baseline CI; the documentation publication has its own subsequent run.
- Preservation SHA256 checks pass for both native package candidates (hashes above), all four
  inspected shell assets and `PWA_MVP3_PROGRESS.md`
  (`eddd4479a9ae1b11029f5436e01b81ccaa6ecdebbc5b7bfb1241b0d5a01e146b`). Native verification
  was not rerun for this documentation-only session; the existing native dependency-audit hold
  remains. Generated browser/pytest evidence stays ignored under `runtime/mvp4-fixes/`.
- Publication scope is four documentation files: M4A matrix, this report, phase overview and
  master roadmap. No application behavior, Core service, private route, enrollment/revocation,
  key erasure, Garmin read or M3C report changed. Physical M4A and aggregate MVP 4 stay open.

Official implementation references checked 2026-10-09: [network availability](https://developer.mozilla.org/en-US/docs/Web/API/Window/online_event),
[queued/abortable Web Locks](https://developer.mozilla.org/en-US/docs/Web/API/LockManager/request),
[scroll-container keyboard access](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/overflow),
[text resize](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html),
[reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html),
[text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html),
[control contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html),
[status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html).

2026-10-12 M4A resumption and desktop zoom checkpoint at baseline `2cb1f96`:

- Owner confirmed iPhone available and Home Screen JARVIS opens with **Offline shell**.
  One **Connect existing device** attempt returned **Connection failed**; owner subsequently
  reported connected. Recovery method/error detail unreported; no cause or spoken-failure pass
  inferred. Owner reports **iPhone 15 Pro, iOS 27.0.1**, metadata receipt recorded at
  `2026-10-12T13:26:59-04:00`. Settings, keyboard availability and phone-loaded version remain
  pending. Owner subsequently confirmed VoiceOver speaking, receipt recorded at
  `2026-10-12T13:32:22-04:00`; this is enablement preparation, not JARVIS speech acceptance.
  Owner then said the first Device access labels read their displayed text, receipt recorded at
  `2026-10-12T13:34:25-04:00`. This is partial A1 naming evidence; disabled-state announcement,
  remaining labels and complete reading order are unobserved. Owner subsequently reported
  **enroll device button** on single touch, without a dimmed/unavailable word (receipt
  `2026-10-12T13:35:40-04:00`), then **Connected; button looks normal** (receipt
  `2026-10-12T13:36:53-04:00`). This differs from the expected host v7 disabled enrollment state;
  phone assets/native disabled state remain unverified, so no screen-reader failure classification
  is inferred. Public access-status guidance below Connect is requested as supporting loaded-script
  evidence. Owner instead suspected an older website and requested the current link. The existing
  private route, one Python loopback listener and current static shell/script/worker were rechecked;
  HTTP 200 and host v7 references pass. Current `/app/?m4a=v7` HTML also passes; the query avoids
  the worker's exact cached navigation key, without website-data clearing or route changes. The
  private link was supplied only to its owner on request and remains absent from Git. Safari
  displays **enroll with an approved ticket, or connect an existing device key.** (receipt
  `2026-10-12T13:43:59-04:00`), the initial v7 HTML access-status paragraph absent in historical
  v6. This does not prove loaded script/worker execution or enrollment. Asked for Safari Enroll/Send
  VoiceOver names/state, owner said screen text is read with nothing special (receipt
  `2026-10-12T13:47:12-04:00`). Asked specifically whether Send includes dimmed/unavailable,
  owner answered **Yes**. This verifies that individual Safari state announcement only; full A1
  names/order and loaded assets remain pending. Owner confirmed Refresh Garmin, Refresh tasks
  and Logout and erase this device all clearly named during swiping, without activation. Owner
   then confirmed Message and the Conversation history area both clearly named. Owner subsequently
   confirmed Enrollment ticket JSON, Enroll device and Connect existing device names and sensible
   page reading order, then all remaining greyed-out controls announcing unavailable. Explicit
   heading traversal and test settings remain pending before closing A1. Cached/older Home Screen assets are a
  possible explanation, not a verified cause; full phone assets and Safari identity remain
  unverified. Instructions proceed in small phone steps.
  No complete physical A1-A11 pass is claimed. Safari observations remain preliminary. Before another
  A3 Connect activation, the matrix now requires public on-page non-health guidance: an existing
  health-enabled identity can automatically refresh Garmin after authenticated polling.
- Existing private Serve route passed ownership/backend/origin checks; tailnet online, Funnel
  disabled. Core was found stopped; resumed with its existing configuration: one Python-owned
  listener at `127.0.0.1:8765`, no non-loopback Core listener. Local/private shell, script and worker
  return HTTP 200 with host `v7` references. Route untouched. This is service readiness, not the
  M3C phone Core-restart row or proof of phone-loaded assets. No Garmin read or identity operation.
- Fresh **43/43 lifecycle tests** and **24/24 desktop geometry cases** pass on Edge
  **155.0.4283.45**. Contrast remains Logout text **5.7947:1**, input boundary/fill **4.9248:1**,
  input boundary/panel **4.6004:1**. Existing harness required normal local access after sandbox
  loopback `EACCES`; no application or Windows security setting changed.
- Separate actual desktop browser zoom gate passes in a fresh headless Edge profile with native
  `tabs.setZoom` in automatic/per-tab mode. At 100%, `innerWidth=1280`, scrollbar-adjusted
  `clientWidth=1265`; at 400%, `innerWidth=320`, `clientWidth=316`, visual width **316.25** and
  root/body scroll widths **316**. DPR **4**, visual scale **1**, CSS zoom **1**. Long public fixtures
  have no inspected horizontal overflow. Ten controls reachable/pointer-hit checks, history
  keyboard scrolling, reading/selection retention, Jump focus, text entry and mocked Send pass.
  Controls use test hooks; no authenticated Core action, phone, speech or WCAG conformance claim.
  Independent read-only review confirms actual zoom and these limits. Zoom restored; isolated
  processes closed. Final ignored evidence timestamp: `2026-10-12T17:02:09.614Z`.
- Root/sidecar lock checks and locked sync pass; Ruff format/lint (**410 files**), mypy
  (**164 source files**), root/sidecar audits and UTF-8 process-only `jarvis doctor` pass.
  Windows blocked the `pytest`/`pip-audit` console launchers with Application Control error **4551**;
  existing Python module entry points execute without changing policy. Full
  `rtk uv --cache-dir runtime/uv-cache-mvp3 run python -m pytest --basetemp runtime/mvp4-fixes/pytest-20261012-m4a`
  passes **1,439 tests, 3 existing skips**, **85.55% coverage**, **102.76s**, one existing warning.
  Both audits use `python -m pip_audit`; sidecar audit uses
  `--path garmin_sync/.venv/Lib/site-packages`. Gitleaks history scans **96 commits**, no leaks.
- Application assets remain unchanged, shell `v7`. Native package candidates and MVP 3 report
  retain their recorded preservation hashes. Runtime checkers, browser profiles, synthetic
  screenshots/JSON and pytest directories stay ignored. Publication scope remains the M4A matrix,
  MVP 4 report, overview and roadmap; physical M4A and aggregate MVP 4 remain open.
- Four-document checkpoint `843f916fc6df068e3164411ed6292ff71465dc3a` was pushed to `main`;
  local HEAD, tracking ref and live upstream matched. [CI run 38282189854](https://github.com/DanCreates1/JARVIS/actions/runs/38282189854)
  passed Windows quality and secret scan at that exact SHA. Follow-up documentation checkpoint
  `d6dd790e05ea685a1bcc8951028e02d8bcb7418c` also passed
  [CI run 38282852401](https://github.com/DanCreates1/JARVIS/actions/runs/38282852401): Windows
  quality and secret scan at that exact SHA. The later owner report of a recovered Home Screen
  connection and phone metadata is recorded above. No physical row is closed by these checkpoints.

2026-10-13 M4A continuation at `d6dd790`, shell `v7`:

- Owner confirms phone available; Safari context is **portrait, normal text/page zoom, VoiceOver
  on, no external keyboard**. Numeric text/zoom values uninspected; these settings do not establish
  the previous day's exact context. A10 is blocked for both surfaces by missing equipment.
  Owner then confirmed Device access, Conversation and Garmin announced as headings in order,
  with clear single-touch heading reading. **Safari A1 passes for the observed shell**: required
  names, reading order and unavailable-state announcements, combined with 2026-10-12 observations.
  This does not close script/worker verification, Home Screen A1, authenticated transitions or M4A.
  VoiceOver off was confirmed for visual checks. Largest-text setup was requested, then owner
  stopped remaining phone tests before confirming its setting or any webpage response (decision
  receipt `2026-10-13T20:13:50-04:00`). Physical acceptance was **owner-deferred** at that checkpoint;
  no questions queued until the subsequent owner request. No A7 pass had been observed then and
  skipping did not accept M4A/MVP 4.
- Core was found stopped; resumed the existing owned private route's loopback configuration.
  Settled check: one Python-owned `127.0.0.1:8765` listener, no non-loopback listener, tailnet online,
  origin/route/backend ownership intact, Funnel disabled. Current static shell/script/worker return
  HTTP 200 with host v7 references. No route/identity operation, ticket or Garmin read. Service
  readiness does not accept M3C restart or verify phone-loaded assets.
- Continuation started at `d6dd790`; all four PWA asset hashes match the prior checkpoint. Native
  package candidate hashes and MVP 3 report hash remain preserved. Two-document Safari A1
  checkpoint `345eb2453f5c7fab690726d9558777e895d92fbf` was committed/pushed after staged secret,
  diff and local-link checks. Owner-deferral publication also updates overview and roadmap; no
  application fix or new local test result claimed.

2026-10-13 owner resumption after the deferral checkpoint:

- Deferral checkpoint `21e60ac40bdf0d2ae9e6df16ba56ea3b7a966381` passed
  [CI run 38489374156](https://github.com/DanCreates1/JARVIS/actions/runs/38489374156): Windows
  quality gate and secret scan at that exact SHA, including the full tests and both Python audits.
  This verifies publication quality; it does not accept the deferred physical rows.
- Owner explicitly resumed phone checks (receipt `2026-10-13T20:20:26-04:00`); use compact batches
  and record working observations. Fixed acceptance criteria and existing scope remain intact.
- Safari visual batch at maximum accessibility text plus 200% Page Zoom: both orientations,
  empty-ticket keyboard show/dismiss, text/caret/control readability and scrolling reachability.
  Owner reports **all worked**, then explicitly confirms webpage text grew before website zoom.
  **Safari A7/A9 observed passes; A8 200% website zoom passes**, with its highest offered value and
  separate magnification still pending. No authenticated Message keyboard or Home Screen result
  claimed; script/worker gate remains open. Current step is original Home Screen public guidance
  and two online reopenings, no protected activation. Restore usual settings after the session.
- Owner then confirmed both Home Screen messages match: public non-health guidance before two
  online close/reopenings and exact v7 enrolled-key startup sentence afterward. This supports
  current Home Screen JavaScript execution and retained identity, with full script URL/CSS/worker
  gate open. Scope evidence comes from the pre-reopening guidance and unchanged identity, not
  the startup sentence alone. Current batch is bounded VoiceOver A1/A3 plus one existing non-health
  Connect and 30-second steady-state speech observation; no tickets/scopes/Garmin operation.
- Owner reported **all worked** for the updated Home Screen connection batch: clear headings/
  names/order/unavailable states, usable busy/ready focus, Message/Send unavailable until readiness
  and no repeated steady connection speech for 30 seconds. **Home Screen A3 passes** using the
  existing non-health identity. Explicit Message single-touch reading is requested with the public
  chat fixture before closing Home Screen A1; streamed speech/earlier-reading A4 remains pending.
- Owner then reported **ALL WORKED** for Message single-touch/activation, one public blue-cube
  fixture, earlier reading during streaming, no repeated delta interruptions or forced position
  loss and one spoken completion. **Home Screen A1 and A4 pass** for these observed cases. No
  transcript retained. A5 selection/reading retention and Jump to latest focus are the next batch;
  reply-too-quick/uncertain-submission limitations remain explicit.
- Owner reported **pass pass keep goin** for selection/earlier-reading retention during a further
  public reply and named Jump to latest content/Conversation focus. **Home Screen A5 passes** for
  the observed batch. Next batch covers Home Screen largest text/layout/keyboard/pinch, Reduce
  Motion and safe ordinary/VoiceOver Refresh tasks activation, plus Safari highest website zoom/
  pinch/empty-ticket touch. No health/enrollment/logout/notification activation requested.
- Resumption/visual-evidence checkpoint `bdaca5d3c5d1b75357b9f9691cc3d6f0c0eb1aa7` passed
  [CI run 38490869728](https://github.com/DanCreates1/JARVIS/actions/runs/38490869728): Windows
  quality and secret scan at that exact SHA. No application change or CI rerun.
- Owner reported **all worked** for the visual finish batch: actual Home Screen webpage text
  growth at largest accessibility size, readable/separate controls in both orientations,
  authenticated Message keyboard/caret/Send scrolling reachability, pinch/pan and no panel
  entrance motion with Reduce Motion. Ordinary and VoiceOver Refresh tasks each updated the
  intended panel. Safari highest offered website zoom, pinch/pan, ordinary/VoiceOver empty-ticket
  touch and Reduce Motion reload worked. **Home Screen A7/A9 and both surfaces' bounded A11 pass**.
  Safari maximum website percentage was requested but unreported; no protected Safari activation.
- Owner reported **all worked** for the final separate iOS Full Screen Zoom/restoration batch:
  usual text/website zoom restored first, VoiceOver off, magnified text/controls and panning usable
  in Safari and Home Screen. The aggregate response covers restoration of usual Zoom, text size,
  Safari Page Zoom, Reduce Motion and VoiceOver; exact restored values were not separately given.
  **Home Screen A8 passes for available mechanisms**; Safari's observed A8 mechanisms pass, with
  maximum website percentage still unreported. Screen Zoom level was not reported on either
  surface. No numeric 400% phone reflow claim. No further phone questions queued this session.
- Final evidence recorded `2026-10-13T21:35:15-04:00` (documentation checkpoint, not a timestamp
  for every phone action). Application shell remains v7 with no asset changes. Native candidate
  files and MVP 3 report retain their recorded hashes; only the four PWA documentation files are
  included in this publication. Existing Core is left running; M3C acceptance remains separate.

## Remaining gates and handoff

M4A local fixes are reviewable; **MVP 4 is not complete**. Owner resumed manual phone checks after
brief deferral on 2026-10-13. Bounded Safari A1/A7/A9/A11 and Home Screen
A1/A3/A4/A5/A7/A8/A9/A11 observations passed. Safari website zoom at 200% and highest offered value,
pinch and iOS screen magnification worked; the maximum website percentage remains unreported.
Full phone script URL/CSS/worker verification is open despite the Home Screen v7 runtime
fingerprint. Safari identity/script execution is unverified, so its authenticated A3-A5 remain
unexecuted; do not enroll it for M4A. A2 invalid-ticket acceptance remains unexecuted, blocked on
Home Screen by its retained identity. A6 failure/recovery/draft speech was not exercised; the
earlier plain connection failure is no substitute. A10 is blocked without an external keyboard.
Logout focus/cleanup stays blocked on separate M3C exact-device authority/evidence. Actual desktop
browser 400% zoom passed on the synthetic Edge shell 2026-10-12. Retain the dated
[M4A matrix](../PWA_M4A_ACCESSIBILITY_ACCEPTANCE.md). F11 needs protocol-aware cancellation/retry and Core-backed history,
including uncertain commit outcome/session guards, before its phone soak. Record explicit phone
performance thresholds before measurements and milestone closure. M3C health-scoped phone
enrollment/revocation/Garmin recovery acceptance stays in its separate report and authority scope.

Estimated active PWA completion: **88%**; accepted phone chat/protected Core Garmin plus verified
M4A local accessibility fixes and bounded owner-reported phone accessibility passes. Health-scoped
physical acceptance, remaining accessibility prerequisites/failure cases,
chat cancel/retry/history and performance/release gates remain open. Estimate is milestone-based,
not a measured test percentage.
