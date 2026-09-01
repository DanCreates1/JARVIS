# Phase 4 Durable Memory and Personalization Completion

Status: `complete`
Started: 2026-08-29
Completed: 2026-08-29
Updated: 2026-08-31
Recommended Sol thinking: Extra high

## Objective

Deliver useful, inspectable, host-isolated memory without silently treating model guesses or
untrusted content as facts. Ship bounded working, episodic, profile, semantic, and task memory;
candidate extraction and exact confirmation; provenance, confidence, retention, correction,
conflict, export, transitive deletion, FTS5 retrieval, prompt projection, and measured evidence.

## 2026-08-31 revalidation

Current source, migration, store, API/runtime integration, tests, prior evidence, and recovery
behavior were reinspected. No implementation gap was found; current evidence supports `complete`.

- Targeted lifecycle/privacy/migration/restart/recovery/API/adversarial suite: 56 passed with one
  upstream Starlette `TestClient` deprecation warning in 1.92 seconds.
- Fresh enforced benchmark: precision 0.9090909091, recall 1.0, accepted-hit rate 1.0, false recall
  0.0, and zero cross-host hits across 25 golden queries.
- Warm retrieval: 500 queries over 2,500 records; p50/p95 1.2383/37.0088 ms. Cold/restart:
  20 samples; p50/p95 41.0982/80.0949 ms.
- Deletion completeness 1.0; two requested/derived canonical, FTS, and provenance rows removed;
  zero content-bearing rows remained. Backup/restore, migration versions 1-5, FTS5, integrity,
  and 100 concurrent operations with zero failures all passed.
- Storage: 5,394,432 checkpointed bytes, 2,157.7728 bytes per record. FTS5 still meets every
  target; embeddings remain unjustified and unadopted.
- RTK remains blocked by Windows Smart App Control; direct locked commands were used as explicitly
  allowed by this program.
- Fresh ignored evidence: `runtime/phase4-revalidation-20260831-01/results.json`.

## Baseline and preserved state

- Branch/HEAD: `main` at `7d32b93`, tracking `origin/main` when Phase 4 began.
- The worktree already contained extensive uncommitted Phase 1-3 source, tests, scripts, lock,
  configuration, and documentation. All were preserved; no reset, checkout, commit, or push ran.
- Windows 11 Home build 26200; AMD64; Python 3.11.16; SQLite 3.53.1; uv 0.12.5; RTK 0.45.0;
  Gitleaks 8.30.1.
- Existing migrations 001/002 supplied conversations, messages, legacy note/profile/task records,
  audit, and approval tables. Migrations 003/004 supplied Phase 3 authority/audit state.
- No paid service, account, credential change, infrastructure, external disclosure, model download,
  or irreversible data operation was used. Fixtures and benchmarks contain synthetic data only.

## Delivered design

### Schema and lifecycle

- Additive migration `005_phase4_memory.sql` adds canonical memory items, typed provenance,
  derivation edges, contradictions, per-host retention rules, content-free tombstones, append-only
  memory events, synchronized FTS5, and indexes.
- Categories: working, episodic, profile, semantic, and task.
- States: candidate, committed, corrected, expired, rejected, plus physical deletion represented by
  a minimal tombstone/event rather than retained content.
- Every item carries host scope, optional stable key, content SHA-256, structured fields,
  sensitivity, confidence, retention, timestamps, version, correction lineage, conflicts, and
  derivation metadata.
- Legacy note/profile/task rows migrate without loss into an isolated `host-legacy` quarantine.
  They are not silently attributed to a different user/device.

### Confirmation, provenance, and conflicts

- Deterministic extraction recognizes bounded explicit name/preference/task/remember statements and
  can only create candidates.
- Promotion binds pseudonymous local host scope, trusted interface, candidate ID, exact version,
  exact content digest, and confirmation time. Replay, stale content/version, wrong host, and
  invalid state fail closed.
- Provenance types cover conversation, message, tool, import, explicit host input, and derived
  records. Trust is separate from confidence; untrusted content never becomes authorization.
- Corrections create a new version that supersedes the prior fact. Contradictions stay open and
  visible until exact local resolution; no silent last-write-wins merge occurs.

### Retrieval and privacy routing

- SQLite FTS5 is the only production retrieval index. Query sanitization, category/state filters,
  host predicates, deterministic deduplication, and relevance/recency/confidence/trust scoring are
  applied before bounded projection.
- Hits expose a score, reason, matched terms, and conflict/untrusted-source warnings.
- Prompt projection admits committed, unexpired records only and caps item count and characters.
  Retrieval failure degrades to no memory context rather than invented context.
- Private or unknown memory context forces local routing before any provider disclosure. Request
  content cannot choose a host scope.
- Embeddings were not adopted: FTS5 passed every declared target, so no measured recall gap could
  justify another model, dependency, backup surface, or deletion path.

### Inspection, retention, export, and deletion

- `jarvis memory` commands implement remember, list, search, promote, reject, correct, forget,
  export, conflict inspection/resolution, retention inspection/update, and expiry.
- Loopback APIs implement host-bound list/create/search/promote/correct/delete and transitive memory
  removal on conversation deletion. No Phase 3 approval/execution API was added.
- JSON export is explicit, local, exclusive-create, and non-overwriting. SQLite backup uses the
  consistent backup API and verifies integrity on restore.
- Forget physically removes canonical content, FTS rows, provenance, conflicts, and derived records
  whose final source was deleted. Tombstones/events retain no deleted content or content hash.
- `JARVIS_MEMORY_RETRIEVAL_ENABLED=false` disables projection without deleting canonical records or
  blocking inspection/export/correction/deletion.

## Milestones

### Milestone 1 - Baseline, acceptance, and threat boundaries

- Status: complete.
- Git state, prior reports, mandatory Phase 4 references, migrations, stores, tests, installed tools,
  and hardware/runtime were inspected before edits.
- Precision, recall, accepted-hit, false-recall, host-isolation, deletion, latency, storage,
  concurrency, and embedding-adoption thresholds were fixed before tuning.

### Milestone 2 - Schema, lifecycle, provenance, and retention

- Status: complete.
- Typed lifecycle, provenance, trust, confidence, sensitivity, retention, correction lineage,
  conflicts, derivations, events, tombstones, migration, legacy preservation, and WAL-backed store
  operations are implemented and restart-safe.

### Milestone 3 - Retrieval, confirmation, conflicts, and interfaces

- Status: complete.
- Exact confirmation, FTS retrieval, scoring, bounded projection, privacy routing, CLI, and loopback
  API inspection/control paths are implemented and tested.

### Milestone 4 - Adversarial, migration, recovery, and benchmark evidence

- Status: complete.
- Golden retrieval, contradiction, poisoning/injection, host isolation, migration, restart,
  backup/restore, corruption, retention, transitive deletion, lock/concurrency, web, CLI, and runtime
  tests pass.
- Raw SQLite checks verify deletion across canonical, FTS, provenance, conflict, and derivation data.

### Milestone 5 - Release gate and closeout

- Status: complete.
- Locked clean-environment tests, coverage, type, format, lint, dependency audit, secret scan, Git
  whitespace, doctor, benchmark, and required documentation gates pass.
- Optional voice dependencies were restored after the base clean-environment gate, preserving the
  workstation's prior optional environment.

## Acceptance results

- Golden fixture: 20 records across all five categories; 25 queries including five negatives.
- Precision: `0.9090909091` (target `>=0.90`).
- Recall: `1.0` (target `>=0.90`).
- Accepted-hit rate: `1.0` (target `>=0.90`).
- False recall: `0.0` (target `<=0.05`).
- Cross-host hits: `0`; candidate/rejected/corrected/expired records never enter prompt projection.
- Warm retrieval: 500 queries over 2,500 records; p50 `1.15175 ms`, p95 `35.023 ms`, max
  `36.9745 ms` (p95 target `<=50 ms`).
- Cold/restart retrieval: 20 samples; p50 `40.92905 ms`, p95 `82.8513 ms`, max `83.4406 ms`.
- Storage: 2,500 records; `5,386,240` checkpointed bytes; `2,154.496` bytes/record (target
  `<=16,384`).
- Concurrency: 100 operations through independent connections; `0` failures; 100 unique committed
  IDs; integrity `ok`.
- Deletion: two requested/derived records; two canonical, two FTS, and two provenance rows removed;
  zero content rows remain; completeness `1.0`.
- Migration versions: `[1, 2, 3, 4, 5]`; FTS5 available; backup/restore passed.
- Benchmark artifact: ignored local file
  `runtime/phase4-memory-benchmark-20260829-02/results.json`.

## Verification evidence

Current integrated release evidence (2026-08-31): substantive locked gate passes with 530 tests
passed, 1 skipped, 85.20% coverage; 66 source files type-check; 147 files are formatted; lint,
dependency audit (including restored voice extra), Gitleaks, diff check, and doctor pass. Exact
`mypy`, `pytest`, `pip-audit`, and `jarvis` console shims are blocked by Windows Application Control
OS error 4551; Python-module equivalents pass. Full command evidence is in the Phase 1 report.

Historical 2026-08-29 closeout evidence follows:

```text
rtk uv lock --check
PASS: 115-package resolution current

rtk uv sync --locked
PASS: locked base environment, 62 packages checked

fresh ignored runtime/phase4-sync-env-20260829-02
PASS: CPython 3.11.16, 62 locked packages installed with copy mode

rtk uv run ruff format --check .
PASS: 147 files

rtk uv run ruff check .
PASS

rtk uv run python -m mypy src
PASS: 66 source files

rtk uv run python -m pytest --basetemp runtime/phase4-pytest-basetemp-20260829-03
PASS: 525 passed, 1 skipped, 85.11% coverage, 1 third-party warning

rtk uv run python -m pip_audit
PASS: no known vulnerabilities, including restored voice extra environment

rtk gitleaks detect --source . --redact --no-banner
PASS: 8 commits, 716.89 KB, no leaks

rtk git diff --check
PASS: exit 0; two pre-existing PowerShell LF-to-CRLF working-copy notices only

PYTHONIOENCODING=utf-8 + rtk uv run jarvis doctor
PASS: configuration, storage/migrations, disabled computer authority, Ollama service/model,
reasoning catalog; JARVIS ready

rtk uv run python scripts/phase4-memory-benchmark.py ... --enforce
PASS: every declared check true
```

Windows Application Control rejects the generated `mypy.exe`, `pytest.exe`, and `pip-audit.exe`
console shims with OS error 4551. No policy was changed or bypassed. The same locked packages ran as
Python modules through the allowed uv-managed CPython 3.11 interpreter in both the synchronized
project environment and a fresh ignored environment. This matches the established Phase 3 gate
method and executes the complete checks rather than skipping them. `jarvis.exe` is allowed; doctor
passed after `PYTHONIOENCODING=utf-8` avoided RTK/cp1252 output-flush failure.

The one skipped test is the existing Windows directory-symlink negative test: this non-elevated
account lacks `SeCreateSymbolicLinkPrivilege` (`WinError 1314`). All other 525 tests passed. The one
warning is Starlette's third-party `TestClient` deprecation for `httpx`; it does not affect runtime
behavior or test results.

## Security and privacy evidence

- Dedicated adversarial tests cover injected instructions, poisoned memory, stale confirmation,
  contradiction, untrusted provenance, malformed import/record behavior, replay, wrong-host IDs,
  source deletion, and private-context cloud-routing denial.
- Every query, mutation, export, conflict, correction, retention, and deletion path requires exact
  host scope; wrong-host behavior returns no existence oracle.
- Candidate confidence cannot grant authority. Model/chat/tool/import content cannot self-confirm.
- Deletion completeness is checked directly in SQLite, not inferred from API output.
- No cloud request, paid API, account, credential, private data, computer action, microphone,
  camera, or external memory store participated in Phase 4 tests or benchmark.
- Gitleaks found no secret. Dependency audit found no known vulnerability.

## Known limits and deferred scope

- The local host ID partitions one Windows user/device; it is not remote authentication.
  Authenticated enrollment, revocation, cross-device ownership, and encrypted multi-device backups
  remain Phases 8/9.
- Legacy Phase 1 memories remain preserved under `host-legacy` quarantine and are not silently
  adopted. A future explicit migration UI may attribute them after host review.
- SQLite/runtime data is not encrypted at rest by Phase 4. Windows account/storage controls and
  operator-managed private backups remain required.
- Extraction is intentionally narrow and deterministic. Future model-based extraction must retain
  the same candidate-only, untrusted boundary.
- FTS5 is lexical. Embeddings remain absent until a reproducible candidate clears the declared
  five-point benefit and non-regression rule.
- Loopback web controls have no remote authentication and must stay on `127.0.0.1` until Phase 8.
- Automatic backup scheduling and JSON import/restore are not shipped; export is inspection/data
  portability, while SQLite backup restore is an operator recovery procedure.

## Recovery and rollback

- Migration 005 is additive and leaves conversation/action tables intact.
- Disable prompt projection with `JARVIS_MEMORY_RETRIEVAL_ENABLED=false` while retaining local
  inspection and control.
- Before manual database restore, stop writers, preserve the current database, restore only a
  verified private SQLite backup, and run `jarvis doctor`/integrity checks.
- JSON exports never overwrite and are not automatic restore inputs.
- Do not delete migrations or reset the dirty worktree to roll back Phase 4.

## Documentation updated

- `README.md`, `.env.example`, `docs/PHASE_OVERVIEW.md`, `docs/JARVIS_MASTER_ROADMAP.md`,
  `docs/roadmap.md`, `docs/JARVIS_ARCHITECTURE.md`, `docs/architecture.md`,
  `docs/SECURITY_MODEL.md`, `docs/security.md`, `docs/setup-windows.md`, and
  `docs/TECHNOLOGY_DECISIONS.md` now describe verified behavior, controls, recovery, limits, and the
  FTS-only measured decision.

## Final handoff

- Final status: complete.
- Blockers: none for Phase 4. Windows console-shim policy and symlink privilege are documented
  environment limitations with complete allowed-path verification.
- Next recommended phase: Phase 5 research/self-education on the source-aware Phase 4 memory model.
- Commit/push status: not authorized; none performed.
