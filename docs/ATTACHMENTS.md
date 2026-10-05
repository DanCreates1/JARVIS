# Local conversation attachments

Phase G adds default-off attachments to local CLI and loopback browser chat. Original bytes,
normalized images and chunks remain in existing private SQLite. Source and model output are
untrusted data, never tool authority, approved memory or automatic research input.

## Enable and use

Enable on the host; restart an existing browser process after changing settings:

```powershell
$env:JARVIS_ATTACHMENTS_ENABLED = 'true'
rtk uv run jarvis attachments upload C:\local\notes.txt
rtk uv run jarvis attachments upload C:\local\other.pdf -c CONVERSATION_ID
rtk uv run jarvis chat -c CONVERSATION_ID --attachment ATTACHMENT_ID -m 'Explain relevant evidence'
rtk uv run jarvis attachments list CONVERSATION_ID
rtk uv run jarvis attachments inspect CONVERSATION_ID ATTACHMENT_ID
rtk uv run jarvis attachments delete CONVERSATION_ID ATTACHMENT_ID
```

Upload returns metadata JSON (`conversation_id`, `id`, `status`, sanitized `error_code`). Use only
`ready` IDs. Repeat `--attachment` for at most four unique IDs. Interactive chat retains selection
until exit; deletion makes subsequent use fail explicitly. CLI rejects linked/reparse paths and
reads only the selected regular file. Display filenames never become storage paths.

Local browser: choose file, Upload, select checkbox, send message. Status/deletion appear beside
each record; failed records remain inspectable. Upload/message submission serialize conversation
creation. Reload clears browser selection; durable records remain accessible through CLI.
Authenticated phone PWA has no attachment UI/upload scope.

## Bounds and processing

| Resource | Limit |
| --- | --- |
| Upload | Nonempty, at most 5 MiB |
| Types | UTF-8 `.txt`/`.md`, text PDF, single-frame PNG/JPEG |
| Text | 100,000 characters; 1,000-character chunks, at most 100 |
| PDF | 50 pages; 8 MiB decoder bounds; encrypted/textless/scanned PDF rejected |
| Image | 8,000,000 pixels; normalized RGB JPEG, at most 2,048 pixels per side and 2 MiB |
| Parser | 512 MiB allocation; 10-second deadline; service queue/parse deadline 30 seconds |
| Host active storage | Default 50 MiB, configurable 5–100 MiB; originals plus derived/reserved bytes |
| Host active count | Default/max 100, configurable 1–100 |
| Retention | Default 24 hours, configurable 1–168 hours |
| Retrieval | Four selected IDs; six ranked chunks per file; 8,000 total projection characters |
| Vision | 60 seconds per image, at most four images; answer at most 4,000 characters |

Settings: `JARVIS_ATTACHMENT_MAX_STORAGE_BYTES`, `JARVIS_ATTACHMENT_MAX_COUNT`,
`JARVIS_ATTACHMENT_RETENTION_HOURS`, `JARVIS_ATTACHMENT_VISION_MODEL`. Admission reserves
worst-case derived bytes transactionally before parsing. Exact host/conversation/type/body
duplicates reuse a record. Quotas cover logical active payloads; DB/WAL/audit sizes can grow.

Each parse starts fixed Python code with isolated imports, minimal environment, bounded pipes and
OS memory limits. Source paths, URLs, JavaScript/actions/commands are never executed. Windows Job
Objects restrict allocation and child processes; this is not an AppContainer or filesystem/network
sandbox. Parent kills/reaps timed-out or cancelled workers before temporary directory cleanup.
Interrupted processing becomes `failed/processing_interrupted` after 60 seconds during the next
explicit lifecycle operation; no automatic retry or daemon exists.

Local token-overlap ranking emits `[attachment:ID#chunk:N]` provenance. Only selected excerpts
are supplied, with explicit truncation. Raw/derived digests are checked before projection;
deletion/expiry invalidates the selection before the next provider context. Original excerpts
are not automatically persisted in chat; assistant replies can quote sources and remain private.

## Optional local vision

Set vision model only to an already installed local model. Adapter uses configured Ollama at
literal `http://127.0.0.1` or `http://[::1]`, rejects cloud names/remote profiles, disables environment
proxies/redirects, checks `/api/show` vision capability, then sends normalized pixels to `/api/chat`.
No download, credential, paid API, cloud fallback or model-facing tools occur.

Absent/failed interpretation yields explicit `vision_unavailable`, even if the image upload is ready.
Scanned PDF OCR, Office/archive/audio and external OCR binaries are deferred. Local vision is
interpretation, not guaranteed OCR. Installed `qwen3.5:0.8b` identified synthetic red pixels in
1,348.504 ms warm; initial cold request safely hit the unchanged 60-second deadline.

## Privacy and recovery

Upload sets a host-owned sticky conversation privacy flag. Later follow-ups stay local after
deletion, with cloud-role overrides denied, automatic research skipped and automatic memory
candidate capture suppressed. Client metadata cannot clear it. Start a new conversation for
public web research. Phase C public-only acquisition and Phase D discovery/action owners remain.

Upload/list/inspect/delete/attachment chat require local peer and Host, same or absent Origin,
no forwarding headers, cookies or Authorization. No raw download or new `/api/v1` scope exists.
Raw upload: `POST /api/attachments?filename=NAME&conversation_id=ID`, allowlisted Content-Type,
bounded body. Metadata routes: `/api/conversations/{conversation_id}/attachments`. This boundary
does not distinguish programs already running as the same local user.

Delete removes original/derived rows; conversation deletion cascades. Expiry runs during explicit
operations. Processing/deletion audit contains IDs/status only; SQL debug parameter logging is
disabled. Backups include attachments and follow existing encrypted backup/access/retention policy.
Deletion does not erase replies, old backups, WAL pages or storage. Disable attachments to stop
uploads/projection; CLI list/inspect/delete remain usable. Preserve migration 015/private DB on
rollback; never downgrade schema or discard user state.

## Verification

```powershell
rtk uv run python scripts/phase-g-attachments-benchmark.py --enforce
rtk uv run python scripts/phase-g-attachments-benchmark.py --enforce --vision-model ALREADY_INSTALLED_MODEL
rtk uv run python scripts/phase-g-attachments-smoke.py
```

Benchmark uses synthetic data, 100 fixed queries and 20 isolated parses. Smoke uses temporary
private storage and existing local models without reading application credentials. Exact release
evidence: [Phase G completion](phase-reports/PHASE_G_COMPLETION.md).

Primary references checked:
[Ollama vision](https://docs.ollama.com/capabilities/vision),
[Ollama chat](https://docs.ollama.com/api/chat),
[Pillow security](https://pillow.readthedocs.io/en/stable/handbook/security.html),
[pypdf reader](https://pypdf.readthedocs.io/en/stable/modules/PdfReader.html),
[async subprocess](https://docs.python.org/3/library/asyncio-subprocess.html),
[Windows Job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).
