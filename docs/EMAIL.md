# Private email read and preparation

Status: current Phase 15 `implemented-closeout-pending`; local read/prepare foundation retained from Legacy IA.
Owner selected personal Gmail / desktop delegated OAuth / `gmail.readonly` on 2026-11-01. See
[current acceptance](phase-reports/current/PHASE_15_PROGRESS.md) and
[provider/auth decision](EMAIL_PROVIDER_DECISION.md). Production acquisition remains off.

Current live checkpoint, **2026-11-10**: owner completed approved Google setup/consent; actual
PKCE authorization, exact-account verification and protected Windows grant creation passed.
A narrowly selected live-thread attempt failed closed because one of its three messages exceeded
131,072 bytes. A second owner-selected, one-message conversation passed read/preparation in
805.831 ms with verified provenance and an unsent/unstored draft; release closeout remains pending.
Earlier synthetic-only/setup-pending descriptions below remain historical context;
no production configuration, cloud email, polling or send is enabled.

Email is default off. IA reads an explicitly configured local folder of owner-exported `.eml`
messages. It does not log into or discover an account. Gmail uses an explicit protected-host OAuth
command and separately configured foreground reads. No IMAP, SMTP, provider draft API, sender,
polling process or remote/mobile email endpoint exists. [Setup and recovery](GMAIL_SETUP.md).

## Selected Gmail adapter milestone

`jarvis.email.gmail.GmailReadProvider` implements the existing read port with default-off,
account-bound foreground requests. A trusted host token-source port is injected explicitly.
Protected Windows token storage, bounded PKCE desktop OAuth, foreground renewal and explicit
default-off settings/CLI are implemented and tested synthetically. Existing chat connections do
not supply credentials to JARVIS. Owner confirmed no project/client exists; actual project setup,
terms/consent, exact local account/client inputs and live proof remain pending. No live Gmail access
was performed. Startup neither opens credentials nor logs in.

The [frozen contract](EMAIL_PROVIDER_DECISION.md#selected-gmail-contract--frozen-2026-11-01-before-implementation)
records exact request/time/byte limits. Each operation first verifies the configured exact account.
List returns at most one page of 100 references, not a complete mailbox inventory. Reading one
thread acquires all 1–16 messages and compares inventories/history before returning any result;
changed, incomplete or over-limit threads fail closed. Raw MIME remains <=128 KiB/message in the
existing isolated parser. Inert attachment bytes can be present in MIME; no attachment endpoint or
remote resource is fetched. No provider writes, drafts, sending, cache, retries or polling.

Canonical Gmail IDs contain an account fingerprint, thread/message kind and reversible opaque ID.
Existing export ID rules remain unchanged. Provider-backed `EmailService` composition selects
`source_kind="provider"`; projection labels stay provider-neutral and private, with existing
`email:THREAD/MESSAGE` citations and source-byte digests. Neither source IDs nor metadata authenticate
senders or establish verified chronology. Disabling the adapter invalidates in-flight generations;
the preparation service also rejects results started before a disable/re-enable cycle.

Current milestone tests use synthetic tokens/transports, real isolated parsers and a disposable
synthetic Windows Credential Manager target. Actual Google setup/auth and selected-thread live
acceptance remain required; synthetic grants do not satisfy the live-provider exit.

## Configure exports

Keep private exports outside source control. `.eml` and `.mbox` files are ignored globally by this
repository; arbitrary renamed private files still must never be staged. Configure an absolute
local directory without symlinks, junctions, reparse points or hardlinked message files. Windows
drive type is checked before filesystem access; UNC/mapped-network and unknown drives are denied:

```text
exports/
  project_review/
    m001.eml
    m002.eml
```

Thread IDs are directory names; message IDs are filename stems. IDs use lowercase ASCII letters,
digits, `_` or `-`, start with a letter/digit, and contain at most 64 characters. Windows reserved
device names are rejected. Thread grouping and lexicographic message ordering come from the
export layout; subjects, dates and RFC message IDs do not establish identity or verified chronology.

```powershell
$env:JARVIS_EMAIL_ENABLED="true"
$env:JARVIS_EMAIL_EXPORT_ROOT="C:/private/email-exports"
rtk uv run jarvis email list
rtk uv run jarvis email thread project_review
rtk uv run jarvis email read project_review m001
rtk uv run jarvis email summary project_review
rtk uv run jarvis email extract project_review
rtk uv run jarvis email draft project_review --to recipient@example.invalid --subject "Review" --body "Owner-authored proposal"
rtk uv run jarvis chat --email-thread project_review -m "Summarize decisions; cite email message IDs."
```

`summary` returns an extractive digest: a bounded original excerpt per message, with message
provenance. `extract` returns quoted action-keyword and ISO-shaped date candidates. Dates are
unverified text, with no normalized timezone, assigned task, calendar mutation or commitment.
CLI digest excerpts and extraction quotes are prefixes of at most 512 characters; extraction
returns at most 64 candidates. These bounded candidates do not claim exhaustive semantic coverage.
`draft` requires explicit bare recipient mailboxes, subject and body, displays typed JSON and exits.
It neither stores nor sends a draft. A chat-generated draft is also an untrusted unsent proposal;
it can remain in private conversation history under normal chat retention.

## Bounds and parsing

At most 100 thread directories, 16 messages per thread, 128 KiB per message, 32 MIME parts and
8 levels of MIME traversal. Read/preparation has a 30-second deadline; each short-lived parser has
a 5-second deadline, 210,000-byte output cap, isolated Python startup and minimal environment.
Cancellation kills and reaps the parser. Blocking local filesystem reads run off the event loop;
an already-started filesystem read cannot be forcibly canceled. No retry or background work.

Only plain text is extracted: UTF-8, US-ASCII, ISO-8859-1 and Windows-1252. Malformed MIME,
duplicate core headers, unsupported charset, empty/HTML-only content and limit breaches fail
closed. HTML, tracking images, links, message attachments and forwarded `message/*` parts are
not fetched, rendered or used as body evidence. Worker text is capped at 32,000 characters and
truncation is marked. Headers are bounded unverified metadata. SHA-256 identifies observed source
bytes; it does not authenticate a sender. Current primary references:
[Python parsing API](https://docs.python.org/3.11/library/email.parser.html) and
[Python email message API](https://docs.python.org/3.11/library/email.message.html).
Windows local-volume check follows
[GetDriveTypeW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getdrivetypew).

An export read checks component links/types, file identity, size and timestamps before/after open.
It does not claim an atomic snapshot across messages or protection against an adversary controlling
the local filesystem while reads run. Parser isolation is a resource/process boundary, not an OS
filesystem/network sandbox. The worker contains no network acquisition code or inherited provider
credential. Exported attachment bytes remain inert inside the bounded parser process.

## Privacy and authority

Email selection is supported only by explicit local CLI chat. Before acquiring email, migration
016's host-owned `email_private` bit is committed on the existing conversation. The bit survives
restart, failed parsing, selection removal and feature disable; client metadata cannot clear it.
Every later turn stays private, avoids automatic research and automatic memory-candidate capture,
and rejects cloud overrides through the existing model router. Raw email projection is turn-local,
at most 8,000 characters, and never appended to conversation history. Replies can contain private
derived content and follow normal private conversation retention, backup and deletion.

Every projected excerpt carries `email:THREAD/MESSAGE` and its source digest; omission is explicit.
Email bodies, headers, dates, draft recipients and model output remain untrusted data. They grant
no tool, Phase 3 approval, scheduler, memory promotion or send authority. Phase D discovery still
lists only existing execution owners. Phase C public research and Wikimedia's
`authentication_required` blocker remain unchanged.

## Recovery and next gate

Disable `JARVIS_EMAIL_ENABLED` to stop acquisition; remove selection and restart. Source exports
are never modified, deleted or copied into JARVIS storage. There is no email cache/draft database.
Use existing conversation deletion for private replies; SQL deletion does not securely erase WAL,
backups, terminal output or underlying storage. Keep migration 016 and the private database when
rolling source back so sticky privacy remains available.

Current Phase 15 needs approved project/client setup, exact local account/client configuration,
actual credential/access authority and the prepared bounded private mailbox smoke. Existing explicit
authority persists within scope; selection alone does not grant login, new scopes or private reads.
Current official OAuth/API/data-policy sources were reviewed before the inactive read adapter
milestone. Any provider draft/write/send requires exact existing
Phase 3 approval plus provider authorization and fresh external-effect authority. No blanket
send permission transfers from reading email, preparing a draft or Git publication. Stop before
J — Calendar.

Local gates:

```powershell
rtk uv run python scripts/phase-i-email-benchmark.py --enforce
rtk uv run python scripts/phase-i-email-smoke.py
```
