# Inspectable memory and project context

Phase 10 adds explicit `private-memory`: daily local text, existing canonical memory, and a
trusted-laptop review workspace. One Windows Core, SQLite/FTS5 and router. No new client scope,
remote approval, vector service, repository execution, cloud provider or automatic trust.

## Start and inspect

After locked setup, stop the existing Core normally before starting another writer:

```powershell
rtk proxy .\scripts\open-memory.cmd
```

Uses installed `qwen3:1.7b`, temperature 0, local-only routing and clock-only tools. Research,
attachments, health, email, capture, voice, actions, task execution and proactivity stay disabled.
Existing text/files/Garmin profiles remain unchanged. Memory inspection is independent of model
availability and the retrieval toggle. No owner-store migration or credential change is required.

On the laptop, open the Core's literal loopback URL, for example `http://127.0.0.1:8765/app/`, then
Settings → Open trusted local memory review. Direct `/memory` also works. The PWA private HTTPS
route still handles normal authenticated chat; memory review requires the local address. The link
is hidden on remote origins. This local page uses existing trusted-local confirmation authority,
not an enrolled browser's chat scope. It needs no enrollment and grants no remote memory access.

Select Inspect deliberately. Filter candidate/committed/corrected/rejected/expired and category;
pages contain at most 20 previews, 600 characters each, bounded offsets through 10,000. Open an item
for exact content, confidence, sensitivity, provenance/trust, digest/version, expiry, superseded ID,
derivation sources and conflict IDs. Inspect again after concurrent changes; pagination is a fresh
view, not a frozen snapshot. CLI remains available beyond this bounded browser window.

- Approve displays exact candidate text and binds ID, version and SHA-256. Stale/replayed requests
  fail. Original imported/message provenance stays visibly untrusted after explicit confirmation.
- Reject keeps content inspectable but excludes recall. It never grants trust.
- Correct confirms exact replacement and creates a new committed item. Old content remains
  corrected lineage. Existing derived summaries with corrected or expired ancestors are excluded
  from retrieval, including after restart; they remain inspectable. Private sources force derived
  sensitivity private. New derivations reject expired sources.
- Forget confirms physical removal from canonical memory, FTS, provenance/conflicts and final-source
  derivatives. Other corrected versions, independent/multi-source context, transcripts and backups
  remain separate; inspect and forget each version when appropriate. Tombstones/events contain no
  deleted content or digest. Deletion is not forensic disk erasure or backup deletion.
- Save exact owner context requires deliberate text review/confirmation. Chat extraction only
  proposes candidates; model/file/repository instructions cannot promote themselves.

Explain retrieval uses POST body, not a private query URL. It shows actual FTS matching/relevance
reasons and source IDs, plus the bounded projection preview: <=8 approved unexpired items and
<=4,000 characters. Disabled retrieval is labeled inspection-only. Sources remain untrusted context,
never tool/action authority. Private/uncertain context routes locally before disclosure. No model
request occurs during browsing, approval, correction, retention or explanation.

Open contradictions stay visible; no silent merge. Use existing trusted CLI `memory conflicts`
and `memory resolve-conflict --help` to review exact winner control. Rejection/forgetting and
correction do not claim old replies or backups were erased.

## Retention, privacy and recovery

Inspect retention before changing it. Days apply from original creation to existing committed and
future items of that category, updating versions; older content can immediately leave recall.
Working memory cannot be indefinite. UI accepts 1–36,500 days; existing CLI retains full policy
controls. Mark due items expired updates lifecycle; expiry already excludes recall even before this
operation. Expired/rejected/corrected content stays inspectable until explicitly forgotten.

Every memory page/API request requires local peer and literal local Host/Origin, denies forwarding,
cross-site fetch and bearer identity. Static HTML/script may receive a browser cookie during
navigation but contain no private records. Data calls omit credentials; cookies are denied on all
memory data/control APIs. Existing legacy memory routes receive the same guard. Signed/PWA scopes
cannot create trusted-local identity. Mutation bodies are bounded to 262,144 bytes/10 seconds.

Private view uses text nodes, no browser storage, service-worker cache, automatic retry or offline
queue. Clear private view, hide/tab change or navigation aborts pending work and erases rendered
records, query and draft. Returning from browser history requires fresh inspection. Unknown mutation
outcomes require Inspect before retrying. Concurrent version changes fail closed. An interrupted
request may already have committed; clearing a view does not roll back Core. Stop Core normally
before restoring a verified private SQLite backup; preserve migrations and current data first.

`JARVIS_MEMORY_RETRIEVAL_ENABLED=false` disables prompt projection while inspection/lifecycle remain
available. Return to `open-daily.cmd`/`open-local.cmd` for prior profile behavior; this does not delete
memory. Local review remains a trusted Windows-user interface, not separate OS-user authentication.
Windows account/storage protection and private backup management remain operator responsibilities.

## Explicit project context

Repository inspection remains trusted CLI only. Under `private-memory`, enable
`JARVIS_CODING_CONTEXT_ENABLED=true` with `JARVIS_CODING_REPOSITORY_ROOT` set to an explicit absolute
Git checkout. Data/checkpoints must stay outside that repository. Default remains disabled.

```powershell
rtk proxy .\scripts\open-memory.cmd coding context
rtk proxy .\scripts\open-memory.cmd coding checkpoint
rtk proxy .\scripts\open-memory.cmd chat "repo: explain current changes"
rtk proxy .\scripts\open-memory.cmd coding clear
```

Only explicit CLI `repo:` requests get private repository projection. Browser/voice requests deny
before persistence/provider invocation. Fixed inert Git reads, path/secret exclusions, deadlines,
<=8,000-character context and metadata-only 24-hour checkpoints remain as documented in
[Token continuity](TOKEN_CONTINUITY.md). Source content cannot execute, stage, approve, persist into
memory or create a task. Fresh context revalidates source after restart; checkpoint is no proof of
current source. Clearing checkpoint never removes canonical memory or repository files.

## Verification

```powershell
rtk proxy uv run --locked python scripts/memory-acceptance.py --live
rtk proxy uv run --locked python scripts/phase4-memory-benchmark.py --work-dir runtime/phase10/new-memory-benchmark --enforce
rtk proxy uv run --locked python scripts/phase-f-continuity-benchmark.py --enforce
```

Live acceptance owns new synthetic stores, TLS fixture/browser profile and installed local model;
no real credentials, owner state or private route. Runtime evidence remains ignored. Frozen
retrieval set/thresholds and current measurements: [Phase 10 progress](phase-reports/current/PHASE_10_PROGRESS.md).
Existing [memory evidence](phase-reports/PHASE_4_COMPLETION.md) remains historical.

Official contracts checked 2026-10-28: [SQLite FTS5](https://www.sqlite.org/fts5.html),
[Git environment controls](https://git-scm.com/docs/git),
[Python subprocess lifecycle](https://docs.python.org/3.11/library/asyncio-subprocess.html).
No dependency upgrade. Phone checks **skipped by owner; unverified**. No physical/native, mobile MVP,
production or deployment acceptance; native/provider publication holds remain.
