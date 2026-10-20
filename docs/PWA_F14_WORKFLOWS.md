# F14 — PWA assistant workflows

Shell **v11**, from `96f3294`. Repository implementation adds attachments, conversation search
and task views. Remote task cancellation remains blocked by absent control authority; the button
stays disabled. No new enrollment, scope, credential, signing, deployment or native dependency work.
Release evidence: [F14 completion](phase-reports/PWA_F14_COMPLETION.md).

## Attachments

Connected Chat accepts up to **four** PNG/JPEG photos, text PDFs or UTF-8 TXT/MD files, each
**1–1,048,576 bytes**. Existing remote body ceiling stays 1 MiB; local CLI/loopback uploads retain
their 5 MiB ceiling. HEIC, archives, Office files, scanned/textless/encrypted PDFs and OCR are not
added. Image interpretation uses only the existing optional local vision adapter; missing vision
remains explicitly unavailable. No image/model download or cloud fallback.

Selection starts an authenticated upload with progress and Cancel/Remove controls. Photo previews
use revocable local Blob URLs, text previews render up to 1,000 characters as text, and PDF previews
show filename/size/type without opening active PDF content. Errors and expiry disable Send until
the file is removed/reselected. Only explicit **Send** commits files to existing Core extraction,
private conversation storage and routing. Selecting/uploading alone starts no model or task.

`POST /api/v1/client/attachments/{32-hex-id}` accepts binary content, an allowlisted Content-Type
and URI-encoded `X-Jarvis-Filename`. Filenames never become paths or query parameters. Cookie
origin/CSRF/scope or signed-session admission precedes collection; final signed body authentication
and identity revalidation precede staging. Uploads require existing `client.chat` and the existing
default-off `JARVIS_ATTACHMENTS_ENABLED` host gate. This release changes no production setting.

Limits: **15 seconds** body collection; browser **20 seconds** including response; **12** upload
starts/device/minute plus existing API limits; **four** live reservations per session, **32** per
process; **128** total bounded staging/tombstone entries, at most **16** per session for admission.
Sources expire after **600 seconds**, swept every **30 seconds**. Capacity includes uploads still
reading. DELETE writes a tombstone, so cancellation can overtake POST. Restart clears staging;
same-device session renewal cannot consume an older session's files.

Chat departure, conversation change, hidden/pagehide, offline, session replacement/expiry and logout
abort uploads, revoke previews, drop selected bytes/text and attempt authenticated discard. Failed
or offline discard leaves only bounded Core memory until expiry (at most 630 seconds from reserve).
Logout also clears server staging when Core acknowledges revocation. No automatic upload retry,
resume, Send or offline queue. Accepted requests retain opaque upload IDs in their immutable
memory-only retry payload; Core's durable request receipt prevents repeated extraction/generation.

After Send, existing private SQLite retention/quota/deletion and isolated parser limits apply.
Migration **018** adds sticky attachment-origin device provenance: only the device owning a PWA
conversation can read its PWA-sourced private history. Trusted-local uploads, including duplicates,
clear that provenance and deny remote history. Email-private/local-only histories remain denied.
Sticky private routing survives source deletion; source text grants no tools, approvals or memory.

## Conversation search and management

`POST /api/v1/client/conversations/search` requires `client.chat`, origin/CSRF or signed identity,
and same-host ownership. Body contains query (1–200 characters) and optional positive `before`
cursor. Search is literal substring matching, ASCII case-insensitive using SQLite `lower`; other
Unicode follows SQLite's exact matching. `%`, `_`, quotes and SQL/FTS-like text remain literal data.
Only Core-attributed user/final-assistant messages from exact device-owned conversations qualify;
local, tool/planning, foreign-device and disallowed private messages are excluded.

Each page contains up to **20** results with at most **320** excerpt characters and an opaque
numeric cursor. Search terms never enter URLs, browser history, IndexedDB, session/local storage,
service-worker cache or a separate search index. Results render as text. New queries abort older
reads; navigation/offline/session/logout discard results. Empty/error/retry states are explicit.
Opening a match loads the history page ending at that message; Refresh history returns to latest.
Pending requests block conversation switching. New/select/search navigation preserve up to **20**
separate memory-only drafts; session replacement/logout erases them. Normal history retains Core
ownership, pagination, retry receipts and explicit New conversation behavior.

## Tasks

Existing `GET /api/v1/client/tasks` adds completed/total step counts and bounded offset pagination
(50 per UI page, API limit 1–100, offset 0–100,000). Pages reflect live ordering; Refresh tasks
rebuilds current listing. `GET /api/v1/client/tasks/{id}` requires `client.tasks.read` and same-host
identity. Details expose objective, state, version/time, step IDs/states/attempts/failure classes
and cancellation-request metadata. Arguments, outputs, grant IDs and provenance are omitted.

Task views show completion/failure/reconciliation states, step progress and explicit stale/error
recovery. Current-session reads reject obsolete selection/logout responses. Foreground Chat checks
every **30 seconds**; a successful authenticated reconnect schedules fresh task reads, and existing
task events trigger refresh. Hiding/offline/navigation cancels detail reads/timers and marks state
stale; no background task execution or model-authorized controls are added.

**External blocker:** `RemoteScope` has `client.tasks.read` only. Scheduler cancellation exists on
trusted host, but no remote task-control scope or authorized mutation adapter exists. Read scope
cannot authorize cancellation. PWA Cancel task stays disabled with trusted-host guidance. No
remote cancel route is installed. Resolving this requires separate owner authorization for a
reviewed remote task-control boundary and enrolled access; this bundle explicitly excludes it.

## Setup and verification

Use existing private HTTPS origin, enrolled device and locked Python environment. No new packages
or client scopes. Host attachment settings and installed local models remain operator-owned;
disabled capability stays unavailable. Shell/service-worker/cache markers advance together to v11.
The service worker still caches only explicit public assets. APIs and private content are excluded.
CSP adds `blob:` only to `img-src` for selected-photo previews; scripts/workers remain same-origin.

Focused commands:

```powershell
rtk proxy node --test tests/pwa/garmin-lifecycle.test.cjs tests/pwa/pcm-worklet.test.cjs
rtk proxy node scripts/pwa-accessibility-check.cjs
rtk proxy uv run python -m pytest --no-cov tests/unit/test_pwa_workflows.py tests/integration/test_pwa_workflows_web.py
rtk uv run python scripts/phase-g-attachments-benchmark.py --enforce
rtk uv run python scripts/phase8c-pwa-benchmark.py --output runtime/mvp4-fixes/f14-transport.json
```

Standards reviewed for progress/abort and temporary previews:
[XMLHttpRequest](https://xhr.spec.whatwg.org/), [File API](https://w3c.github.io/FileAPI/).
All manual phone checks: **skipped by owner; unverified**. Desktop/synthetic tests establish no
physical acceptance or aggregate MVP completion. Native dependency publication hold remains.
