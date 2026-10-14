# PWA M4A — physical accessibility acceptance

Status: `in-progress` — owner resumed phone checks on 2026-10-13; Safari A1/A7/A9 observations passed.
Target: `main` baseline `2cb1f96`, shell `v7`; application assets unchanged in this session.
Aggregate MVP 4 remains `in-progress`. Preparation and desktop evidence do not accept a phone row.
Use compact phone batches. Results follow actual reported observations; unexecuted checks remain unverified.

## Scope and prerequisites

Run on the owner's physical iPhone, separately in Safari and the existing Home Screen web app.
Use the existing approved private HTTPS origin and existing enrolled identity where present.
**Connect existing device** and public text chat use existing scope; do not issue tickets, erase
keys, revoke devices, change routes, read Garmin, or turn on notifications for this matrix.
Safari and Home Screen may have different identity state: an unenrolled surface can run shell
checks only. Mark its authenticated rows blocked; do not enroll it to satisfy M4A.

Before another **Connect existing device** activation, confirm the already connected surface
shows **Garmin access needs a new approved browser enrollment.** This confirms the current
client's non-health state, not a live Core scope inventory. If absent or unverified when A3 is
attempted, mark A3 blocked; do not reconnect to discover scope. A health-enabled identity can
automatically refresh Garmin after the first authenticated event poll, outside this matrix.

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
| A1 | With VoiceOver on, swipe through headings and controls; explore by touch. | Logical reading order; names for Enrollment ticket JSON, Enroll device, Connect existing device, the history region named Conversation, Message, Send, Refresh tasks and Refresh Garmin. Disabled controls convey unavailable state. Inspect Logout and erase this device label without activating it. |
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

Phone: owner reports **iPhone 15 Pro, iOS 27.0.1**, recorded
`2026-10-12T13:26:59-04:00`. This timestamps receipt of metadata, not every preceding phone action.
Home Screen connection preparation recovered; owner confirmed VoiceOver speaking at
`2026-10-12T13:32:22-04:00` (report receipt). For the 2026-10-13 **Safari context**, owner reports
portrait, normal text/page zoom, VoiceOver on and no external keyboard. Numeric text/zoom values were not
inspected; do not assign these later settings retroactively to the previous day's observations.
Phone-loaded script/worker verification remains pending. Availability and ordinary
connection alone accept no row. Historical 2026-10-10 phone-unavailable checkpoint remains in the
MVP 4 report.
Use `pending`, `pass`, `fail`, or `blocked: reason`. Keep independent surface results.

| Row | Safari | Home Screen | Dated sanitized observation |
| --- | --- | --- | --- |
| Version / device metadata | pending | pending | iPhone 15 Pro/iOS 27.0.1 reported 2026-10-12. Safari shows v7 HTML guidance; loaded script/worker and Home Screen assets unverified. 2026-10-13 Safari context: portrait, normal text/page zoom (numeric values uninspected), VoiceOver on, no external keyboard |
| A1 names / reading order | pass: observed Safari shell | pending | Safari 2026-10-12/13: all required control/history names clear, reading order sensible, disabled controls announce unavailable; Device access/Conversation/Garmin headings in order and touch reading clear. Full assets gate remains open. Home Screen: Enroll speaks only "enroll device button" and looks normal while connected; assets/native disabled state unverified, no failure inferred |
| A2 persistent error / recovery | pending | pending | — |
| A3 busy / disabled focus | pending | pending | 2026-10-12 Home Screen preparation: Connect existing device initially returned Connection failed; owner subsequently reports connected. Recovery method and VoiceOver behavior unobserved |
| A4 completed speech / earlier reading | pending | pending | — |
| A5 selection / Jump to latest | pending | pending | — |
| A6 spoken failure / draft | pending | pending | — |
| A7 largest text | pass: observed Safari layout | pending | 2026-10-13 owner reports webpage text grew at maximum accessibility text before website zoom; visual batch in both orientations worked at largest text plus Safari 200%. Home Screen unobserved |
| A8 website zoom / magnification | pending: 200% website zoom passed | pending | Safari 200% Page Zoom visual/keyboard batch worked; highest offered website value and separate pinch/iOS Zoom observations pending |
| A9 rotation / keyboard / safe areas | pass: empty ticket field | pending | 2026-10-13 Safari: both orientations, empty-ticket keyboard show/dismiss, caret/text/controls readable and scroll-reachable at largest accessibility text plus 200% website zoom; owner reports all worked. Authenticated Message keyboard not tested |
| A10 external keyboard | blocked: no external keyboard | blocked: no external keyboard | Owner confirmed no keyboard available 2026-10-13; no keyboard acceptance inferred |
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
Owner tapped **Connect existing device** once and reported **Connection failed**, then subsequently
reported connected. Recovery method and smaller error guidance were not reported; do not infer a
cause or a spoken-failure pass. Owner reports **iPhone 15 Pro, iOS 27.0.1**, then confirmed
**VoiceOver speaking**. The connection observation preceded VoiceOver confirmation and does not
accept A3. At report receipt `2026-10-12T13:34:25-04:00`, owner said the first Device access
labels read their displayed text. This is partial A1 evidence only; no disabled-state announcement
or complete reading order was reported. Text/zoom settings, reload/version proof and all complete
accessibility rows remained pending at that checkpoint. Instructions proceed in small phone
steps. Owner subsequently reported that touching **Enroll device** speaks only
**enroll device button**, without a reported dimmed/unavailable word (receipt
`2026-10-12T13:35:40-04:00`). Owner then reported **Connected; button looks normal** (receipt
`2026-10-12T13:36:53-04:00`). Current host v7 disables Enroll device when an identity exists, but
phone-loaded assets and native disabled state remain unverified. Record this discrepancy without
assuming a screen-reader failure or accepting A1. Owner then suspected an older website and
requested the current link instead of reporting access-status guidance. Historical v6 leaves
Enroll device enabled and lacks the v7 access-status paragraph, so cached/older assets are one
possible explanation, not a verified cause. The existing owned private route and one loopback
Python listener were rechecked; current static shell/script/worker return HTTP 200 with host v7
references. A navigation to `/app/?m4a=v7` also returns current HTML; its query avoids the worker's
exact cached `/app/` navigation key, without clearing storage or changing routes. Current private
link was supplied only to the owner on request, omitted from repository evidence. The current
step was to open it in iPhone Safari and report public access-status guidance, without enrollment
or Connect activation. Owner reported **enroll with an approved ticket, or connect an existing
device key.** (receipt `2026-10-12T13:43:59-04:00`). This matches the initial v7 HTML paragraph,
absent in historical v6. It does not prove current script/worker execution or an enrolled Safari
identity. Asked for Safari VoiceOver names/state for **Enroll device** and **Send**, owner reported
**it reads whatever that is on the screen nothing special** (receipt
`2026-10-12T13:47:12-04:00`). Individual announcements/state words were not given; do not convert
this into either a disabled-state pass or failure. Asked specifically whether touching **Send**
speaks dimmed/unavailable, owner answered **Yes**. This accepts that individual Safari state
announcement, not the complete A1 row or loaded-script/identity state. Owner subsequently
confirmed **Refresh Garmin**, **Refresh tasks** and **Logout and erase this device** are all
clearly named during swiping, without activation. Owner then confirmed **Message** and the history
area **Conversation** both clearly named. Owner then confirmed **Enrollment ticket JSON**, **Enroll
device** and **Connect existing device** clearly named, with sensible page reading order. Asked
about Message, Refresh Garmin, Refresh tasks and Logout and erase this device, owner confirmed
**All greyed-out controls announce unavailable**. These are bounded Safari naming/order/state
observations, with single-touch Enroll/Send inspection and no activation. Explicit heading traversal
and test settings were still pending at this checkpoint. Ordinary HTTP evidence and an HTML
fingerprint cannot accept the full loaded-asset gate.

2026-10-13 continuation: owner confirmed iPhone available again, then reported **portrait; normal;
on; no keyboard** for Safari orientation, text/page zoom, VoiceOver and keyboard availability.
Owner then confirmed **Device access**, **Conversation** and **Garmin** announced as headings in
that order, and a single-touch heading sample read clearly (final report receipt
`2026-10-13T20:09:13-04:00`, not an exact timestamp for every preceding phone action). This closes the bounded Safari A1
names/order/disabled-state observation; current script/worker asset verification and Home Screen A1
remain open. VoiceOver was subsequently confirmed off for visual checks. Largest accessibility-
text setup was requested, but owner stopped remaining phone tests before confirming the setting
or any webpage response (decision receipt `2026-10-13T20:13:50-04:00`). A7-A9/A11 were unexecuted
at that checkpoint; A2-A6 and current-asset/Home Screen acceptance remained open. A10 was blocked
by missing equipment. No further phone checks were queued until the owner's subsequent resumption.
No physical result is inferred from the desktop in-app
browser. Core was found stopped; resumed with its existing owned private
route and loopback configuration. Settled checks confirm one Python-owned `127.0.0.1:8765` listener,
no non-loopback listener, tailnet online, Funnel disabled and static shell/script/worker HTTP 200
with host v7 references. This is readiness, not M3C restart acceptance or phone asset proof. No
route/identity operations, tickets or Garmin reads.

Owner resumed phone checks (receipt `2026-10-13T20:20:26-04:00`) and requested a pragmatic, compact
flow. Safari visual batch: maximum Larger Accessibility Sizes, observe actual webpage growth,
Page Zoom 200%, both orientations and empty-ticket software-keyboard show/dismiss with caret,
text and controls readable/reachable by scrolling. Owner reported **all worked** (receipt
`2026-10-13T20:23:18-04:00`), then explicitly confirmed **Webpage text got bigger** before website
zoom. This accepts the bounded Safari A7/A9 observations and A8's 200% website-zoom component;
other A8 mechanisms and all Home Screen observations remain pending. No protected action taken.
Current Home Screen preparation asks for public non-health guidance before close/reopen twice
online, then the v7 enrolled-key startup sentence. No Connect/enrollment/logout/health activation
is requested. Restore usual settings after the resumed session.

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
