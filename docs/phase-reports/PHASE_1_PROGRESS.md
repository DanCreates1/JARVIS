# Phase 1 Acceptance Closeout Progress

Status: `blocked-external`
Started: 2026-08-28
Updated: 2026-09-04
Recommended Sol thinking: High

## Objective

Close the privacy-aware text vertical slice without weakening privacy, security, zero-dollar cost,
reliability, sample count, fixed latency, bootstrap, or release gates.

## Baseline and preservation

- Fresh start: branch `main`; HEAD and `origin/main`
  `c33497b1474d1867230caf5a1f4bd8489dfd73a4`; worktree clean before this continuation.
- No fetch, branch change, stage, commit, push, remote deployment, billing change, credential change,
  private cloud disclosure, destructive action, or policy bypass occurred.
- Host: Windows 11 Home build 26200; Intel i5-11400H, 6 cores/12 threads;
  16,888,967,168 bytes RAM; RTX 2050 Laptop GPU, 4,096 MiB VRAM; driver 610.62.
- Tools: uv 0.12.5; Python 3.11.16; Ollama 0.33.3; Gitleaks 8.30.1; RTK 0.45.0.
- Provider configuration was inventoried by variable name only. Hosted runs used existing explicit
  NVIDIA free-tier/trial confirmations and the hard `$0` cost cap. No secret value entered evidence.
- Runtime evidence is ignored under `runtime/`; reports contain fixture hashes and bounded
  operational metadata, never prompt/response text or credentials.

## Acceptance checklist

- [x] Provider-neutral message, tool, routing, usage, and streaming contracts.
- [x] Genuine visible-token streaming through Ollama NDJSON and NVIDIA SSE.
- [x] Router/runtime events, CLI, browser SSE, final-only persistence, cancellation, and structured
  mid-stream errors verified.
- [x] Buffered completion is not labelled TTFT. First-useful latency is the first nonblank visible
  `assistant_delta`; deterministic latency uses its persisted nonblank result.
- [x] Sensitive/uncertain content remains local; provider payloads and cloud tool schemas remain
  privacy-filtered.
- [x] Tool denial, unsupported/side-effecting tools, quota, outage, catalog removal, fallback,
  cancellation, restart, deletion, and zero-spend scenarios pass.
- [x] Deterministic state: 20/20 successful observations and fixed latency gate pass.
- [x] Local verified-cold and warm states: 20/20 successful observations each and fixed latency gate
  pass with the configuration-driven `qwen3:0.6b` local model.
- [x] Current public live smoke passes for local `nemotron-3-nano:4b`; NVIDIA Ultra catalog and live
  public streaming also pass. Active NVIDIA Lightning catalog and streaming pass.
- [x] NVIDIA hosted simple cold/warm and complex cold/warm each reached 20/20 successes with zero
  failures using compiled public fixtures.
- [ ] Fixed NVIDIA hosted latency gates pass. All four states miss at least one p50/p95 target.
- [x] Clean Windows bootstrap evidence remains reproducible on the independent runner.
- [x] Source formatting, lint, tests/coverage, dependency audit, secret scan, diff check, and doctor
  pass. Exact current-host `mypy`, `pytest`, `pip-audit`, and `jarvis` console shims remain blocked
  by Windows Application Control error 4551; locked module entry points pass, and prior clean
  Windows exact-command evidence remains valid.

## Implemented streaming path

- Added typed `ProviderStreamFrame` and `ASSISTANT_DELTA` contracts.
- Ollama uses `/api/chat` with `stream: true`, bounded NDJSON parsing, separate-thinking suppression,
  visible deltas, terminal response assembly, usage, tool calls, response-byte bounds, and transport
  cancellation.
- NVIDIA uses OpenAI-compatible SSE with `stream: true`, separate `reasoning_content` suppression,
  visible deltas, fragmented tool-call assembly, usage, `[DONE]` validation, response-byte bounds,
  concurrency/rate limits, and transport cancellation.
- Router emits the selected/fallback route before provider frames. Retry/fallback is allowed only
  before the first provider frame; partial output is never combined with another provider.
- Runtime emits ordered deltas but persists only the validated terminal assistant response.
  Cancellation or a mid-stream provider failure persists no partial assistant message.
- CLI renders deltas live without duplicating the terminal reply. Browser page consumes the
  loopback POST SSE interface; typed JSON chat remains available.
- Groq/Gemini remain provider-neutral terminal-frame adapters. No genuine-token claim is made for
  those adapters.

## Local optimization

Fixed settings used for the final local gate:

- model: `qwen3:0.6b`
- digest: `7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435`
- size: 522,653,767 bytes; Q4_K_M; tools/thinking capabilities
- active context: 4,096 tokens
- maximum output: 512 tokens
- keep-alive: `5m`
- verified cold: `ollama stop` plus `/api/ps` absence before every observation; OS caches not flushed
- warm: one excluded warm-up, same runtime/client, model residency verified

Comparative genuine-TTFT evidence:

| Model/settings | Cold p50/p95 | Warm p50/p95 | Result |
| --- | ---: | ---: | --- |
| Nemotron Nano 4B, 4K | 7,304.644/9,260.436 ms | 964.546/2,746.125 ms | Cold fail; warm pass |
| Qwen 2.5 3B, 4K | 3,416.946/3,833.340 ms | 49.409/579.827 ms | Cold fail; warm pass |
| Qwen3 1.7B, 4K | 2,942.449/3,432.295 ms | 34.183/411.135 ms | Cold fail; warm pass |
| Qwen3 1.7B, 2K | 2,706.817/3,122.634 ms | 36.285/424.831 ms | Cold fail; warm pass |
| Qwen3.5 0.8B, 4K | 2,978.988/3,761.379 ms | 155.738/532.889 ms | Cold fail; warm pass |
| Qwen3 0.6B, 4K final | 1,233.312/1,453.556 ms | 25.374/212.986 ms | PASS/PASS |

All candidate reports contain 20 successful cold and 20 successful warm observations. Context was
not reduced below 2K merely to pass. The selected 4K model passed a live exact-output smoke and
issued a real read-only file tool call that independently failed closed outside configured roots.
Current Nemotron Nano compatibility smoke returned exactly `NEMOTRON NANO LIVE` through the
production CLI streaming path.

## Final deterministic and local evidence

Evidence: `runtime/phase1-benchmark-20260901-final-local-01/phase1-benchmark.json`

| State | Success/failure | First-useful p50 | p95 | Fixed target | Result |
| --- | ---: | ---: | ---: | --- | --- |
| Deterministic steady | 20/0 | 5.329 ms | 6.621 ms | 300/800 ms | PASS |
| Local verified cold | 20/0 | 1,233.312 ms | 1,453.556 ms | 1,500/3,000 ms | PASS |
| Local warm resident | 20/0 | 25.374 ms | 212.986 ms | 1,500/3,000 ms | PASS |

Nearest-rank quantiles are used. Final local completion p50/p95 was 1,473.186/1,808.234 ms cold
and 218.119/394.576 ms warm. Benchmark enforcement exited successfully with all three required
states complete.

## Hosted NVIDIA evidence and blocker

Final evidence:
`runtime/phase1-benchmark-20260904-nvidia-lightning-bounded-02/phase1-benchmark.json`

Exact configured model: `nvidia/nemotron-3.5-lightning-30b-a3b`. Catalog validation passed. The
adapter used genuine OpenAI-compatible SSE and counted the first nonblank visible assistant delta,
never hidden `reasoning_content` or buffered completion. Only compiled public fixtures were sent.

Exact settings: 1,024 maximum output tokens, 256 non-reasoning output tokens, 256 hidden-reasoning
budget tokens, one concurrent request, local 30-request/minute guard, 60-second total stream
deadline, and bounded serial execution. Simple used `ReasoningLevel.NONE`/thinking disabled;
complex used `ReasoningLevel.DEEP`/thinking enabled.

| Required state | Success/failure | Visible TTFT p50 | p95 | Fixed target | Result |
| --- | ---: | ---: | ---: | --- | --- |
| Simple cold-client | 20/0 | 2,076.445 ms | 4,304.367 ms | 1,000/2,500 ms | FAIL |
| Simple warm-client | 20/0 | 1,179.622 ms | 37,975.215 ms | 1,000/2,500 ms | FAIL |
| Complex cold-client | 20/0 | 2,172.771 ms | 11,608.523 ms | 3,000/7,000 ms | FAIL |
| Complex warm-client | 20/0 | 3,607.162 ms | 10,243.188 ms | 3,000/7,000 ms | FAIL |

Nearest-rank quantiles are used. All 80 required observations succeeded on the requested provider
with no fallback, so sample count and capacity errors no longer block. Provider tail latency still
fails the immutable Phase 1 gate. An earlier Lightning run independently completed all states with
zero failures and also failed all p95 targets; Ultra retains current public catalog/live-streaming
compatibility evidence but was materially slower in benchmark evidence.

This is the sole Phase 1 completion blocker. A `PHASE_1_COMPLETION.md` was not created and progress
was not retired.

## Scenario and release verification

Focused Phase 1 suite after streaming/default changes:

```text
120 passed, 1 upstream Starlette deprecation warning
```

Full repository suite after final hosted-model/deadline changes:

```text
rtk uv run python -m pytest
PASS: 543 passed, 1 skipped, 1 warning; coverage 85.01% (required 85%)
```

The skip is the existing Windows capability-dependent directory-symlink case. Full tests cover
privacy routes/overrides, cloud-schema filtering, tool denial, unsupported and side-effecting tool
fail-closed behavior, quota/outage/catalog removal, zero spend, restart, deletion, cancellation,
stream ordering, final-only persistence, and mid-stream error behavior.

Current-host release gate:

```text
rtk uv lock --check                         PASS: 115 packages
rtk uv sync --locked                        PASS
rtk uv run ruff format --check .            PASS: 148 files
rtk uv run ruff check .                     PASS
rtk uv run mypy src                         BLOCKED: Windows Application Control, OS 4551
rtk uv run python -m mypy src               PASS: 66 source files
rtk uv run pytest                           BLOCKED: Windows Application Control, OS 4551
rtk uv run python -m pytest                 PASS: 543 passed, 1 skipped, 85.01% coverage
rtk uv run pip-audit                        BLOCKED: Windows Application Control, OS 4551
rtk uv run python -m pip_audit              PASS: no known vulnerabilities
rtk gitleaks detect --source . --redact ... PASS: 12 commits, 2.31 MB, no leaks
rtk git diff --check                        PASS
rtk uv run jarvis doctor                    BLOCKED: Windows Application Control, OS 4551
rtk uv run python -X utf8 -m jarvis doctor  PASS; Qwen local and NVIDIA Lightning catalog healthy
```

The exact console-launcher blocks are host policy, not code/test failures; no bypass was attempted.
Independent clean Windows run 33467300560 previously passed the exact commands with uv 0.12.5 and
Python 3.11.16. Current lock, complete module-entry release gate, and doctor were revalidated on
2026-09-04. `scripts/bootstrap.ps1` remains unchanged; `scripts/setup-model.ps1` changes only the
configuration-driven latency-qualified local-model default and bounded Ollama settings.

## Smallest external action

Retry the same public-only, zero-dollar hosted command when NVIDIA free-endpoint tail latency
improves. Sample count already passes. Completion requires every fixed p50/p95 target to pass. If
the endpoint continues producing 4–38 second p95 visible TTFT, completion requires NVIDIA service
improvement or separately authorized replacement hardware/provider that still satisfies zero cost
and public-only disclosure. No local code, threshold, privacy rule, or sample-count change can
honestly convert current evidence to a pass.

## Recovery

- Runtime benchmark artifacts remain ignored and were not deleted.
- Additional Ollama candidate models were downloaded outside Git and may be removed later through a
  separately authorized cleanup; no model artifact is committed.
- Revert only Phase 1 streaming/default/documentation hunks if rollback is required. Do not reset
  unrelated repository state.
- No database schema migration was required. Existing persisted messages remain compatible.
