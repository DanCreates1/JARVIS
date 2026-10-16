# PWA M4A — physical accessibility acceptance

Status: `in-progress` — observed phone checks passed; unverified prerequisites and failure cases remain open.
Target: F11 shell `v8`, baseline `34b4010`, implemented 2026-10-14. Ledger below preserves historical v7 observations; no physical v8 result yet.
2026-10-15 F11 acceptance resumed at `4fa75e3`; use the [physical F11 ledger](PWA_F11_PHYSICAL_ACCEPTANCE.md) for new-control/recovery checks and frozen phone performance targets. Existing M4A results below remain unchanged.
Aggregate MVP 4 remains `in-progress`. Preparation and desktop evidence do not accept a phone row.
Use compact phone batches. Results follow actual reported observations; unexecuted checks remain unverified.

## Scope and prerequisites

Run on the owner's physical iPhone, separately in Safari and the existing Home Screen web app.
Use the existing approved private HTTPS origin and existing enrolled identity where present.
**Connect existing device** and public text chat use existing scope; do not issue tickets, erase
keys, revoke devices, change routes, read Garmin, or turn on notifications for this matrix.
Safari and Home Screen may have different identity state: an unenrolled surface can run shell
checks only. Mark its authenticated rows blocked; do not enroll it to satisfy M4A.

Before another **Connect existing device** activation, establish non-health state from the
previously connected surface's **Garmin access needs a new approved browser enrollment.** with
same-identity continuity, or trusted current Core metadata proving every active browser enrollment
has exactly the prior seven scopes and no `client.health.read`. Fresh disconnected startup
shows generic **Connect JARVIS to see Garmin data.**; code sets the new-enrollment guidance only
after Connect, so a fresh startup cannot provide it beforehand. If neither evidence path exists,
mark A3 blocked; do not reconnect to discover scope. A health-enabled identity can automatically
refresh Garmin after the first authenticated event poll, outside this matrix.

2026-10-15 read-only Core inventory: one active browser enrollment, exactly the prior seven scopes,
no health scope, risk ceiling at most 1. Aggregate booleans/count only; no IDs, keys or account
data emitted. This establishes the Core boundary, not phone identity, assets or an A3 pass.

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
Expected source has `app.js?v=8` in `index.html` and `jarvis-shell-v8` in `sw.js`. A host source
check alone cannot prove which cached page the phone loaded. Record phone version verification
method, or mark it unverified. If available, inspect only script URL/cache version using trusted
Safari tooling; do not copy storage, cookies, network bodies or keys. No website-data clearing.
Inspect loaded `/app/app.js?v=8`, loaded `/app/app.css`, active `/app/sw.js?v=8` and
`jarvis-shell-v8` cache name separately for each surface. CSS URL alone does not identify its
content; compare only the public loaded stylesheet against current source.
[WebKit remote inspection](https://webkit.org/web-inspector/enabling-web-inspector/) requires
an iPhone connected to macOS Safari with Web Inspector enabled. This Windows session has no
connected iPhone inspection surface; the repository records no available Mac. Do not enable
debugging/device trust, install a proxy or clear storage merely to close this gate. Host source,
HTTP responses and startup wording remain supporting evidence only. Reference checked 2026-10-13.

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
| Version / device metadata | pending | pending | iPhone 15 Pro/iOS 27.0.1 reported 2026-10-12. Safari v7 HTML guidance observed; Home Screen v7 JavaScript startup fingerprint observed after two reopenings with retained identity. Full script URL/CSS/worker verification open. Safari context then advanced from normal text/zoom to largest accessibility text plus 200% Page Zoom; no external keyboard |
| A1 names / reading order | pass: observed Safari shell | pass: observed updated Home Screen | Safari names/headings/order/unavailable states passed. Updated Home Screen names/headings/order/unavailable states plus Message single-touch sample worked. Earlier Enroll normal-state discrepancy belonged to unverified prior assets; no failure inferred. Full assets gate open |
| A2 persistent error / recovery | pending | blocked: existing identity | Home Screen retained key confirmed; invalid-ticket test excluded to preserve it. Safari identity/script execution unverified; no invalid-ticket activation performed |
| A3 busy / disabled focus | pending: Safari identity unverified | pass: existing non-health identity | 2026-10-13 updated Home Screen VoiceOver: one Connect, usable busy/ready focus, Message/Send unavailable until readiness, no repeated connection speech over 30 seconds; owner reports all worked. Oct12 plain connection failure/recovery was not this acceptance |
| A4 completed speech / earlier reading | pending: Safari identity unverified | pass: observed public reply | 2026-10-13 Home Screen: public fixture sent once with VoiceOver; earlier prompt/line reading usable during streaming, no repeated delta interruption, completion spoken once. Owner reports ALL WORKED; no transcript retained |
| A5 selection / Jump to latest | pending: Safari identity unverified | pass: observed public replies | Home Screen: further public fixture, earlier reply selection/reading usable during arrivals, named Jump to latest reaches latest and usable Conversation focus; owner reports pass. No uncertain replay or transcript retained |
| A6 spoken failure / draft | pending | pending | No ordinary failure occurred in the accepted VoiceOver batches. Earlier plain connection failure had no observed spoken recovery/draft evidence |
| A7 largest text | pass: observed Safari layout | pass: observed Home Screen layout | 2026-10-13 actual webpage text grew on both surfaces at largest accessibility text; readable/reachable controls in both orientations. Safari first observed growth before 200% website zoom; Home Screen confirmed in visual finish batch |
| A8 website zoom / magnification | pending: maximum numeric value unreported; observed mechanisms passed | pass: observed pinch/iOS Zoom | Safari 200% and highest offered Page Zoom, pinch/pan, then separate iOS Full Screen Zoom worked. Highest website value and screen magnification level unreported. Home Screen pinch/pan and separate iOS Full Screen Zoom worked; no Safari Page Menu assumed. Usual text/website zoom restored before screen Zoom; final batch reports all worked, including settings restoration |
| A9 rotation / keyboard / safe areas | pass: empty ticket field | pass: authenticated Message field | Both orientations at largest text: software keyboard show/dismiss, caret/field/control reachability and no reported clipping/trap. Safari at 200% website zoom used empty ticket field; authenticated Safari Message keyboard not tested. Home Screen Message caret and Send scroll-reachable |
| A10 external keyboard | blocked: no external keyboard | blocked: no external keyboard | Owner confirmed no keyboard available 2026-10-13; no keyboard acceptance inferred |
| A11 reduced motion / touch | pass: observed shell and empty-ticket touch | pass: observed safe target activation | Reduce Motion reload/reopen: no panel entrance motion; distinguishable/reachable controls at largest text. Home Screen ordinary and VoiceOver Refresh tasks each updated intended panel. Safari ordinary/VoiceOver empty-ticket touch worked. Enrollment/logout/Garmin targets inspected only, never activated |
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

Owner subsequently confirmed **both messages match**: non-health Garmin guidance was observed
on the original Home Screen surface before two online close/reopenings, then **Enrolled key found.
Connect existing device to start a fresh session.** appeared. The exact startup sentence is emitted
by v7 JavaScript after local identity load, absent in v6; this supports updated HTML/JavaScript and
retained identity. It is not direct script-URL/CSS/cache-name verification or a fresh Core scope
inventory. Startup wording alone does not prove health scope; the preceding non-health guidance
and same-identity continuity support one existing non-health Connect within the owner's standing
M4A authority. The current batch
asks Home Screen VoiceOver headings/names/order/unavailable states, one Connect, usable busy/ready
focus and 30 seconds without repeated steady-state speech. No enrollment/logout/health action.

Owner reported **all worked** for that Home Screen connection batch. This accepts A3's observed
busy/ready focus, authenticated Message/Send gating and 30-second steady connection speech.
Updated headings/names/order/unavailable states are also reported; an explicit Message single-
touch sample is requested in the next public-chat batch to complete A1 touch evidence. A4 now
asks one bounded public fixture, earlier reading during streaming, no repeated delta interruption
and one spoken completion. If the reply finishes too quickly, record that limitation rather than
accepting unobserved streaming behavior. No uncertain-submission replay requested.

Owner reported **ALL WORKED** for the Home Screen public-chat batch: Message single-touch then
activation, one public fixture submission, earlier reading during streamed arrivals without
repeated interruption or forced loss of position, and completion spoken once. This closes bounded
Home Screen A1 touch evidence and A4. No transcript recorded. A5 now asks one further confirmed
public-fixture submission, selection/earlier-reading retention during arrivals and named Jump to
latest returning usable Conversation history focus. A reply ending too quickly remains a limitation.

Owner reported **pass pass keep goin** for the Home Screen history batch. This accepts bounded A5
selection/earlier-reading retention during a further public reply and named Jump to latest content/
focus. Current visual batch asks Reduce Motion, largest-text Home Screen layout in both orientations,
Message keyboard/caret/Send reachability, pinch magnification, ordinary/VoiceOver Refresh tasks
target activation, and Safari highest offered Page Zoom/pinch/empty-ticket touch. Each observed
surface/mechanism remains independent. No enrollment/logout/Garmin/notification action requested.

2026-10-13 visual finish: owner reported **all worked** for the requested batch. Home Screen
webpage text enlarged at largest accessibility size, controls remained readable/separate in both
orientations, and authenticated Message keyboard/caret/Send remained scroll-reachable. Reduce
Motion suppressed panel entrance motion; ordinary and VoiceOver Refresh tasks each reached the
intended panel. Home Screen pinch/pan worked. Safari highest offered Page Zoom, pinch/pan,
ordinary/VoiceOver empty-ticket touch and Reduce Motion reload worked. This accepts bounded
Home Screen A7/A9 and both surfaces' A11; no protected Safari activation was tested. The requested
numeric maximum website zoom was not supplied.

Final evidence checkpoint recorded `2026-10-13T21:35:15-04:00`; this timestamps documentation,
not each phone action. In the separate magnification/restoration batch, owner reported
**all worked**. With VoiceOver off
and usual text/website zoom restored first, iOS Full Screen Zoom reading, control reachability and
three-finger panning worked on Safari and Home Screen. The batch included restoration of usual
Zoom, text size, Safari Page Zoom, Reduce Motion and VoiceOver; owner's aggregate response covers
that step, without separately reported setting values. Screen magnification level and Safari's
maximum website zoom percentage remain unreported. Home Screen A8's available mechanisms pass;
Safari A8 keeps the numeric-value documentation limit. These observations do not accept layout
reflow or a numeric browser 400% gate. No more phone questions queued this session.

2026-10-13 resumption at `114ab9a`: the existing Core was already running and was reused.
Sanitized readiness confirms one Python-owned `127.0.0.1:8765` listener, no non-loopback Core
listener, exact owned private route/backend/origin, online tailnet and disabled Funnel. Both
loopback and private shell/script/worker return HTTP 200 with host v7 shell/worker references.
This accepts service readiness only; no phone asset, identity, speech or M3C result is inferred.
Fresh supporting checks pass 43 lifecycle tests and 24 desktop geometry cases on Edge
155.0.4283.45. Existing phone results and open rows remain unchanged.

The next compact owner batch requests the Safari access-status sentence after an online reload,
highest offered Page Zoom percentage and current external-keyboard availability. No protected
activation is requested. Await observations before choosing A2 or authenticated Safari steps.
Safari's initial HTML sentence alone cannot prove JavaScript execution or absence of a key.
A2 stays blocked on Home Screen by its retained identity. A6 remains pending unless an ordinary
failure is actually observed with VoiceOver; do not replay an uncertain send or force a separate
M3C interruption solely for this row. No new phone outcome is recorded by this resumption.

## Closure and resumption

2026-10-14 v8 supporting revalidation: all 24 desktop geometry cases pass. Separate native Edge
155.0.4283.45 400% page zoom passes (`innerWidth` 1280 at 100%, 320 at 400%; root scroll width 316).
Fourteen controls are pointer-reachable; new conversation/history/cancel controls are keyboard-
reachable. Reading/selection retention and mocked Send pass. Synthetic static shell only; no v8
physical-device, spoken-screen-reader, authenticated Core or Garmin result is inferred.

M4A physical acceptance requires dated actual-device evidence for applicable rows, verified
current phone assets, resolution/retest of critical failures, and explicit pending limitations.
Absent identity/equipment or a required browser feature leaves the relevant gate open. No health
scope or enrollment is required for shell-only work. Run focused tests after any fix and applicable
release/security gates before publication. Record outcomes in
[MVP 4 progress](phase-reports/PWA_MVP4_PROGRESS.md); keep this ledger synchronized.

F11 now implements Cancel reply, Retry request and bounded Core-backed saved history in shell v8.
Automated regressions do not accept physical cancellation/retry/reload/restart soak or speech for
the new controls. Recheck A1 names/order/focus for Saved conversations, New conversation, Refresh
history, Load earlier messages, Cancel reply and Retry request when applicable. Historical v7
passes above remain historical. Startup/navigation/first-delta/memory performance thresholds must
be frozen before actual phone measurement; no physical performance result is claimed.
M3C remains separate. Native candidates were repaired locally on 2026-10-14 and retain an upstream
dependency-audit publication hold; see the current MVP 4 report.
