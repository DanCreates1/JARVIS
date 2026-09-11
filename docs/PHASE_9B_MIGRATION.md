# Phase 9B Migration, Backup, Reconciliation, and Rollback

Phase 9B provides a reversible data-transfer and ownership-evidence workflow. It does not deploy a
server, enable a remote writer, change `JARVIS_TOPOLOGY_PROFILE`, or permit two active cores.
Runtime remains hard-locked to `local-only`; Phase 9C must consume the reviewed ownership receipt
before any split/server-primary activation.

## State classification

One SQLite database contains all eight shared durable domains and moves as one consistent snapshot:

- identity;
- sessions and replay state;
- conversations;
- memory;
- research;
- tasks;
- permission authority; and
- audit.

Device settings, computer effects, and media capture stay on the laptop. Voice, vision, and
computer-access JSON controls are not copied by the migration bundle. Model files, `.env*`, API
keys, migration keys, logs, caches, media, runtime evidence, and PWA private keys are also excluded.

SQLite remains the justified database for Phase 9B. The workload has one canonical writer and does
not yet have measurements requiring PostgreSQL. A different database belongs after split-topology
capacity evidence, not inside this migration rehearsal.

## Bundle and key boundary

`jarvis-migration-bundle-v1` uses:

- SQLite's online backup API for a transactionally consistent snapshot while the source remains
  readable;
- a caller-supplied random 256-bit master key stored in a separate private file;
- a random 256-bit HKDF-SHA256 salt and unique 96-bit AES-GCM nonce per bundle;
- a per-bundle AES-256 key derived with key-ID/domain separation;
- AES-256-GCM streaming encryption with the bounded public header authenticated as additional data;
- an encrypted manifest containing the exact topology profile/epoch/digest, source and target
  owners, current migration ledger, database SHA-256, schema SHA-256, row counts, and per-table
  logical fingerprints; and
- exclusive destination creation, flush, private file mode, and partial-file cleanup on handled
  failure.

The public header contains only the format, cipher, key ID, salt, and nonce. It contains no database
hash, schema, table, owner, host, prompt, user content, credential, or encryption key. Never store
the key file beside the bundle or in Git. Losing the key makes the bundle unrecoverable. A copied
key without its exact key ID is rejected.

Restore authenticates the complete ciphertext before parsing or exposing its plaintext. It then
creates a new destination only and verifies exact byte count/hash, current packaged migration
ledger, schema, every logical table fingerprint, `PRAGMA integrity_check`, and
`PRAGMA foreign_key_check`. Wrong key, altered header/ciphertext/tag, truncation, trailing data,
stale schema, foreign-key damage, topology mismatch, and existing destination fail closed.

## RPO, RTO, and ownership rules

- RPO: the exact accepted online snapshot. A source write after that snapshot invalidates cutover;
  create and verify a fresh bundle.
- RTO target: operator-driven recovery within 15 minutes after the service is stopped, paths and
  topology are verified, and the separate key is available.
- Cutover requires the source and restored target to have equal schema, migration ledger, row
  counts, and logical fingerprints while `BEGIN IMMEDIATE` locks reject concurrent writers.
- A cutover receipt selects exactly the remote topology's one shared-state owner. It does not move,
  delete, overwrite, chmod, or edit either database.
- Rollback requires an epoch-advanced `local-only` manifest, exact state equality, and the untampered
  cutover receipt. Its receipt chains the prior receipt hash and selects one local owner.
- Receipt creation is not runtime activation. Keep all JARVIS processes stopped around a real
  ownership transition. Phase 9C must add deployment enforcement before any remote writer exists.

## Rehearsal

Use private directories outside Git. Commands below never overwrite a file. Replace node IDs and
paths with reviewed values. Do not paste key bytes into a command, log, report, or chat.

Create a random key file with exclusive creation:

```powershell
$keyPath = 'D:\JARVIS-private\phase9b.key'
$key = [byte[]]::new(32)
[Security.Cryptography.RandomNumberGenerator]::Fill($key)
$stream = [IO.File]::Open($keyPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $stream.Write($key, 0, $key.Length); $stream.Flush($true) } finally { $stream.Dispose() }
[Array]::Clear($key, 0, $key.Length)
```

Create and review a remote topology manifest. This file grants nothing and reports
`"activates_runtime": false`:

```powershell
uv run jarvis remote migration manifest D:\JARVIS-private\split-epoch-2.json `
  --profile split --epoch 2 --server-node-id node:server --laptop-node-id node:laptop `
  --offline-capability node.voice
```

Create the encrypted bundle from the configured JARVIS database, then record the returned
`accepted_state_sha256` without recording the key:

```powershell
uv run jarvis remote migration backup D:\JARVIS-private\phase9b-epoch-2.j9b `
  --manifest D:\JARVIS-private\split-epoch-2.json `
  --key-file D:\JARVIS-private\phase9b.key --key-id phase9b-2026-09 `
  --source-owner-node-id node:laptop
```

Transfer the encrypted bundle and reviewed manifest through the approved private channel. Transfer
the key separately. Restore only to a new private path and compare the live source with the target:

```powershell
uv run jarvis remote migration restore D:\JARVIS-private\phase9b-epoch-2.j9b `
  D:\JARVIS-private\restored\jarvis.db --manifest D:\JARVIS-private\split-epoch-2.json `
  --key-file D:\JARVIS-private\phase9b.key --key-id phase9b-2026-09
uv run jarvis remote migration shadow $env:LOCALAPPDATA\JARVIS\jarvis.db `
  D:\JARVIS-private\restored\jarvis.db
```

Stop JARVIS before the final comparison. Create the cutover receipt using the exact accepted digest:

```powershell
uv run jarvis remote migration cutover $env:LOCALAPPDATA\JARVIS\jarvis.db `
  D:\JARVIS-private\restored\jarvis.db D:\JARVIS-private\cutover-epoch-2.json `
  --manifest D:\JARVIS-private\split-epoch-2.json `
  --source-owner-node-id node:laptop --accepted-state-sha256 <64-hex-digest>
```

Before any remote writes, rehearse rollback. Create a local-only manifest with a higher epoch and
chain a rollback receipt. Source and target must still match:

```powershell
uv run jarvis remote migration manifest D:\JARVIS-private\local-epoch-3.json `
  --profile local-only --epoch 3 --laptop-node-id node:laptop
uv run jarvis remote migration rollback D:\JARVIS-private\restored\jarvis.db `
  $env:LOCALAPPDATA\JARVIS\jarvis.db D:\JARVIS-private\rollback-epoch-3.json `
  --manifest D:\JARVIS-private\local-epoch-3.json `
  --previous-receipt D:\JARVIS-private\cutover-epoch-2.json `
  --accepted-state-sha256 <64-hex-digest>
```

If the source drifts, a lock cannot be obtained, any digest differs, or any command fails: do not
cut over. Keep `JARVIS_TOPOLOGY_PROFILE=local-only`, retain the last verified encrypted bundle and
separate key, and diagnose from content-free error code. Never copy a live SQLite main file without
its WAL through ordinary filesystem copy.

## Fixed verification

```powershell
uv run pytest --no-cov -q tests/unit/test_phase9_migration.py `
  tests/unit/test_phase9_migration_cli.py `
  tests/security/test_phase9_migration_security.py
uv run python scripts/phase9b-migration-benchmark.py `
  --output runtime/phase9b/benchmark.json
uv run jarvis doctor
```

The benchmark requires 100 full backup/restore/shadow/cutover/rollback cycles, 100 rejected
corruption attempts, one 64 MiB payload capacity run, zero operation failure/false accept/mismatch,
backup and restore p95 <= 2,000 ms, shadow p95 <= 1,000 ms, transition p95 <= 100 ms, and RSS growth
<= 100 MiB.

## Primary references checked

- [SQLite Online Backup API](https://www.sqlite.org/backup.html): use a consistent snapshot rather
  than copying a live database file.
- [SQLite PRAGMA checks](https://www.sqlite.org/pragma.html): `integrity_check` does not cover
  foreign-key errors, so both checks are mandatory.
- [Python `sqlite3.Connection.backup`](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup):
  supported online backup interface used by the implementation.
- [`cryptography` symmetric encryption](https://cryptography.io/en/latest/hazmat/primitives/symmetric-encryption/):
  GCM nonce uniqueness, full tag validation, and no plaintext use before finalization.
- [NIST SP 800-57 Part 2 Rev. 1](https://csrc.nist.gov/pubs/sp/800/57/pt2/r1/final): separate key
  management, recovery, and contingency responsibilities.
- [NIST SP 800-34 Rev. 1](https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final): rehearse and maintain
  contingency/recovery procedures rather than treating backup creation alone as recovery proof.
