# Token and coding continuity

Phase F adds opt-in private repository context to the existing assistant. Conversation reduction,
approved memory retrieval, tool result/iteration bounds, model routing and fallback remain the
existing implementations. There is no second orchestrator, authoritative memory store, scheduler,
model-facing coding tool, or remote coding endpoint.

## Setup and use

Configure local `.env.local` with `JARVIS_CODING_CONTEXT_ENABLED=true` and
`JARVIS_CODING_REPOSITORY_ROOT` set to the absolute checkout root containing `.git`.
`JARVIS_DATA_DIR` must put coding checkpoints outside that checkout. Default data storage already
uses local application data. Coding context defaults off; no root is inferred from chat or cwd.

```powershell
rtk uv run jarvis coding context
rtk uv run jarvis coding checkpoint
rtk uv run jarvis chat 'repo: explain current changes'
rtk uv run jarvis coding clear
```

`coding context` refreshes local context and its checkpoint without constructing model providers
or calling research. Local CLI chat projects repository data only for explicit `repo:` requests.
Those requests bypass automatic research, use `LOCAL_CONTEXT` freshness guidance, and attach a
private projection before provider routing. A requested cloud role cannot override privacy.
Browser/voice `repo:` requests, disabled context, malformed/public projections and adapter errors
fail before message persistence and provider invocation. Ordinary requests receive no repository
projection. Existing remote input adapters fix their interface metadata themselves.

The model receives file paths, up to twelve Python top-level class/function names with line
numbers per file, and compact HEAD-relative changed-code hunks. Changed files rank before unchanged
files within the inspected inventory. JavaScript/TypeScript/docs and other eligible text get paths
only in the map. Map/diff content is untrusted data, never approval or execution authority.

## Bounds and exclusions

- Eligible source directories: `src`, `tests`, `scripts`, `docs`, `mobile`, `garmin_sync`.
- Eligible extensions: `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.md`, `.sql`, `.css`, `.html`.
- Only current index or HEAD regular tracked source; staged additions/deletions and unstaged edits
  are reflected in the net working-tree-versus-HEAD diff. Untracked files are excluded. Stage a
  reviewed source file explicitly before it can enter coding context; the assistant cannot stage.
- Hidden paths, credential/secret names, ignored files (including force-tracked ignored files),
  fixtures, runtime/data/log/memory/model directories, vendor/generated directories, binary/control
  content, symlinks/junctions, submodules and path escapes are excluded.
- At most 512 sorted inventory paths, 128,000 bytes per source, 4,000,000 aggregate source bytes,
  eight changed-file diffs and 2,000 lines per compared file. Larger inputs are omitted with partial
  status. Metadata subprocess output over 256,000 bytes fails closed.
- Map and diff together use at most 8,000 characters (configurable down to 1,024); diff uses at most
  4,000 characters. Character limits bound context size; they are not exact provider token counts.
- Each Git subprocess has a five-second deadline; a snapshot has a 20-second asynchronous deadline.
  Source reads and bounded parsing are local. Timeouts/cancellation terminate and reap active Git
  children; a cancelled read worker can finish its bounded read but cannot write a checkpoint.

Git reads use fixed argument arrays, no shell/pager, no optional index writes, fsmonitor hooks or
lazy fetch. Inherited Git environment overrides are removed. Source is read directly; HEAD blobs
are obtained through inert `cat-file`, and Python computes diffs. This avoids clean filters,
external diff and textconv execution. Global/system Git settings are excluded except an existing
exact global `safe.directory` root entry, rechecked on each snapshot. No new trust exception is
created and no wildcard root is imported. See official [Git environment controls](https://git-scm.com/docs/git),
[tracked inventory](https://git-scm.com/docs/git-ls-files), and
[subprocess lifecycle](https://docs.python.org/3.11/library/asyncio-subprocess.html).

## Cache, checkpoint, recovery

The map has one in-memory cache slot per service/root. Its key hashes HEAD, fixed policy, included
paths and freshly read contents. `JARVIS_CODING_CONTEXT_CACHE_SECONDS` defaults to 30 (0 disables
reuse; maximum 3,600). Cache reuse saves symbol parsing only: current inventory, source bytes and
diffs are still checked. Diff content is never cached. Failures/cancellation and service close clear
the cache. No provider prompt cache or cross-conversation/source cache is introduced.

Every successful coding snapshot atomically updates
`JARVIS_DATA_DIR/coding-checkpoints/<repository-id>.json`. It contains schema version, pseudonymous
root/policy digests, HEAD, source fingerprint, file/change counts, partial status and UTC timestamps.
It contains no absolute paths, source filenames, symbols, code, diff, conversation, prompt, task
arguments, credentials, or instructions. Checkpoints never enter prompts or approved memory.
`docs/JARVIS_CHECKPOINT.md` remains reviewed repository documentation, not runtime state.

`coding checkpoint` inspects prior unexpired metadata, not a promise that the working tree still
matches. Always run `coding context` to revalidate after edits/restart. Checkpoints expire after
24 hours; expired records are excluded from inspection and replaced on the next successful
snapshot. Expiry is logical retention, not a background physical deletion worker. Wrong schema,
oversize, corrupt content, wrong root/policy binding or linked checkpoint paths fail closed.
Atomic replace leaves previous evidence intact on write failure. No migration is needed. To recover,
inspect local settings/Git, clear the exact derived checkpoint with `coding clear`, then refresh.
`coding clear` deletes only the configured root's derived state; it leaves transcripts and canonical
memory intact. Disabling coding context removes projection, while metadata remains available for
explicit deletion after re-enabling. No private coding cache/checkpoint should be committed.

## Evidence

```powershell
rtk uv run pytest tests/unit/test_coding_context.py --no-cov
rtk uv run python scripts/phase-f-continuity-benchmark.py --repository . --enforce
```

The fixed synthetic benchmark uses 100 snapshots: 50 content-change cache misses and 50 validated
cache hits over 60 source files. Gates: zero oracle/privacy errors, projection at most 8,000 chars,
and cold/warm p95 at most 1,000 ms. Optional workstation smoke reports aggregate counts and timing
only. Temporary synthetic repositories and their checkpoint metadata are removed at completion.
No model, credential, remote provider, paid service, research acquisition, deployment or live
computer effect is required. Phase C's Wikimedia `authentication_required` blocker remains separate;
Phase D registries retain their existing execution owners.
