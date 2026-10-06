# Private email read and preparation

Status: IA local release; IB live provider integration blocked on fresh authority.

Email is default off. IA reads an explicitly configured local folder of owner-exported `.eml`
messages. It does not log into or discover an account. No credential, OAuth, IMAP, SMTP, provider
draft API, sender, polling process or remote/mobile email endpoint is installed.

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

IB needs owner-selected provider/account type, fresh credential/access scopes and a separately
authorized private mailbox smoke. Review current official OAuth/API documentation then implement
the adapter behind `EmailReadProvider`. Any provider draft/write/send requires exact existing
Phase 3 approval plus provider authorization and fresh external-effect authority. No blanket
send permission transfers from reading email, preparing a draft or Git publication. Stop before
J — Calendar.

Local gates:

```powershell
rtk uv run python scripts/phase-i-email-benchmark.py --enforce
rtk uv run python scripts/phase-i-email-smoke.py
```
