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
- RTK 0.45.0 now runs normally. Windows Smart App Control still blocks generated `mypy`, `pytest`,
  `pip-audit`, and `jarvis` console shims with OS error 4551. Allowed Python-module equivalents
  and independent exact-command CI evidence are both retained; no policy bypass was attempted.

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
- [x] Bootstrap is reproduced on a fresh independent GitHub `windows-latest` runner through the
  repository script, with uv 0.12.5, Python 3.11.16, and the locked environment.
- [x] Independent exact-command repository gate passes in CI: lock, sync, format, lint, mypy,
  pytest, pip-audit, and complete-history Gitleaks. Current-host module equivalents and doctor also
  pass; current-host generated console shims remain an environment limitation.

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
error 4551. The same locked Python 3.11 environment executes `python -m pytest` successfully. Both
results remain visible; the independent fresh Windows runner now supplies passing exact-command
evidence.

### Integrated repository gate — 2026-08-31

Independent fresh Windows evidence:

```text
GitHub Actions run 33467300560, commit 1f75017531a8e31d9119d10dfb088a9c19effc67
scripts/bootstrap.ps1                         PASS: Python 3.11.16; 115 resolved; 62 checked
uv lock --check / uv sync --locked            PASS
uv run ruff format --check .                  PASS: 148 files
uv run ruff check .                           PASS
uv run mypy src                               PASS: 66 source files
uv run pytest                                 PASS: 535 passed, 1 skipped, 85.09% coverage
uv run pip-audit                              PASS: no known vulnerabilities
complete-history Gitleaks job                 PASS
```

The capability skip is the directory-symlink negative on a runner without that host capability;
all other tests pass. The sole warning is the upstream Starlette `TestClient` deprecation.

Final current-host evidence after documentation reconciliation:

```text
rtk uv lock --check                          PASS: 115 packages
rtk uv sync --locked                         PASS: base environment synchronized
rtk uv run ruff format --check .             PASS: 148 files
rtk uv run ruff check .                      PASS
rtk uv run mypy src                          BLOCKED: OS error 4551
rtk uv run python -m mypy src                PASS: 66 source files
rtk uv run pytest                            BLOCKED: OS error 4551
rtk uv run python -m pytest                  PASS: 535 passed, 1 skipped, 85.24% coverage
rtk uv run pip-audit                         BLOCKED: OS error 4551
rtk uv run python -m pip_audit               PASS: no known vulnerabilities
rtk gitleaks detect --source . --redact ...  PASS: 11 commits, 2.30 MB, no leaks
rtk git diff --check                         PASS
rtk uv run jarvis doctor                     BLOCKED: OS error 4551
rtk uv run python -m jarvis doctor           PASS: every diagnostic; JARVIS ready
rtk uv sync --locked --extra voice           PASS: optional voice environment restored
voice dependency audit and voice doctor      PASS: no vulnerabilities; every diagnostic healthy
```

The voice doctor found 26 capture and 30 render endpoints, verified the persisted microphone and
speaker, and passed local VAD/STT/TTS/openWakeWord health checks. The sole skip remains the
non-elevated Windows directory-symlink case (`WinError 1314`); the sole warning is upstream
Starlette `TestClient` deprecation.

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

Evidence: `runtime/phase1-benchmark-20260831-06/phase1-benchmark.json`

- Existing private configuration was verified without printing the secret: key configured,
  free-tier confirmation true, prior trial-terms acknowledgement true, cost cap exactly `$0`, and
  model `nvidia/nemotron-3-ultra-550b-a55b`. Exact catalog validation passed before each profile.
- Simple cold-client: 10 observations, 9 NVIDIA successes and one local fallback; successful p50
  `1,584.476 ms`, p95 `5,790.438 ms`, versus fixed `1,000/2,500 ms`. The harness stopped on the
  first capacity/fallback signal, so no simple warm state was started.
- Complex cold-client: 20/20 NVIDIA successes; p50 `22,227.169 ms`, p95 `43,157.135 ms`, versus
  fixed `3,000/7,000 ms`.
- Complex warm-client: 7 observations, 6 NVIDIA successes and one local fallback; successful p50
  `11,025.118 ms`, p95 `46,278.779 ms`. The harness stopped on the first fallback.
- Three of four required states were observed, but only complex cold reached 20 successes. None met
  its latency target. No quota ceiling was probed, no paid path exists, and no sensitive content
  was sent. The endpoint is usable intermittently but does not satisfy current capacity/latency
  acceptance.

## Bootstrap and clean Windows

Independent fresh Windows evidence:

```text
GitHub Actions run 33467300560 on windows-latest
setup-uv 0.12.5 + uv-managed CPython 3.11.16
uv lock --check; uv sync --locked; ./scripts/bootstrap.ps1
PASS: 115 locked packages resolved; 62 packages checked; bootstrap ready message emitted
```

The same clean checkout then passed exact format, lint, mypy, pytest, and dependency audit
commands; a separate complete-history Gitleaks job passed. This resolves the independent Windows
bootstrap/repository-gate requirement.

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

This remains useful host-specific regression evidence. The independent CI run supplies the clean
Windows result without creating a VM, account, license, remote deployment, or policy bypass.

## External blockers

1. **NVIDIA capacity and latency remain insufficient.** The endpoint completed 35 current public
   fixture requests but fell back twice before every state reached 20 successes, and all measured
   hosted p50/p95 values missed their fixed targets. Retry with the same zero-dollar policy,
   2.1-second pacing, bounded timeouts, and fail-closed stop. Do not probe quota ceilings.
2. **Local latency misses on target hardware.** Completing this gate requires a measured adapter
   streaming/preload improvement or stronger approved hardware. Buffered completion cannot be
   relabelled TTFT, and cold model load cannot be called passing.
3. **Current-host launcher policy.** RTK and uv run, but generated console launchers remain blocked
   by Smart App Control. Allowed module entry points pass locally and exact commands pass on the
   independent Windows runner; no host policy was changed.

## Known limits and deferred scope

- Ollama adapter still buffers full responses and has no current local output-token setting; the
  60-second timeout and HTTP/result validation remain the primary bound.
- Benchmark corpus has four fixed prompts per profile repeated to 20 observations; it measures
  latency/routing success, not broad answer quality. Hosted digest is not published; record exact
  model ID/version/catalog date instead.
- Hosted-runner bootstrap proves a fresh Windows checkout and toolchain, not this laptop's exact
  OEM drivers, Ollama/GPU stack, or Smart App Control policy.
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
- Next action: improve local streaming/preload latency and retry NVIDIA only when capacity is
  healthy, without relaxing targets. Clean-Windows/bootstrap evidence is now complete.
- Phase 1–4 implementation, CI hardening, and final evidence reconciliation are committed and
  pushed to `origin/main`; remote SHA verification is recorded in the final handoff.
