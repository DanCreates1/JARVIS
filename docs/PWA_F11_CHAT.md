# F11: Core-owned phone chat

Implemented 2026-10-14 in Home Screen PWA shell **v8**. Physical-iPhone F11 soak is pending.
Core remains authoritative for authentication, scopes, permissions, routing, transcript and audit.
Native signing remains deferred under the $0/no-Mac constraint.

F12 carries these contracts into shell **v9** with Chat / Garmin / Settings navigation. Conversation
and task controls live in Chat; enrollment/connect/logout live in Settings. Shared session,
conversation, pending request and stream ownership survive view changes. See [F12](PWA_F12_NAVIGATION.md).
Remaining physical checks are **skipped by owner; unverified**; v8 evidence below remains historical.

## Phone behavior

Connect existing device restores its owned conversation from Core before enabling Send, followed
by a successful authenticated event poll. Saved conversations selects recent Core conversations;
New conversation starts a fresh one on the next accepted Send. Load earlier messages reads older
bounded pages. The phone never caches API responses or stores transcript/draft text.

Cancel reply stops the Core task and propagates cancellation to the provider. Once POST starts,
generation cancellation is confirmed from Core. An unsent request can be cancelled locally before
POST. If the acknowledgement is lost, Retry request checks the existing
request and retries cancellation. Cancellation before local marker commit skips POST; cancellation
arriving before Core accepts POST records a durable cancellation barrier.

Retry request is explicit. It reads Core status first, then only resubmits an unaccepted request
using its original immutable request ID, message and conversation. It can attach a renewed session's
owned subscription to accepted work without starting another generation. Completed, failed,
cancelled or interrupted requests never generate again under that ID. Interrupted Core-restart
outcomes remain explicit; a new user instruction is a new request.

The only extra IndexedDB record is `{deviceId, request_id}` under `chat-request`. Its transaction
must commit before chat POST. It allows reload to check uncertain outcomes without storing text.
If Core has no accepted request and the page no longer has its draft, Core closes that ID before
the UI permits re-entry. A delayed original POST cannot then generate after a new submission.
Logout waits pending storage writes, erases this record and clears displayed private state.

## Contract

All paths below are under `/api/v1`; the existing `client.chat` scope authorizes these phone-chat
operations. Browser Origin, session, CSRF for POST, host/device binding, rate and body controls
remain enforced. No scope expansion, ticket or enrollment is required for F11.

| Method/path | Contract |
| --- | --- |
| `POST /client/chat` | Existing input: `request_id`, current owned `subscription_id`, `message`, original nullable `conversation_id`, optional existing model/reasoning fields. Returns 202 running or 200 terminal. |
| `GET /client/chat/{request_id}` | Exact device-owned durable outcome; 404 unknown. Optional `subscription_id` validates and attaches the current owned chat subscription to running work. |
| `POST /client/chat/{request_id}/cancel` | Stops running work; repeats return the same terminal outcome. Unknown IDs receive a durable cancellation barrier. A 202 running response means cleanup is not yet confirmed. |
| `GET /client/conversations` | `{conversations:[{id,updated_at}],active_request}`; newest 20 exact device-owned conversations. |
| `GET /client/conversations/{id}/messages?limit=50&before=sequence` | `{conversation_id,messages,requests,has_more,next_before}`. Newest page or preceding page, each chronological; only phone-authored visible user/assistant text. |

Request envelopes contain `request_id`, nullable `conversation_id`, `status`, nullable `reply`,
nullable safe `error`, and optional `reply_truncated`. Status is `running`, `completed`, `failed`,
`cancelled` or `interrupted`. Messages carry `id`, `sequence`, `role`, `content`, `request_id` and
optional `truncated`. HTTP/history responses cap at 128KiB; oversized text is explicitly excerpted.
Terminal SSE payloads carry an authoritative reply within the event ceiling. Status/history repair
missing terminal frames and deltas; speech is deduplicated by request ID.

## Isolation and recovery

Durable request fingerprint covers message, original conversation, model role and reasoning;
subscription changes do not change that fingerprint. Changed payload reuse conflicts. Core reserves
before starting background generation. One turn per device, 64 per process and a 300-second deadline
bound execution. The generation outlives an HTTP acknowledgement or obsolete subscription, while
Core continues to revalidate session authority. Logout/expiry/revocation cancels bound work.

Core restart marks unresolved receipts interrupted and never guesses that they are safe to rerun.
Deleting conversation content preserves a content-free no-replay receipt. History rejects foreign,
unowned and local private conversations; local CLI/tool/email/attachment additions cannot silently
become phone history. Pre-F11 conversations have no provable device owner and are not backfilled.

The 2026-10-15 phone continuation exposed an early already-applied migration 017 with neither
sequence column nor the deletion trigger. Chat-store startup now repairs those known omissions
inside one transaction, without rewriting migration 017 or replacing existing rows. Named insert
columns support both original and appended column order. Historical sequence bounds stay unknown
(0/null); exact ownership and `client_request_id` still govern visible history. Cancelled repair
rolls back; normal Core recovery still interrupts unresolved work and preserves no-replay receipts.
This uses SQLite's [ADD COLUMN](https://www.sqlite.org/lang_altertable.html#altertabaddcol)
and [transaction](https://www.sqlite.org/lang_transaction.html) behavior; no website-data clearing
or phone re-enrollment is required.

The browser guards response/body continuations by session and CSRF, histories by selection
generation, and events by the current request/conversation. One stream owner survives ordinary
offline recovery; cancelled queued Web Locks cannot acquire an obsolete owner. New conversation
ignores delayed frames from a previously viewed request.

## Verification and open gates

Physical procedure, independent result ledger and frozen phone performance targets:
[F11 physical acceptance](PWA_F11_PHYSICAL_ACCEPTANCE.md), initiated 2026-10-15 at `4fa75e3`.
No new phone result is implied by preparation.

Synthetic Core/provider, API/security, real-script lifecycle and desktop geometry checks are
recorded in [MVP 4 progress](phase-reports/PWA_MVP4_PROGRESS.md). They contain no real account,
transcript or health data. M3C Garmin acceptance remains in its separate report. Physical v8
cancel/retry/reload/Core-restart/network soak, new-control VoiceOver/focus and measured phone
performance remain pending; existing v7 observations are historical evidence only.

Standards checked: [Fetch cancellation](https://fetch.spec.whatwg.org/#abort-fetch),
[IndexedDB transaction lifetime](https://www.w3.org/TR/IndexedDB/#transaction-lifetime),
[Web Locks](https://www.w3.org/TR/web-locks/#api-lock-manager), and
[Python task cancellation](https://docs.python.org/3.11/library/asyncio-task.html#task-cancellation).
Client fetch cancellation alone cannot establish whether Core accepted a request; the durable
receipt/cancellation barrier resolves that boundary.
