# Phase 15 Gmail setup and activation

Status, **2026-11-10**: approved Google project/Desktop-client setup and actual protected Gmail
authorization succeeded. Client registration remains outside the checkout; refresh grant resides
in Windows Credential Manager. Production configuration remains off. Selected-source live
read/preparation passed with one message, verified provenance and an unsent/unstored synthetic
draft in 805.831 ms. The earlier oversized conversation remains a documented rejection; limits
were not changed. Current release/documentation closeout remains pending. See current evidence in
[Phase 15 progress](phase-reports/current/PHASE_15_PROGRESS.md).

The setup instructions below remain the operator contract. Earlier absence of a project/client
was confirmed on 2026-11-01 and is superseded by this actual authorization checkpoint.

## Prepared setup decision

Proposed project display name: **JARVIS Personal Email**. Owner-controlled personal project,
Gmail API only, one **Desktop app** OAuth client named **JARVIS Windows Core**. Personal Gmail
uses External audience with Testing status and only the selected owner as test user. No public
publishing, billing linkage, paid assessment, deployment or other API/scope is part of this plan.
If the console requires billing or a new unreviewed commitment, stop for a concrete owner decision.
The owner must review applicable Google terms/data-policy setup and identify the exact account;
project creation and consent require the consequential-action approval in root instructions.
See [Google setup](https://developers.google.com/workspace/gmail/api/quickstart/python),
[consent configuration](https://developers.google.com/workspace/guides/configure-oauth-consent),
[API terms](https://developers.google.com/terms) and
[data policy](https://developers.google.com/terms/api-services-user-data-policy).

Request only `https://www.googleapis.com/auth/gmail.readonly`, with offline renewal. This grant
can read the mailbox even though JARVIS foreground operations are narrower. It grants no write,
provider draft, send, calendar or remote-client capability. Restricted-scope verification/testing
requirements and token lifetime must be checked against the actual project before activation;
this personal testing plan is not public verification. Never bypass a Google denial or warning
without reviewing its actual cause. [Scope classification](https://developers.google.com/workspace/gmail/api/auth/scopes).

Google's External/Testing refresh grants for Gmail expire after **7 days**. Expiration stops
reads; JARVIS does not silently obtain a new grant. A successful bounded proof therefore does
not establish indefinite unattended access. Any later change to the project's publishing or
access-duration configuration requires review of that actual change and its applicable authority.
[Google refresh-token lifetime](https://developers.google.com/identity/protocols/oauth2#expiration).

## Local client and consent

After approved project/client setup, save the downloaded Desktop JSON **outside this checkout**,
for example under the Windows user's private application-data directory. Do not paste its contents,
tokens, passwords or browser callback URLs into chat. The explicit local file is bounded to 16 KiB;
network paths, symlinks, reparse points and hardlinked files are denied. Only the installed-app
schema and allowlisted Google OAuth metadata are accepted. Google's documented legacy metadata
URLs are recognized; runtime authorization/token requests still use the fixed current URLs,
never URLs selected by the file. [Client-file format](https://developers.google.com/api-client-library/dotnet/guide/aaa_client_secrets).
The downloaded registration
file remains owner-managed; it contains the Desktop client secret and must remain private.

Commands below are templates, not evidence that setup or consent happened. Replace placeholders
locally. The exact lowercase personal mailbox is required; no dot/plus alias equivalence is inferred.

```powershell
rtk proxy uv run --locked jarvis email gmail-auth --account "<exact-lowercase-mailbox@gmail.com>" --client-file "<absolute-private-desktop-client.json>"
```

The local default-No confirmation describes mailbox-wide read scope and offline access. One
system-browser consent flow uses S256 PKCE/random state and an ephemeral IPv4 loopback callback.
Total deadline is 180 s, at most eight callback requests/four active handlers, 8 KiB headers and
2 s/header. Successful consent performs one bounded token POST and an exact-account profile check,
then creates a new per-user **Windows Credential Manager** entry. Existing entries are refused;
this command never replaces a token automatically. It reads no thread/body and enables no feature.
[Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app).

Credential targets use an account/client fingerprint. The protected entry stores exact account,
client ID, scope and refresh token only, <=2,560 serialized bytes, refresh token <=2,048 ASCII
characters. Access tokens stay in process memory. Persistence is Windows `CRED_PERSIST_LOCAL_MACHINE`
for this user/host, without roaming or plaintext fallback. Same-user processes/administrators and
a compromised Windows account remain outside this protection boundary. No credential enumeration
occurs. [Windows credential writes](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew).

## Foreground activation and bounded acceptance

Set only in the intended trusted-local process; this task does not write production dotenv files:

```powershell
$env:JARVIS_RUNTIME_PROFILE="private-email"
$env:JARVIS_EMAIL_ENABLED="true"
$env:JARVIS_EMAIL_PROVIDER="gmail"
$env:JARVIS_EMAIL_GMAIL_ACCOUNT="<exact-lowercase-mailbox@gmail.com>"
$env:JARVIS_EMAIL_GMAIL_CLIENT_FILE="<absolute-private-desktop-client.json>"
rtk proxy uv run --locked jarvis email list
```

Do not also configure `JARVIS_EMAIL_EXPORT_ROOT` for Gmail. Provider choice never falls back to
exports/another account. `private-email` keeps cloud, automatic research, other integrations,
actions and background execution disabled. Existing text profiles continue denying email.
Startup constructs a lazy source without opening the client file, reading a token or making a
network call. Only explicit foreground acquisition uses protected credentials. Normal same-account
renewal is at most one 5 s/16 KiB token POST per operation, no retries; it stays within the existing
5 s list/30 s thread deadline. Granted scopes must match exactly. Rotation to a different refresh
token is refused; expiry/revocation never opens login or changes account/scope. No raw mailbox cache.

The first live proof is separately approved: one deliberately selected opaque Gmail thread ID,
at most **3 messages, 128 KiB/message**. The inventory rejects larger threads **before raw reads**.
No list/discovery, attachment extraction, cloud call, model call, provider mutation or message occurs.
Preparation reuses the single volatile acquired thread for provenance-checked summary/extraction,
private projection and a fixed synthetic **unsent, unstored** draft. Output is aggregate counts,
elapsed time and boolean/cost evidence only; no account, source IDs, message text or tokens.

```powershell
rtk proxy uv run --locked jarvis email gmail-proof --account "<exact-lowercase-mailbox@gmail.com>" --client-file "<absolute-private-desktop-client.json>" --thread-id "<explicit-selected-opaque-thread-id>"
```

Normal `email thread/read/summary/extract/draft` and local `chat --email-thread` use the configured
provider under [email privacy/retention controls](EMAIL.md). Their output can contain private text;
do not capture it into public evidence. A mailbox reply is untrusted evidence, never action authority.

## Disable, disconnect and recovery

Set `JARVIS_EMAIL_ENABLED=false` or choose another text profile, remove
selection and stop/restart existing Core/CLI processes. A running adapter/service disable invalidates
in-flight results, including disable/re-enable cycles. Changing environment variables alone cannot
reconfigure an already-running process. Selecting `private-email` alone does not enable reads;
the independent `JARVIS_EMAIL_ENABLED=true` setting is also required.

Disable stops reads; it does not remove credentials, revoke Google consent or erase conversations.
To disconnect local credentials, stop other Core/CLI processes, then explicitly confirm:

```powershell
rtk proxy uv run --locked jarvis email gmail-disconnect --account "<exact-lowercase-mailbox@gmail.com>" --client-file "<absolute-private-desktop-client.json>"
```

The command deletes only this exact local account/client token, not the registration file or
Google grant. Other active processes can hold access tokens until stopped/expired; each new
acquisition rechecks local token presence. Provider-side revocation is a separate owner action at
[Google Account connections](https://myaccount.google.com/connections). Never automate revocation
or token replacement without applicable authority. Use normal conversation deletion for private
derived replies; SQL deletion does not securely erase WAL/backups/storage. Keep privacy migration
016 on source rollback. Physical phone checks remain **skipped by owner; unverified**.
