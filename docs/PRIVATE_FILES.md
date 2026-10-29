# Private files workspace

Phase 9 adds explicit `private-files`: daily local text plus deliberately supplied attachments.
One existing Windows Core, SQLite store, router and authenticated PWA. Laptop must stay reachable.
Accepted `prototype-text`, `daily-text` and `private-garmin` profiles keep their boundaries.

## Start and capabilities

After locked setup, stop existing Core normally before starting another writer:

```powershell
rtk proxy .\scripts\open-files.cmd
```

Uses installed `qwen3:1.7b`, temperature 0 and local-only routing. Explicitly enables attachments
while disabling research, health, email, coding context, capture, voice, computer actions, task
execution and proactivity. Only deterministic clock is registered as a tool. Existing approved
private HTTPS origin and application identity/`client.chat` remain required; launcher creates no
route, enrollment or new scope. No credential or owner-store replacement.

| Supplied file | Behavior |
| --- | --- |
| UTF-8 TXT/MD | Bounded local extraction and selected cited chunks |
| Text PDF | Isolated local text extraction; embedded content never opens |
| Single-frame PNG/JPEG | Local preview and normalized JPEG; understanding separately configured |
| Scanned/textless/encrypted PDF, HEIC, Office/archive/audio | Explicit rejection/unavailable; use supported text |

Optional image understanding: configure `JARVIS_ATTACHMENT_VISION_MODEL` only to an already
installed local vision model, then restart. Configuration is not a successful interpretation:
each image checks actual local capability and rejects remote/cloud profiles before pixel disclosure.
Absent capability, timeout or failure yields `vision_unavailable`; no OCR guarantee, model download,
cloud upload or fallback. Capability text distinguishes extraction, normalization and configured
interpretation. Default product acceptance exercises unavailable image understanding.

## Deliberate workflow

1. Connect existing device; open Chat. Choose up to four files, each 1–1,048,576 bytes.
2. Review text/photo previews or PDF metadata. Cancel/Remove discards selection. Selection stages
   bytes in bounded Core memory; no parsing, generation or memory promotion occurs.
3. Write question and select Send. Core persists/processes files privately, then supplies bounded
   excerpts to local inference. Replies use `[attachment:ID#chunk:N]` references; references identify
   supplied excerpts and grant no authority. Interpretations can still be wrong.
4. Refresh attachment status. Ready files can be deliberately selected with Reuse in their same
   authorized conversation. Review, then Send. No silent reprocessing.
5. Search saved messages by literal text; source bodies are not a separate search index.

Four combined staged/reused files; 600-second staging with bounded cleanup. Navigation, hide,
offline, session changes and logout abort uploads and discard previews/selections. Restart clears
staging; choose original file again. No offline queue, automatic retry, resumption or Send.

## Privacy, lifecycle and recovery

Core owns exact host/device/conversation checks, parser isolation, original/derived integrity,
immutable request receipts, quotas and retention. Source/model output stays untrusted. Files grant
no tools, actions, research, approval or memory. Conversations become sticky private: follow-ups
stay local after deletion/restart; automatic memory candidate capture stays suppressed. No private
body/title/query/draft/file enters browser persistence, service-worker cache, URL, public provider
or diagnostics. Explicit replies can quote sources and remain in private conversation history.

Parser deadline 10 seconds; service queue/parse deadline 30 seconds; 512 MiB worker allocation;
100,000 text characters, 50 PDF pages, 8,000,000 image pixels; projection <=8,000 characters.
Host defaults: 50 MiB logical active payload, 100 files, 24-hour retention. Full
[bounds/storage contract](ATTACHMENTS.md#bounds-and-processing). Isolated worker with OS limits
is not an AppContainer/network/filesystem sandbox.

Failed/expired/interrupted sources show recovery guidance. Remove rejected selection and choose
supported original; review history before new request. Retry request checks original receipt and
never authorizes substituted content. Cancel reply stops current request; source rows remain
inspectable. Restart never blindly resumes parser/model work.

Trusted-host CLI list/inspect/delete remains available under [attachment contract](ATTACHMENTS.md).
Delete exact owned source through existing CLI; no new remote destructive route. Expiry runs on
explicit lifecycle operations. SQL deletion removes active source/derived rows, not earlier replies,
WAL pages, backups or underlying storage. Preserve migrations/private DB on rollback. To return to
text only, stop Core normally and use `open-daily.cmd` or `open-local.cmd`; files are not erased.
Disabled upload/projection preserves host lifecycle inspection/deletion.

## Verification

```powershell
rtk proxy uv run --locked python scripts/files-acceptance.py --live
rtk proxy uv run --locked python scripts/phase-g-attachments-benchmark.py --enforce
```

Live command uses only new ignored synthetic TLS identities/stores/files and installed local model;
never loads owner configuration/credentials. Results stay under ignored `runtime/phase9/`.
Foundation contracts: [F14](PWA_F14_WORKFLOWS.md), [F15](PWA_F15_WORKSPACE.md).
Current evidence: [Phase 9 progress](phase-reports/current/PHASE_9_PROGRESS.md).

Official contracts rechecked 2026-10-28: [Ollama vision](https://docs.ollama.com/capabilities/vision),
[Pillow security](https://pillow.readthedocs.io/en/stable/handbook/security.html),
[pypdf extraction limits](https://pypdf.readthedocs.io/en/stable/user/extract-text.html),
[Python 3.11 subprocess pipes](https://docs.python.org/3.11/library/asyncio-subprocess.html),
[Windows worker limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).
Locked parser versions retained; newer documentation grants no dependency upgrade.

Phone checks **skipped by owner; unverified**. Automated desktop evidence grants no physical/native,
mobile MVP or production acceptance. Native dependency and held provider publication boundaries stay.
