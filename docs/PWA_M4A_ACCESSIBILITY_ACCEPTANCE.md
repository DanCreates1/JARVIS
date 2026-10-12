# PWA M4A — physical accessibility acceptance

Status: `in-progress` — owner confirmed phone available on 2026-10-12; accessibility observations pending.
Target: `main` baseline `2cb1f96`, shell `v7`; application assets unchanged in this session.
Aggregate MVP 4 remains `in-progress`. Preparation and desktop evidence do not accept a phone row.

## Scope and prerequisites

Run on the owner's physical iPhone, separately in Safari and the existing Home Screen web app.
Use the existing approved private HTTPS origin and existing enrolled identity where present.
**Connect existing device** and public text chat use existing scope; do not issue tickets, erase
keys, revoke devices, change routes, read Garmin, or turn on notifications for this matrix.
Safari and Home Screen may have different identity state: an unenrolled surface can run shell
checks only. Mark its authenticated rows blocked; do not enroll it to satisfy M4A.

M3C health-scoped enrollment, Garmin values/freshness, Wi-Fi/cellular recovery, Core restart,
logout/erase and test-device revocation stay in [MVP 3 progress](phase-reports/PWA_MVP3_PROGRESS.md).
M4A can inspect the empty Garmin panel's labels without pressing **Refresh Garmin**. Destructive
logout-focus acceptance must use the separately approved M3C test device; mark it pending here
until that evidence exists. Do not renew or expand M3C authority through this checklist.

Before testing, record date/time with offset, iPhone model and iOS version, surface, orientation,
text/zoom settings, VoiceOver state and external keyboard model if available. Keep account/device
identifiers, private origin, tickets, health values and transcripts out of evidence. Report row ID,
pass/fail/blocked, control name and sanitized symptom only. No screenshot or recording needed.

Reload online, allow the current service worker to activate, then close/reopen each surface.
Expected source has `app.js?v=7` in `index.html` and `jarvis-shell-v7` in `sw.js`. A host source
check alone cannot prove which cached page the phone loaded. Record phone version verification
method, or mark it unverified. If available, inspect only script URL/cache version using trusted
Safari tooling; do not copy storage, cookies, network bodies or keys. No website-data clearing.

## Procedure and fixed pass criteria

Run each row in both surfaces unless its stated platform prerequisite is absent. Each required
control must remain reachable and understandable; missing equipment or unchanged text is a
recorded blocker/limitation, never a pass. Stop a row after an accessibility failure and record
the smallest reproducible symptom. Restore the owner's previous accessibility settings afterward.

| ID | Action | Pass criterion |
| --- | --- | --- |
| A1 | With VoiceOver on, swipe through headings and controls; explore by touch. | Logical reading order; names for Enrollment ticket JSON, Enroll device, Connect existing device, the Conversation history region, Message, Send, Refresh tasks and Refresh Garmin. Disabled controls convey unavailable state. Inspect Logout label without activating it. |
| A2 | Read empty/error guidance slowly. If the surface already has no identity, enter only `{` and activate Enroll device. Otherwise leave this invalid-ticket case blocked. | Error associated with Enrollment ticket JSON; recovery remains available after 30 seconds and can be read again. No ticket issued or successful enrollment. Existing identity remains untouched. |
| A3 | On an already enrolled surface, focus Connect existing device and activate it. Keep VoiceOver on through checking/connected states. | Focus stays recoverable when controls become busy/disabled; no focus trap or unexpected jump into unrelated content. Message and Send become usable only after authenticated readiness. Steady connection does not repeatedly interrupt speech. |
| A4 | Send public fixture: `Write eight numbered sentences about a fictional blue cube. Do not use tools or save memories.` Read an earlier displayed line while the reply streams. | Stream deltas do not repeatedly interrupt reading. A completed-answer status is spoken once for that reply. Earlier reading position remains usable; new answer does not force focus to the bottom. Record actual speech behavior, not DOM inference. |
| A5 | Scroll earlier history; select public fixture text while more text arrives. Activate Jump to latest when shown. | Reading/selection retained through arriving text. Jump to latest has a clear name, reaches latest content and returns usable focus to Conversation history. No lost text or trap. If reply ended before observation, repeat a public fixture and record incomplete observation honestly. |
| A6 | If an ordinary chat/connection failure occurs, listen to its status and reread recovery after 30 seconds. Do not replay an uncertain submission. | Failure and recovery understandable without transient notices; draft retained where submission is unconfirmed. No false completion or repeated delta speech. If no failure occurs, leave spoken-failure acceptance pending; desktop failure tests cannot close it. |
| A7 | Set Settings > Accessibility > Display & Text Size > Larger Text to largest available accessibility size; reopen both surfaces, portrait and landscape. Record actual webpage text response. | Text and required controls readable/reachable without clipping or overlap. If webpage text does not enlarge, record that limitation; setting the slider alone does not accept text scaling. Restore previous setting after testing. |
| A8 | In Safari, use its website Page Menu zoom at 200% and highest offered value. In both surfaces test pinch/iOS Zoom separately when available. | At 200% website zoom, content and functionality retained. Magnified touch/reading usable. Record mechanism and value separately; pinch/iOS screen magnification does not accept layout reflow or a numeric browser 400% gate. Home Screen has no assumed Safari Page Menu. |
| A9 | Rotate portrait/landscape; show and dismiss software keyboard in Message (or empty ticket field), including largest text. | Caret and focused field can be brought into view; required controls reachable by scrolling. No keyboard trap, safe-area clipping, overlap with home indicator, or unreachable Send. |
| A10 | With an already available external keyboard, test forward/backward navigation, activation and Conversation scrolling with VoiceOver off; then use configured VoiceOver navigation/activation commands. Record keyboard-access settings. | Visible focus; all enabled controls/history reachable in sensible order; no trap, lost focus or obscured required control. Jump to latest returns usable history focus. No keyboard means blocked, not pass. |
| A11 | Enable Reduce Motion; reopen app. Explore visible buttons by ordinary touch and VoiceOver touch/double-tap. | No panel entrance motion; controls distinguishable and activate intended target, including at enlarged text. Do not activate enrollment/logout/Garmin merely to test target size. Desktop 44 CSS px geometry is supporting evidence only. |

Apple documents [VoiceOver gestures](https://support.apple.com/en-ca/guide/iphone/iph3e2e2281/ios),
[external keyboard commands](https://support.apple.com/en-ca/guide/iphone/iph6c494dc6/ios),
[larger text](https://support.apple.com/en-ca/guide/iphone/iph3c076905a/ios),
[Safari website zoom](https://support.apple.com/en-ca/guide/iphone/iphb3100d149/ios) and
[iOS Zoom](https://support.apple.com/en-ca/guide/iphone/iph3e2e367e/ios). Select the installed iOS
version in each guide; menu names and configured shortcuts can differ. References checked
2026-10-10. These instructions do not assert that JARVIS supports Dynamic Type on WebKit.

## Separate actual browser zoom gate

Desktop 320 CSS px emulation remains supporting geometry evidence. On a desktop browser, set a
1280 CSS px content viewport at 100%, then use actual browser zoom 400%, record resulting layout
width and check content/controls without two-direction reading scroll. Do not use CDP viewport
override, CSS zoom or pinch as its substitute. Dated browser evidence below closes this separate
desktop gate for the bounded synthetic shell; phone rows remain independent.
[W3C reflow guidance](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) distinguishes
320 CSS px layout reflow from magnification; [resize text](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html)
requires retained content/functionality at 200% text enlargement. No WCAG conformance claim follows
from this bounded matrix alone.

## Results ledger

Phone metadata and version verification: **pending — phone available; owner details/observations requested
2026-10-12**. Availability alone accepts no row. Historical 2026-10-10 phone-unavailable checkpoint
remains in the MVP 4 report.
Use `pending`, `pass`, `fail`, or `blocked: reason`. Keep independent surface results.

| Row | Safari | Home Screen | Dated sanitized observation |
| --- | --- | --- | --- |
| Version / device metadata | pending | pending | Phone available 2026-10-12; Home Screen opens with Offline shell; model/iOS, enrollment state, keyboard and loaded version not yet verified |
| A1 names / reading order | pending | pending | — |
| A2 persistent error / recovery | pending | pending | — |
| A3 busy / disabled focus | pending | pending | 2026-10-12 Home Screen preparation: Connect existing device returned Connection failed; detailed guidance and VoiceOver behavior unobserved |
| A4 completed speech / earlier reading | pending | pending | — |
| A5 selection / Jump to latest | pending | pending | — |
| A6 spoken failure / draft | pending | pending | — |
| A7 largest text | pending | pending | — |
| A8 website zoom / magnification | pending | pending | Record each supported mechanism separately |
| A9 rotation / keyboard / safe areas | pending | pending | — |
| A10 external keyboard | pending | pending | Equipment not yet confirmed |
| A11 reduced motion / touch | pending | pending | — |
| Logout focus / cleanup | blocked: M3C exact-device authority/evidence | blocked: M3C exact-device authority/evidence | No erasure in M4A |
| Actual desktop browser 400% | not applicable | not applicable | Pass: desktop Edge synthetic shell, 2026-10-12; Edge 155.0.4283.45, native automatic/per-tab browser zoom; innerWidth 1280 at 100%, 320 at 400%; root/body scrollWidth 316 equals clientWidth 316 |

2026-10-12 browser evidence: fresh isolated headless Edge profile, actual
[`tabs.setZoom`](https://developer.chrome.com/docs/extensions/reference/api/tabs#type-ZoomSettingsMode)
in `automatic`/`per-tab` mode. Native window bounds established `innerWidth=1280` at 100%; scrollbar
leaves `clientWidth=1265`. At 400%, `innerWidth=320`, `clientWidth=316`, visual viewport width
`316.25`, DPR `4`, visual scale `1` and CSS zoom `1`. No horizontal overflow in inspected components
or long public fixtures. Ten controls reachable with pointer-hit checks; keyboard history scrolling,
reading/selection retention, Jump focus, text entry and mocked Send passed. Controls were enabled
by test hooks; this does not prove protected Core actions, every control's activation, speech or
phone behavior. Zoom restored; isolated processes closed. Reviewed local harness, JSON and
synthetic screenshot remain ignored under `runtime/mvp4-fixes/`; final JSON timestamp
`2026-10-12T17:02:09.614Z` (`13:02:09.614-04:00`). No WCAG conformance claim.

2026-10-12 phone session: owner confirmed Home Screen JARVIS opens, then reported **Offline shell**.
Owner tapped **Connect existing device** once and reported **Connection failed**. Smaller error
guidance remains pending; VoiceOver was not confirmed enabled, so this does not accept A3. Device/settings,
reload/version proof and all accessibility rows remain pending. Safari has not yet been observed.

## Closure and resumption

M4A physical acceptance requires dated actual-device evidence for applicable rows, verified
current phone assets, resolution/retest of critical failures, and explicit pending limitations.
Absent identity/equipment or a required browser feature leaves the relevant gate open. No health
scope or enrollment is required for shell-only work. Run focused tests after any fix and applicable
release/security gates before publication. Record outcomes in
[MVP 4 progress](phase-reports/PWA_MVP4_PROGRESS.md); keep this ledger synchronized.

Chat cancel/retry, Core-backed history across restart, full reconnect/restart soak and startup/
navigation/first-delta/memory performance remain later MVP 4 work. This checklist adds no such
implementation, and no physical performance threshold or result is claimed. Freeze those
thresholds before that later measurement session. Keep `PWA_MVP3_PROGRESS.md` and native package
candidates unchanged during M4A publication.
