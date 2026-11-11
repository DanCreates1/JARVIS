# Phase 15 provider and authentication decision

Status: personal Gmail selected, 2026-11-01. Desktop delegated OAuth with PKCE and
`https://www.googleapis.com/auth/gmail.readonly` selected. Exact account/client registration and
consequential setup/read review remain pending. Owner confirmed no project/client exists.
Protected auth/configuration are implemented; no live access or production adapter enabled.
[Current progress](phase-reports/current/PHASE_15_PROGRESS.md) freezes scope and acceptance.

## Choices reviewed

| Mailbox | Proposed auth path | Minimum read scope for body summaries | Setup input |
| --- | --- | --- | --- |
| Gmail / Google Workspace | Desktop OAuth authorization code with PKCE and loopback callback; system browser; protected host token storage | `https://www.googleapis.com/auth/gmail.readonly` | Owner-selected personal/Workspace account type and existing or separately authorized desktop OAuth client/project |
| Outlook.com / Microsoft 365 | Public desktop client, delegated authorization code with PKCE; supported Microsoft authentication library; protected host token storage | `https://graph.microsoft.com/Mail.Read` | Owner-selected personal/work-school account type, tenant policy and existing or separately authorized client registration |
| Local exports | Existing explicit absolute local `.eml` directory | None | Explicit source path; this retains local functionality but does not satisfy live-provider exit |

These are alternatives, not activated settings. An account already connected to this chat does
not establish account choice or grant JARVIS independent credential access. Do not inspect private
mail or profiles merely to resolve provider selection. Never request passwords, tokens or secret
client files in chat. Selecting a path does not approve new credentials/scopes or live reads.

Google's metadata scope excludes bodies. `gmail.readonly` is restricted; verification/security
assessment applicability must be checked against the actual personal/internal/distributed use,
data routing and publishing status before setup. No paid assessment, public distribution or
verification claim follows from this proposal. References: [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[Workspace data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy).

Microsoft basic-mail permissions exclude body/attachments; delegated `Mail.Read` supports body
reading for the signed-in account. Tenant policy can still require administrator approval. Exclude
application-wide and shared-mail scopes, `Mail.ReadWrite` and `Mail.Send`. Request refresh access
only if selected and approved as part of the concrete auth review. References:
[permissions](https://learn.microsoft.com/en-us/graph/permissions-reference#mailread),
[authorization code/PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow),
[message API](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0),
[API terms](https://learn.microsoft.com/en-us/legal/microsoft-apis/terms-of-use).

## Concrete review after selection

### Selected Gmail contract — frozen 2026-11-01 before implementation

Owner selected personal Gmail; do not infer the connected chat account. A local account alias,
exact mailbox address and owner-controlled Desktop OAuth client must be supplied locally before
activation. Application data remains on Windows. System-browser authorization code + S256 PKCE,
random state, an ephemeral IPv4 loopback callback, and protected per-user Windows token storage
are the selected auth design; no embedded browser, service account or application-wide delegation.
Only the selected read scope is allowed. Refresh access needs concrete review; no automatic login,
scope expansion, token replacement, account switching or fallback to exports.

First implementation milestone: inactive read adapter behind `EmailReadProvider`, injected
host-only token source, synthetic transport and lifecycle tests. No production credential loading,
OAuth flow, startup wiring or network-enabled CLI is added by that milestone. The token source is
not a model/client port. That first milestone is complete. The subsequent protected auth/configuration
milestone is implemented with synthetic acceptance; [setup and approval proposal](GMAIL_SETUP.md)
records exact bounds, Windows retention, commands and remaining actual Google/live acceptance.

Frozen request/response limits (all total deadlines include token acquisition and parsing):

| Operation | Allowed requests | Deadline | Decoded HTTP response cap |
| --- | --- | --- | --- |
| List | `users/me/profile`, then one `threads.list` page, `maxResults=100`; no pagination | 5 s total | 16 KiB profile; 32 KiB list |
| Selected thread | Profile; minimal thread inventory; at most 16 `messages.get(format=raw)`; final minimal inventory | 30 s total; 5 s/request | 16 KiB each inventory; 192 KiB each raw envelope; 16 KiB profile; <=3,194,880 bytes total |

The production-auth extension was frozen in the progress report before auth implementation:
at most one additional token POST (5 s, 16 KiB) when an existing access token needs renewal.
Original total operation deadlines and Gmail GET bounds above remain unchanged. Including renewal,
list is <=3 requests/65,536 response bytes and a maximum-sized thread <=20 requests/3,211,264 bytes.
Initial explicit OAuth is <=180 s with one token POST and one profile GET, no mail body read.
The prepared first live proof lowers inventory capacity to three messages and acquires no raw
message from a larger thread. [Exact auth/storage/callback controls](GMAIL_SETUP.md).

Thread inventory must contain 1–16 distinct message IDs, matching thread IDs and history versions.
All raw responses must match that inventory; final inventory/history must remain identical.
Reject changed, incomplete, duplicate or over-limit threads; never silently summarize a subset.
The inventory check detects observed changes, not a provider transaction or verified chronology.
Every MIME message remains <=128 KiB and passes the existing isolated text-only parser. No
attachment endpoint, HTML rendering, remote-resource fetching, provider draft, write or send API.
Raw MIME can contain inert attachment bytes inside the same message bound.

Allowed data origin is exactly `https://gmail.googleapis.com`; implemented token exchange uses
exactly `https://oauth2.googleapis.com/token`. API transport disables ambient proxies,
redirects, cookie persistence and automatic retries. Only adapter-built GET paths/queries are used.
401/403, 429, 5xx, malformed JSON, timeout, unavailable transport and limits yield fixed errors
without private content. Cancellation closes responses and drains parser work. Disable invalidates
in-flight operations even across disable/re-enable. No mailbox data or raw provider error is logged.

Profile address must exactly match configured normalized personal `@gmail.com` address before
mail requests. No dot/plus/alias equivalence guessing. Token source also binds that exact account
and the exact read scope.
Bearer tokens are ASCII and at most 8,192 characters including padding; malformed/expired tokens
are denied before any profile request. Token-source error details are never propagated.
Provider IDs are opaque bounded ASCII (1–28 letters/digits/`_`/`-`); unsupported IDs fail closed.
Canonical IDs encode an account fingerprint, thread/message kind and
reversible base32 provider ID, within existing export ID validation. Export ID rules stay unchanged.
Digests identify observed MIME bytes; headers/dates remain unverified and IDs grant no authority.

Official sources reviewed 2026-11-01: [desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[profile](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile),
[thread listing](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/list),
[thread read](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/get),
[message read](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get),
[message/raw schema](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages),
[Workspace data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy),
[API user-data policy](https://developers.google.com/terms/api-services-user-data-policy).
[Google APIs terms](https://developers.google.com/terms) were also reviewed before any live use;
owner-specific project/consent requirements remain pending, and no acceptance is performed here.
Local private summaries must remain user-facing and must not train general models. Restricted-scope
personal-use/testing exceptions, consent-screen publishing state and token lifetime require review
against the actual client project; no public verification, paid assessment or terms acceptance is
claimed. This implementation milestone does not accept terms or activate access.

Record selected provider/account type, client-registration ownership, exact scopes/refresh policy,
protected credential location, fixed allowed API origins, account-binding strategy and bounded
read requests. Review selected provider API/terms in detail before implementation; this alternatives
review is not final approval or terms acceptance. Prepare synthetic adapter/lifecycle evidence
before requesting any consequential setup/access approval. Reuse existing exact authority when
present; do not renew routine permissions.

Proposed first live proof: one deliberately selected thread containing at most three messages,
each at most 128 KiB; reject a larger thread rather than silently truncate it. Bounded read/summary
plus owner-authored volatile draft. Raw email stays local and
out of committed evidence. OAuth permission may cover the mailbox even when application reads
are narrower; disclose that scope clearly before consent. No mutation/provider drafts/send.

## Retention and revocation boundary

No raw mailbox cache, persisted MIME, background polling or provider data in diagnostics. Parsed
selected text/projection is volatile. Private model replies follow canonical conversation retention;
sticky privacy survives removal/disable/restart. No cloud/research/memory promotion from mail.

Disable stops new acquisition and invalidates in-flight results; existing history remains private.
Expired/revoked credentials fail closed without login, account switching or scope expansion.
Disconnect, local token erasure, provider grant revocation and conversation deletion are separate
operations. [Current commands](GMAIL_SETUP.md#disable-disconnect-and-recovery) implement explicit
local disconnect; Google revocation remains a separate owner action.
Provider-side revocation/token replacement requires applicable consequential authority. No email
scope authorizes calendar, Windows effects, remote clients or third-party messages.
