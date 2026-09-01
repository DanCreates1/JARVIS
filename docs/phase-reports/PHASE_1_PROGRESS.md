# Phase 1 Acceptance Closeout Progress

Status: `blocked-external`
Started: 2026-08-28
Updated: 2026-08-31
Recommended Sol thinking: High

## Objective

Formally close the privacy-aware text vertical slice with current functional, failure, security,
restart, deletion, provider, benchmark, bootstrap, and release evidence. Preserve all pre-existing
Phase 1–4 work. Do not weaken privacy, cost, latency, clean-machine, or release gates.

## Baseline and preservation

- Branch `main`, HEAD and `origin/main` both
  `7d32b9378f024e41a250d0864bf4dafca7dd4df1`; no fetch, branch change, stage, commit, or push.
- Before this closeout continuation, 45 tracked files were modified and 87 paths were untracked.
  All dirty-file timestamps predated this request. Ignored handoff manifests show the layered
  Phase 1–4 provenance. Shared files were patched by hunk; no dirty file was reset or replaced.
- Windows 11 Home build 26200; Intel i5-11400H, 6 cores/12 threads; 16,888,967,168 bytes RAM;
  RTX 2050 Laptop GPU, 4,096 MiB VRAM; NVIDIA driver 610.62.
- Project runtime: Python 3.11.16, uv 0.12.5, Ollama 0.33.2, Gitleaks 8.30.1.
- RTK remains blocked by Windows Smart App Control at
  `C:\Users\poyan\.local\bin\rtk.exe`. Required commands therefore use the explicitly allowed
  direct-command fallback. No policy change or execution bypass was attempted.

## Acceptance checklist

- [x] Functional routes and direct deterministic time command are current-test verified.
- [x] Failure, cancellation, restart/deletion, quota/outage/removal, and zero-spend scenarios are
  current-test verified with fakes/contracts.
- [x] Privacy routing and tool denial are current-test verified, including truncated legacy
  assistant/tool history, tool arguments, provider payloads, and SQLite label persistence.
- [x] Deterministic benchmark has 20 current successful samples and passes its fixed target.
- [x] Local benchmark has 20 verified-cold and 20 warm successful samples with honest p50/p95.
- [ ] Local cold/warm latency meets the fixed 1,500/3,000 ms p50/p95 target.
- [ ] Current hosted NVIDIA run yields 20 cold-client and 20 warm-client successful samples per
  simple/complex profile. Production requests timed out and failed closed before sampling.
- [ ] Bootstrap is reproduced on a genuinely fresh Windows 10/11 OS image. Current-host fresh
  environment rehearsal passes, but it is not clean-OS evidence.
- [ ] Integrated exact-command release gate passes. Current substantive locked checks pass, but
  WinGet `uv.exe` and generated `mypy`, `pytest`, `pip-audit`, and `jarvis` shims are blocked by
  Windows Application Control; exact commands remain externally blocked.

## Implemented closeout fixes

1. Corrected `get_current_time` and `get_system_status` structured-result leaf caps from one to
   their real maximums (3 and 8). Runtime previously rejected valid tool output.
2. Added the missing deterministic phrase `Please tell me the time.` to the fixed time grammar.
3. Made Ollama honor core reasoning policy with explicit `think: false` for `ReasoningLevel.NONE`
   and `think: true` for reasoning requests. Ollama enables thinking by default for supported
   models; the prior adapter silently ignored the requested level.
4. Added durable disclosure sensitivity/source labels to provider-neutral messages. User,
   assistant, tool, static-system, and memory-projection messages now receive local provenance.
5. Router now scans all disclosed message content plus canonical tool-call arguments. Unlabelled
   legacy assistant/tool/system history is `UNKNOWN` and local-only. A trusted public label can
   suppress heuristic ambiguity, but a deterministic private match always overrides it.
6. Changed unmatched nonblank privacy input from implicitly public to conservative `UNKNOWN`.
   Bounded general-query forms remain public; deictic, confidential, internal, client, patient,
   employee, attachment, and multiline content stays local unless deterministically proven public.
7. Corrected hosted benchmark fixtures and added a preflight proving every compiled hosted fixture
   classifies `PUBLIC` before any network call.
8. Retained OneDrive-safe `uv sync --locked --link-mode copy` bootstrap behavior and Nemotron local
   default in the model setup script.

## Verification evidence

### Focused Phase 1 suite

```text
uv run --locked python -m pytest -q --no-cov \
  tests/unit/test_bootstrap.py tests/unit/test_cli.py tests/unit/test_config.py \
  tests/unit/test_diagnostics.py tests/unit/test_phase_one_tools.py \
  tests/unit/test_policy.py tests/unit/test_routing.py tests/unit/test_runtime.py \
  tests/unit/test_phase1_acceptance_script.py tests/contract/test_cloud_providers.py \
  tests/contract/test_ollama.py tests/integration/test_sqlite_store.py \
  tests/integration/test_web.py
PASS: 115 tests; 1 upstream Starlette TestClient deprecation warning; 1.78 s.
```

Focused post-fix lint and types:

```text
uv run --locked ruff check <changed Phase 1 files>
PASS
uv run --locked python -m mypy src
PASS: 66 source files
```

Smart App Control blocks the unsigned `pytest.exe` launcher used by exact `uv run pytest` with OS
error 4551. The same locked Python 3.11 environment executes `python -m pytest` successfully. This
does not make the exact-command release gate pass; both results remain visible.

### Integrated repository gate — 2026-08-31

```text
uv lock --check                              BLOCKED: WinGet uv.exe access denied
.bootstrap-venv uv lock --check              PASS: 115 packages
uv sync --locked                             BLOCKED: WinGet uv.exe access denied
.bootstrap-venv uv sync --locked             PASS: base environment synchronized
uv run ruff format --check .                 PASS via allowed uv: 147 files
uv run ruff check .                          PASS via allowed uv
uv run mypy src                              BLOCKED: OS error 4551
uv run --locked python -m mypy src           PASS: 66 source files
uv run pytest                                BLOCKED: OS error 4551
uv run --locked python -m pytest --basetemp  PASS: 530 passed, 1 skipped, 85.20% coverage
uv run pip-audit                             BLOCKED: OS error 4551
uv run --locked python -m pip_audit          PASS: no known vulnerabilities
gitleaks detect --source . --redact ...      PASS: 8 commits, 716.89 KB, no leaks
git diff --check                             PASS: line-ending notices only
uv run jarvis doctor                         BLOCKED: OS error 4551
uv run --locked python -m jarvis doctor      PASS: every diagnostic; JARVIS ready
```

The optional locked voice environment was restored after the base sync and also reports no known
vulnerabilities. The sole skip remains the non-elevated Windows directory-symlink case
(`WinError 1314`); the sole warning is upstream Starlette `TestClient` deprecation.

### Privacy/security regressions added

- Unlabelled orphan assistant/tool history after message-count truncation forces local routing.
- Labelled public history can use cloud, but private content overrides a bad public label.
- Canonical tool-call arguments are scanned before disclosure.
- Ollama provider payloads exclude internal sensitivity/provenance metadata.
- SQLite restart preserves disclosure labels.
- Sensitive and uncertain override requests remain local; cloud tool schemas remain public-only.
- Result byte/leaf limits, unsupported tools, side-effect broker requirement, timeout,
  cancellation, provider failure, and zero-dollar usage enforcement remain covered.

## Benchmarks

All reports are ignored under `runtime/`; they contain fixture hashes and bounded operational
metadata, never prompt/response text or credentials. Quantiles are nearest-rank.

### Final deterministic evidence

Evidence: `runtime/phase1-benchmark-20260831-03/phase1-benchmark.json`

| State | Samples | Success | Failures | p50 | p95 | Target | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Steady deterministic | 20 | 20 | 0 | 6.204 ms | 6.691 ms | 300/800 ms | PASS |

All 20 used the deterministic path; no model ran.

### Final local evidence

Evidence: `runtime/phase1-benchmark-20260831-04/phase1-benchmark.json`

| State | Samples | Success | Failures | p50 | p95 | Target | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Verified cold | 20 | 20 | 0 | 9,477.214 ms | 10,927.172 ms | 1,500/3,000 ms | FAIL |
| Warm resident | 20 | 20 | 0 | 2,344.215 ms | 4,078.548 ms | 1,500/3,000 ms | FAIL |

- Cold eviction verified 20/20 with `ollama stop` plus `/api/ps` absence; OS caches were not
  flushed. All 40 observations used Ollama with no route failure.
- Model `nemotron-3-nano:4b`, digest
  `6cc467f054393a55e98a74098abde0c762ffb6d1d8cd64becf30458f38886197`,
  2,837,597,147 bytes, 3,973,556,832 parameters, Q4_K_M, tools and thinking.
- Declared artifact context is 262,144; observed active Ollama context was 4,096. Adapter responses
  remain buffered, so measured first-useful output equals complete-response latency, not TTFT.
- Host before/after: GPU 0/2,289 MiB; 41/62 C; 10.18/28.14 W snapshot; available RAM
  2,729,299,968/2,145,206,272 bytes. These are endpoint snapshots, not sampled peaks.
- Earlier preserved runs show the fixes' effect:
  - pre-fix: deterministic 0/20 due tool cap; local cold 11,153.715/15,331.710 ms,
    warm 6,925.224/16,116.059 ms;
  - after tool/thinking fix but before grammar/privacy closeout: deterministic 15/20,
    local cold 7,610.182/9,838.166 ms, warm 2,308.359/4,376.473 ms.

The current local path is functionally reliable but does not meet the declared interactive latency
gate on this hardware. Targets were not moved.

### Hosted NVIDIA evidence

Evidence: `runtime/phase1-benchmark-20260831-05/phase1-benchmark.json`

- Existing private configuration was verified without printing the secret: key configured,
  free-tier confirmation true, prior trial-terms acknowledgement true, cost cap exactly `$0`,
  model `nvidia/nemotron-3-ultra-550b-a55b`.
- Exact model catalog validation passed before each profile.
- No current inference completed on NVIDIA. The first simple observation exhausted bounded
  production timeouts and fell back local; total observation time 121,557.453 ms. Harness stopped
  the profile immediately.
- One complex observation was correctly rejected local after the new conservative gate exposed an
  ambiguous fixture; that fixture is now removed and guarded by tests. The next valid public
  complex observation also timed out/fell back; total 157,586.284 ms. Harness stopped immediately.
- Current successful hosted samples: 0 simple cold, 0 simple warm, 0 complex cold, 0 complex warm.
  No quota ceiling was probed, no paid path exists, and no sensitive content was sent.
- Historical August 22 three-run hosted smoke timings remain historical only; they do not replace
  current 20-sample acceptance.

## Bootstrap and clean Windows

Current-host fresh environment rehearsal:

```text
UV_PROJECT_ENVIRONMENT=runtime/phase1-bootstrap-20260831-01
./scripts/bootstrap.ps1
PASS: Python 3.11 already installed; 115 packages resolved; 62 locked packages installed
      using copy mode in 4.02 s.
runtime/phase1-bootstrap-20260831-01/Scripts/python.exe --version
PASS: Python 3.11.16
fresh Python import jarvis, fastapi, httpx, pydantic
PASS: imports-ok
```

This is useful bootstrap regression evidence, not a clean Windows result: it reused the laptop OS,
user profile, uv/Python cache, source checkout, and network/tool installation. Windows 11 Home has
no Windows Sandbox feature; Hyper-V/VMware/VirtualBox/WSL guests are unavailable. No VM, account,
license, download, remote machine, or security-policy change was authorized or created.

## External blockers

1. **Clean Windows target unavailable.** Provide an approved genuinely fresh Windows 10/11 VM or
   disposable machine with documented image/reset provenance and policy-permitted Python/uv.
2. **NVIDIA trial endpoint did not complete production requests.** Retry only after provider
   capacity is available; keep public fixtures, existing zero-dollar policy, 2.1-second pacing,
   60-second production timeout, and fail-closed stop. Do not probe quota ceilings.
3. **Local latency misses on target hardware.** Completing this gate requires a measured adapter
   streaming/preload improvement or stronger approved hardware. Buffered completion cannot be
   relabelled TTFT, and cold model load cannot be called passing.
4. **RTK/exact launcher policy.** RTK and some generated console launchers are blocked by Smart App
   Control. Direct commands are the authorized fallback for substantive testing, but exact release
   command results must remain documented.

## Known limits and deferred scope

- Ollama adapter still buffers full responses and has no current local output-token setting; the
  60-second timeout and HTTP/result validation remain the primary bound.
- Benchmark corpus has four fixed prompts per profile repeated to 20 observations; it measures
  latency/routing success, not broad answer quality. Hosted digest is not published; record exact
  model ID/version/catalog date instead.
- Current-host bootstrap does not prove a clean OS, empty caches, installer prerequisites, or PATH
  behavior on another Windows machine.
- Phase 2–4 revalidation and integrated release evidence are recorded in their own reports.

## Recovery and rollback

- Runtime benchmark/bootstrap artifacts are ignored and can be removed only after resolving and
  verifying their exact workspace-local paths. No cleanup was performed.
- To revert this continuation, reverse only the explicit hunks in Phase 1 routing, runtime,
  provider, tool, benchmark, tests, and documentation. Do not restore whole dirty files from HEAD.
- No database migration was required: messages already persist versioned Pydantic payload JSON;
  new optional fields remain compatible with legacy rows, which deliberately fail local.

## Final handoff

- Final status: `blocked-external`; no `PHASE_1_COMPLETION.md` exists.
- Safe local work completed: correctness/privacy fixes, 115-test suite, deterministic/local
  benchmarks, bounded hosted attempt, and fresh current-host bootstrap rehearsal.
- Next action: supply a clean approved Windows target and retry hosted inference when NVIDIA
  capacity is healthy; separately improve local streaming/preload latency without relaxing targets.
- Worktree remains uncommitted and unstaged.
