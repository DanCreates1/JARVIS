# Phase 5 Research and Self-Education Completion

Status: `complete`
Started: 2026-09-04
Completed: 2026-09-07
Recommended Sol thinking: High

## Objective

Research host-selected public topics under bounded acquisition and parsing, answer with exact
source-level citations and visible uncertainty, and retain evidence only through explicit local
approval. Keep all external content separate from executable authority and trusted Phase 4 memory.

## Baseline and scope control

- Git branch/HEAD: `main` at `c33497b1474d1867230caf5a1f4bd8489dfd73a4`, tracking
  `origin/main` when Phase 5 began.
- The worktree already contained unrelated uncommitted Phase 1 streaming, benchmark, test, and
  documentation changes. They were preserved. No reset, checkout, stage, commit, or push occurred.
- Phase 4's completed host-isolated memory, provenance, conflicts, deletion, and FTS5 behavior was
  used as a persistence reference. Research remains a distinct, explicitly untrusted ledger.
- No paid service, account creation, credential change, private-data cloud disclosure, computer
  action, deployment, or destructive external operation was required.
- Runtime evidence: Windows build 26200, CPython 3.11.16, SQLite 3.53.1, HTTPX 0.28.1, uv 0.12.5,
  Gitleaks 8.30.1, and locked pypdf 6.17.0.

## Delivered system

### Contracts and bounded orchestration

- Added provider-neutral search, fetch, parse, synthesis, report, source, claim, citation, conflict,
  unanswered-question, approval, and storage contracts under `src/jarvis/research/`.
- `BoundedResearchOrchestrator` owns deterministic plan/search/fetch/parse/synthesize/review flow.
  It enforces total time, queries, sources, fetches, domains, per-source/aggregate text, claims,
  media types, and partial-failure bounds while preserving cancellation.
- Results are volatile by default. Stable report/source IDs and a SHA-256 report digest bind exact
  review and storage without treating model output as authority.

### Public discovery and acquisition

- Added account-free Wikimedia full-text discovery using the MediaWiki Action API. Provider
  selection and endpoint remain configuration-driven.
- `HttpDocumentFetcher` rejects credentials, fragments, direct IPs, localhost, and non-global
  DNS results. It connects to a validated IP while retaining original Host/SNI certificate
  verification, ignores proxy environment settings, disables connection reuse, and clears cookies.
- Redirects are manual, bounded, and revalidated. Only public HTTPS, approved media types, bounded
  decompressed bytes, valid metadata, and successful responses are accepted. Paywall/login,
  rate-limit, unavailable, timeout, malformed, oversized, and cancellation states stay typed.

### Isolated document parsing

- HTML, plain text, and PDF parsing runs in a short-lived `python -I -X utf8` subprocess with a
  minimal environment and fresh temporary working directory.
- Stdin/stdout, body, extracted text, timeout, PDF page count, and PDF decompression/filter limits
  are fixed. External JBIG2 execution is disabled. Scripts, styles, templates, navigation, macros,
  source instructions, unsupported formats, encrypted PDFs, malformed PDFs, empty documents, and
  oversized output fail closed.
- The worker contains no network, shell, computer-control, communication, or dynamic tool surface.
  This is process isolation and resource bounding, not a Windows AppContainer/kernel sandbox.
- `jarvis doctor` verifies the worker and locked PDF dependency with a fixed local text fixture.

### Citation and synthesis integrity

- Every material answer point references typed claim IDs. The deterministic renderer alone adds
  nearby `[source:<id>]` markers.
- Validation rejects unknown/inactive sources, fabricated or mismatched quotes, invalid/out-of-range
  locators, provider-authored markers/URLs, over-budget quotation, omitted material claims,
  unsupported uncited claims without explicit uncertainty, and unreported contradictory evidence.
- Configured model synthesis remains privacy-routed and schema-validated. Normal provider/schema
  failure degrades to a deterministic extractive synthesizer using exact bounded source sentences;
  cancellation still propagates.

### Durable research ledger and workflows

- Additive migrations 006–007 create host-isolated immutable source versions, active-source FTS5,
  claims, citations, conflicts, reports, unanswered questions, one-use approvals, append-only
  lifecycle events, and content-free tombstones.
- Exact storage approval binds host, trusted interface, report ID, digest, expiry, and one use.
  Replay, mutation, wrong host/interface, expiry, or failed digest comparison is denied.
- Source change/unavailability stales dependent claims. Report/claim supersession preserves lineage;
  obsolete open conflicts are dismissed. Restart, concurrent writers, corruption rejection, and
  not-found host-isolation behavior pass.
- Transitive source deletion removes all URL versions and dependent reports, claims, citations,
  conflicts, questions, and FTS rows. Remaining events/tombstones contain identifiers and lifecycle
  metadata only—not source text, claim text, quote, or content hash.
- Host-scoped JSON export uses exclusive file creation and refuses overwrite.

### Host interfaces

- CLI: `research run`, explicit `--store`, `list`, `show`, `search`, `revalidate`, `export`,
  `delete-source`, `questions`, and `close-question`.
- Loopback browser/API: bounded research run, digest-bound approval/denial, report/source inspection,
  local ledger search, revalidation, and exact-confirmation deletion.
- Browser/API surfaces expose no Phase 3 approval or execution authority. Source/model text cannot
  invoke research storage, deletion, or trusted-memory promotion.

## Acceptance evidence

### Final revalidation (2026-09-07)

- Phase 5 contract, integration, security, benchmark, model, orchestration, and parser tests:
  **94 passed** in 10.44 s.
- Fresh enforced 30-sample benchmark:
  `runtime/phase5-final-benchmark-20260907-02/results.json` (ignored runtime artifact).
- Citation coverage, fixture claim entailment, source diversity, freshness awareness, conflict
  handling, injection resistance, and reproducibility: **1.0** each; failures: **0**.
- Fresh latency: p50 **413.6922 ms**, p95 **447.6634 ms**, max **455.4612 ms**; fixed p95
  target **2,000 ms**.
- Fresh live public, no-storage Wikimedia run for `What is Python programming language?`:
  **2 sources**, **2 exact cited claims**, visible uncertainty, successful deterministic fallback,
  and explicit `Not stored` result.
- Full locked release suite: **644 passed, 1 skipped, 1 warning** in 25.22 s; exact coverage
  **85.02%**. Lock, sync, format, lint, type, dependency, secret, Git whitespace, and doctor gates
  pass. The generated `pip-audit` shim remains blocked by Windows Application Control with OS
  error 4551; the locked `python -m pip_audit` entry point passed without changing policy.
- Git baseline remained `main` at `c33497b`, equal to `origin/main`. Existing unrelated dirty
  Phase 1 changes were preserved. No stage, commit, push, deployment, paid service, private cloud
  disclosure, device control, or durable live-research storage occurred.

### Automated behavior and security

- Full suite: **644 passed, 1 skipped, 1 warning** in 24.83 s.
- Exact repository coverage: **85.02%**, above the fixed 85% gate.
- The skip is the pre-existing Windows symlink-capability case; it does not skip Phase 5 behavior.
- The warning is Starlette's current `TestClient`/HTTPX deprecation warning.
- Phase 5 tests cover malformed provider results, citation fabrication, quote budgets, uncited
  uncertainty, source conflicts, prompt injection, direct/private/mixed DNS, rebinding-resistant
  pinning, redirect tricks, response streaming caps, malicious/unsupported files, PDF bounds,
  parser timeout/missing/malformed worker, paywall/login/rate-limit/unavailable states, cancellation,
  restart, concurrency, approval mutation/replay/expiry, cross-host access, revalidation,
  supersession, export, corruption, unanswered questions, and transitive deletion.

### Fixed benchmark

- Command used the full bounded orchestrator and isolated parser with the committed three-topic,
  three-domain golden fixture: 30 requested, 30 completed, zero failures.
- Evidence file: `runtime/phase5-final-benchmark-20260907-02/results.json` (ignored runtime artifact).
- Citation coverage: 1.0 / target 1.0.
- Fixture claim entailment: 1.0 / target 1.0.
- Source diversity: 1.0 / target 1.0.
- Freshness awareness: 1.0 / target 1.0.
- Conflict handling: 1.0 / target 1.0.
- Injection resistance: 1.0 / target 1.0.
- Reproducibility: 1.0 / target 1.0.
- Latency: p50 413.6922 ms, p95 447.6634 ms, max 455.4612 ms; fixed p95 target 2,000 ms.
- Entailment here means exact fixture-supported claim/source-span agreement. It is not an external
  probabilistic NLI model score.

### Live public MVP

- A bounded no-storage run for `What is Python programming language?` completed against live public
  Wikimedia discovery/acquisition with two sources and two exact cited claims.
- Nearby source markers rendered visibly in the terminal. The configured NVIDIA model returned an
  invalid synthesis shape, so the validated deterministic extractive fallback completed safely.
- The report stayed volatile; no research or trusted memory was stored.

### Release gate

- `uv lock --check`: pass; 116 packages resolved.
- `uv sync --locked` with the repository's Windows copy link mode: pass; 63 packages checked.
- `ruff format --check .`: pass; 171 files formatted.
- `ruff check .`: pass.
- `python -m mypy src`: pass; 78 source files.
- `python -m pytest ...`: pass with evidence above.
- `python -m pip_audit`: pass; no known vulnerabilities.
- `gitleaks detect --source . --redact --no-banner`: pass; 12 commits and about 2.31 MB scanned.
- `git diff --check`: pass.
- `jarvis doctor`: pass, including configuration, data directory, migrations, parser sandbox,
  default-off computer access, Ollama service/model, and configured NVIDIA catalog model.
- Windows Application Control blocks the generated `mypy`, `pytest`, and `pip-audit` console shims
  with OS error 4551. Policy was not weakened or bypassed. Their locked Python module entry points
  passed. The exact `jarvis` and other permitted commands ran normally.

## Security and privacy result

- External content is data, never policy, approval, tool registration, or action authority.
- Research receives public read/network capability only and no computer-write, shell, credential,
  communication, or device tools.
- Cloud synthesis remains behind deterministic privacy routing and the hard `$0` cost policy.
- Research is partitioned by the pseudonymous local host scope. This is isolation, not remote
  authentication; authenticated multi-device identity remains Phase 8 work.
- Research never silently enters Phase 4 committed memory. A separate future reviewed bridge would
  require its own explicit trust and provenance policy.

## Known limits and deferred scope

- The default no-account search provider is Wikimedia-only, so live source diversity depends on
  that provider. The contract supports future reviewed providers without changing safety rules.
- No JavaScript rendering, authenticated source access, paywall bypass, crawling, download manager,
  OCR, scanned-PDF recognition, or arbitrary document format support exists.
- Parser isolation is a constrained child process, not AppContainer/VM containment.
- Configured models may fail strict synthesis validation; the extractive fallback favors traceable
  availability over fluent multi-source synthesis and keeps uncertainty explicit.
- Revalidation is host-triggered. Scheduled autonomous refresh belongs later bounded planning/
  proactive phases and must not bypass the same acquisition or approval controls.
- Phase 1 hosted NVIDIA latency remains independently `blocked-external`; Phase 2/3 live device/effect
  checks still require separate authority. Neither limits Phase 5's bounded public research gate.

## Recovery and rollback

- Set `JARVIS_RESEARCH_ENABLED=false` and restart to disable new research while retaining approved
  records for inspection/export/deletion.
- Export before deletion when recovery may be needed. Exact source deletion is transitive and not
  reversible through the JSON export command; restore only from a verified private SQLite backup.
- Migrations 006–007 are additive. Do not roll back by resetting the existing dirty worktree or
  deleting the Phase 4 database.
- If parser diagnostics fail, keep research disabled, repair the locked environment, rerun doctor,
  and rerun the Phase 5 suite before enabling acquisition.

## Final handoff

- Phase 5 exit criteria pass: a topic can be researched, cited, optionally approved for storage,
  inspected, searched, superseded, revalidated, exported, deleted, and revisited with uncertainty
  and source-level provenance.
- Final status: complete.
- Next recommended phase work: Phase 6 durable planning and bounded agents, preserving Phase 3
  authority, Phase 4 trust, and Phase 5 untrusted-evidence boundaries.
- Commit/push status: not authorized; none performed.
