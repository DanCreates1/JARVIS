# F15 — daily-use workspace and reliability

Shell **v12**, from verified F14 checkpoint `29fe496`. Core remains sole owner of authentication,
history, routing, permissions, task execution and audit. No dependency, scope, enrollment,
production-control, network exposure or native-package change. All examples/tests use synthetic data.

## Conversation library

Accessible cards replace the recent-conversation selector. Each page contains at most **20**
exact host/device-owned conversations, an **80-character** title, **240-character** excerpt and
Core updated timestamp. Pinned items sort first, then updated time and ID descending. Active and
archived history have separate views. Archive changes metadata only; history remains readable and
searchable. There is no permanent deletion control.

Default titles use the first locally read, Core-attributed user message. No title-generation model
call occurs. Local/tool/unattributed message text never supplies titles or excerpts. Existing
attachment-origin and email-private denials apply to listing, search, history, metadata and reuse.
Legacy unowned conversations are not backfilled.

Migration **019** adds title/pin/archive/revision fields to existing ownership rows, per-device
library revisions, content-free attachment/request relationships and per-host task-list revisions.
Optimistic metadata writes compare the exact conversation revision under `BEGIN IMMEDIATE`.
Listing reads revision and page in one SQLite snapshot. Concurrent edits/pagination changes return
409; UI retains unsaved title input and requests explicit refresh/review, never overwrites or retries.

## Structured replies

The dependency-free renderer supports paragraphs, headings, lists, emphasis, fenced code,
blockquotes and tables. Existing `[source:ID](<https://…>)`, `[source:ID]`,
`[attachment:ID#chunk:N]` and image markers receive readable labels. Labels identify references;
they do not establish verification, ownership, permission or execution authority.

Only fixed DOM elements and text nodes are constructed. No HTML parser, executable content,
remote media, syntax highlighter, embed, source lookup or automatic fetch. Links require explicit
activation and absolute HTTP(S) without credentials; they open with `noopener noreferrer` and no
referrer. Other schemes, malformed links and image syntax remain readable text. Raw HTML stays text.

Per reply: **100,000 characters** retained; only first **32,000** receive Markdown parsing,
remainder stays plain text; **1,200 constructed nodes**, **4 inline levels**, **40 links**,
**12 fenced blocks**, **16,000-character copyable code blocks**, **12 columns / 50 table rows**.
Unfinished fences or budget exhaustion preserve readable plain text. Copy response/code require
explicit buttons; accessible status reports success or device-copy fallback after failure.

Streaming appends to existing text nodes. Final formatting/canonical replacement defers while
history text is selected or reply controls hold focus. Formatting preserves scroll intent and
never moves keyboard focus. History display retains at most **200 rows / 512,000 characters**,
protecting selected/focused rows; oversized old display windows are recoverable from Core.
Structured display falls back to plain text once the shared formatted-node budget is reached.
Search display caps at **100** matches; refine query for more. No Core history is removed.

## Attachment lifecycle

Uploads remain **four combined staged/reused files**, **1 MiB/file**, **10-minute staging**.
Uploading and staged mean unprocessed Core memory. Explicit Send alone commits existing private
processing. Core metadata reports processing, ready, failed, expired or unavailable; no raw bytes,
images, chunks or digest are returned by the metadata adapter. It performs no cleanup or processing.

Conversation metadata is paginated **20/page**, with up to **four recent persisted request IDs**
per attachment. Message source hints use those relationships only. Old F14 attachments without
request links remain conversation-associated; no historical message relationship is invented.
Content-free links retain unavailable-reference evidence after ordinary host retention cleanup.
Processing older than the existing 60-second lease is displayed as interrupted, without restarting it.

Ready files may be deliberately selected for reuse only in their authorized conversation. Core
validates exact conversation/host/device ownership, ready state and expiry before provider work;
attachment IDs join the immutable request fingerprint. Replay does not parse or generate again.
Existing source integrity checks, sticky private routing, quotas, cancellation and provider authority
remain canonical. Metadata source content cannot grant actions. No download endpoint, cloud OCR,
model download, automatic upload resume or silent reprocessing exists.

UI explains parser rejection/timeout/interruption, expired/unavailable references, capacity and
unavailable local vision. After an accepted request fails asynchronously, the original draft is
restored only if composer is empty; newer typing survives. In-session reuse selections follow their
conversation. Staged previews/uploads are cancelled/discarded on existing lifecycle boundaries;
session replacement/logout erase all private selections, drafts and metadata.

## Task monitoring and recovery

Existing `client.tasks.read` permits read-only status and sanitized events. Task lists show **50/page**,
status filters (including steps verifying), newest/oldest updated sorting and stable selected task.
Page revisions detect concurrent changes; refresh restarts pagination. Current-page refresh and
reconnect preserve selected task and an explicitly selected earlier timeline window.

Timeline shows latest **50** Core events or an explicit earlier page, oldest-to-newest within page.
Only sequence, timestamp, event/status/node identifiers and fixed safe explanations cross this
adapter. Arbitrary reason strings, arguments, results, grants and private execution payloads do not.
Step attempts/progress/failure classes and fixed explanations remain Core-authored. Event gaps,
lost subscriptions and restart recover persisted state through existing authenticated read paths.

Task creation/execution/approval/remote cancellation remain absent or disabled. **F14 blocker stays:**
`client.tasks.read` does not authorize cancellation. Task schema has no trustworthy persisted
conversation relationship, so F15 adds no inferred conversation correlation or authority.

## API additions

All paths below are under `/api/v1`, with existing origin/session/scope/CSRF/body/rate controls,
host checks and `no-store` responses. Titles/search text travel only in request bodies.

| Method/path | Contract |
| --- | --- |
| `POST /client/conversations/library` | `archived`, bounded `offset`, optional `revision`; returns cards, revision and next-page state. Existing `GET /client/conversations` also returns first active page and active request. |
| `POST /client/conversations/{id}/metadata` | Complete `revision`, nullable `title`, `pinned`, `archived`; exact owned optimistic mutation under existing `client.chat`. |
| `GET /client/conversations/{id}/attachments?offset=N` | Bounded metadata, processing/recovery states, availability and provenance; no raw file adapter. History includes first metadata page within existing 128 KiB response ceiling. |
| `POST /client/chat` | Optional ready same-conversation `attachment_ids` alongside existing `upload_ids`; combined maximum four unique selections. |
| `GET /client/tasks?status=S&sort=newest\|oldest&offset=N&revision=R` | Existing list projection; `X-Jarvis-Task-Revision` guards pagination. `verifying` filters runtime node state. |
| `GET /client/tasks/{id}/events?limit=50&before=N` | Exact host-owned bounded sanitized timeline. Task detail includes latest timeline. |

## Composer and operational limits

Enter remains multiline editing. Send or Ctrl/⌘+Enter submits deliberately; IME composition,
composition keycode 229 and repeated shortcut events cannot Send. Twenty nonempty conversation
drafts fit in session memory; exceeding capacity blocks switching with guidance, preserving current
text instead of silently evicting it. Completed-send drafts cannot reappear as a new-conversation draft.

Browser persistence remains identity key plus content-free request marker/cursor/subscription
references only. No transcript, title, query, attachment, task payload or draft enters URLs, browser
persistence, service-worker caches or logs. Offline actions never queue. Existing-key reconnect and
uncertain-request retry remain deliberate and receipt-based.

Manual phone checks: **skipped by owner; unverified**. Desktop automation does not establish physical
Safari/VoiceOver performance, native acceptance or aggregate MVP completion. Native manifests and
their existing dependency publication hold remain unchanged and excluded. $0/default-off controls stay.

Standards checked: [DOM textContent](https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent),
[composition events](https://developer.mozilla.org/en-US/docs/Web/API/Element/compositionstart_event),
[SQLite transactions](https://www.sqlite.org/lang_transaction.html).
