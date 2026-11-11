# Phase 15 provider and authentication decision

Status: selection pending, 2026-10-31. No live access or provider adapter enabled.
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
operations. Final commands depend on selected auth adapter; do not claim unimplemented controls.
Provider-side revocation/token replacement requires applicable consequential authority. No email
scope authorizes calendar, Windows effects, remote clients or third-party messages.
