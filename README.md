# JARVIS

JARVIS is a privacy-aware hybrid assistant for Windows. Phases 1–6 implement a
local deterministic privacy gate, configurable NVIDIA/Groq/Gemini/Ollama roles,
zero-cost fallback routing, durable SQLite state, audited read-only tools, CLI,
loopback browser chat, local push-to-talk speech, opt-in controlled Windows actions, bounded cited
public research, and durable budgeted task graphs. Sensitive and uncertain work remains local.

This repository is the source of truth for the project. Local model weights,
runtime databases, logs, generated media, and secrets do not belong in Git.

## Current verification status

As of 2026-09-07, Phases 4–6 are complete. Phase 1 genuine Ollama/NVIDIA token streaming and the
optimized local latency gate pass; Phase 1 remains blocked only by fixed hosted NVIDIA latency
gates. All four hosted states have 20 successful public-fixture observations, but measured p50/p95
still exceed one or both fixed targets. Clean-Windows bootstrap and exact repository quality gates
pass on an independent fresh GitHub Windows runner. Phases 2 and 3 pass current safe local gates but
still require separately authorized current real-device/application smokes. See
[Phase Overview](docs/PHASE_OVERVIEW.md) and the phase reports for exact evidence. No threshold or
privacy/authority gate is waived by implementation status.

## Implemented Phase 1

The supported text vertical slice can:

- validate local storage, Ollama, configured cloud credentials, and live model catalogs;
- chat interactively from a terminal;
- chat from a loopback-only browser page and JSON/SSE API;
- stream visible Ollama/NVIDIA token deltas through CLI and browser SSE while persisting only the
  validated final assistant message;
- send one non-interactive message;
- route safe simple, normal, and difficult work across logical model roles;
- keep credentials, files, memory, communications, personal data, and uncertain content local;
- fall back on quota, model removal, or outage without entering paid service;
- persist and explicitly delete conversations and basic memory records; and
- expose only schema-validated, policy-approved read-only clock, system-status, and allowlisted
  text-file tools with audit records.

## Implemented Phase 2

The optional local voice slice adds:

- explicit push-to-talk with visible capture state and a persistent software kill switch;
- provider-neutral audio, VAD, STT, TTS, wake-word, and output contracts;
- CPU/int8 faster-whisper, Silero VAD, Windows SAPI speech, and optional openWakeWord ONNX;
- persisted stable input/output endpoint selection and voice diagnostics;
- phrase-streamed output, speech interruption, render-reference suppression, cancellation,
  bounded audio/events, and text fallback; and
- a local WER/latency/trigger/barge-in/device/soak benchmark harness.

Wake-word and clap always-listening are hard-disabled in configuration. Detection foundations emit
untrusted typed intents; they cannot approve or execute a computer action. Vision, remote network
access, general desktop automation, and graphical clients remain later milestones.

## Implemented Phase 3

Controlled computer access adds:

- dual default-off host gates and a dedicated controlled-file root;
- deterministic permission Levels 0–4, with Levels 3–4 unavailable in shipped policy;
- exact trusted-terminal approval, expiring one-use grants, restart-safe SQLite authority state,
  append-only sanitized lifecycle audit, and live policy kill checks;
- fixed enrolled app/app-group launch, Core Audio volume, global media keys, bounded clipboard,
  configured browser targets, filename search, printer status, controlled text printing, and one
  reversible same-volume file move;
- file/executable identity and SHA-256 revalidation, no shell/elevation, output/time limits,
  postcondition evidence, guarded recovery, cancellation receipts, and hostile-input tests; and
- an allowlisted acoustic-intent proposal gate that never grants authority.

Computer actions are disabled by default. See
[Controlled Computer Access](docs/CONTROLLED_COMPUTER_ACCESS.md) before enabling either gate.

## Implemented Phase 4

Durable memory adds:

- host-isolated working, episodic, profile, semantic, and task records in SQLite;
- extraction candidates that cannot enter retrieval until exact trusted confirmation;
- typed provenance, trust, confidence, sensitivity, retention, correction lineage, conflicts,
  derivation links, append-only events, and content-free deletion tombstones;
- SQLite FTS5 retrieval with relevance, recency, confidence, and trust scoring plus bounded prompt
  projection and visible retrieval reasons;
- explicit remember, promote, reject, correct, conflict-resolution, retention, export, expiry, and
  transitive-forget workflows in the CLI and loopback API; and
- golden, poisoning, contradiction, host-isolation, migration, backup/restore, corrupt-record,
  concurrency, performance, storage-growth, and deletion-completeness tests.

Private or unknown retrieved context forces local routing. FTS5 met the declared quality and
latency targets, so no embedding model, vector extension, or external memory service was added.

## Implemented Phase 5

Research and self-education adds:

- provider-neutral discovery, acquisition, parsing, synthesis, citation, and storage contracts;
- public-DNS validation, validated-IP/SNI-pinned HTTPS fetching, manual redirects, and hard
  source/domain/byte/time/content limits;
- short-lived isolated HTML/plain/PDF parsing with no action tools and bounded PDF resources;
- exact source-span citations, visible uncertainty/conflicts, and deterministic extractive fallback;
- volatile-by-default runs plus exact one-use host approval for a separate untrusted research ledger;
- host-scoped inspection, FTS5 search, supersession, revalidation, unanswered questions, exclusive
  export, and transitive deletion through CLI and loopback browser/API; and
- a fixed 30-sample benchmark covering citation, entailment, diversity, freshness, conflicts,
  injection resistance, reproducibility, failure rate, and latency.

## Implemented Phase 6

Planning and bounded tasks add:

- immutable validated DAGs with owner, host, provenance, deadline, dependencies, budgets, attempts,
  outputs, checkpoints, and ordered lifecycle events;
- hard ceilings for steps, wall time, tokens, provider requests, retries, tool calls, zero cloud
  cost, and four-way read-only concurrency;
- explicit foreground execution, pause/resume/cancel, classified retries, partial failure,
  compensation hooks, and restart reconciliation without blind effect replay;
- approved-research metadata inspection and exact Phase 3 one-use grant execution through fixed
  handlers; and
- CLI lifecycle/export/deletion controls plus loopback preview/inspection/pause/cancel endpoints.

Task execution is disabled by default. See [Bounded Tasks](docs/BOUNDED_TASKS.md).

## Model strategy

| Role | Target default | Use |
| --- | --- | --- |
| `FAST` | Groq `openai/gpt-oss-20b` | Safe simple requests and safe ambiguous intent |
| `PRIMARY` | Groq preview `qwen/qwen3.6-27b` | Safe normal conversation and tool planning |
| `REASONING` | NVIDIA `nvidia/nemotron-3.5-lightning-30b-a3b` | Safe difficult public reasoning, coding, research, long context, and tools |
| `LOCAL` | Ollama `qwen3:0.6b` | Normal/private requests, offline operation, cloud fallback |

A deterministic local gate must classify sensitivity before any cloud request.
Initial cloud spend is hard-capped at `$0`; quota exhaustion, outage, or model
retirement falls back to another free/local role or returns a capacity error.
NVIDIA trial APIs must never receive sensitive, confidential, or personal content;
the local privacy gate keeps that work on Ollama. Model IDs and access are checked
against live provider catalogs at startup.

All mappings are configuration-driven. Without confirmed free-tier credentials,
cloud roles remain disabled and every request uses local Ollama. `jarvis doctor`
checks configured model IDs against live provider catalogs without printing keys.

## Requirements

- Windows 10 or Windows 11
- PowerShell 5.1 or newer
- Git
- [`uv`](https://docs.astral.sh/uv/)
- [Ollama for Windows](https://ollama.com/download/windows)
- Optional NVIDIA API Catalog trial key for the difficult-work cloud role

Python 3.11 is selected by `.python-version` and can be installed by `uv`. Do not
install Python packages globally.

## Quick start

```powershell
git clone https://github.com/DanCreates1/JARVIS.git
Set-Location JARVIS
./scripts/bootstrap.ps1
./scripts/setup-model.ps1
```

The default local model is `qwen3:0.6b`. `nemotron-3-nano:4b` remains a supported live-smoke
compatibility model. Then verify the installation:

```powershell
uv run jarvis doctor
```

Start an interactive session:

```powershell
uv run jarvis chat
```

Or start loopback browser chat:

```powershell
uv run jarvis serve
```

Or send a single message:

```powershell
uv run jarvis chat --message "Summarize what you can do."
```

Inspect and manage durable memory locally:

```powershell
uv run jarvis memory list
uv run jarvis memory search "printer preference"
uv run jarvis memory remember profile "Prefer concise responses" --key profile.response-style
uv run jarvis memory export .\jarvis-memory-export.json
```

Use `uv run jarvis memory --help` for confirmation, correction, conflict, retention, expiry, and
forget commands. Exports use exclusive creation and never overwrite an existing file.

Run bounded public research. Results are volatile unless `--store` explicitly approves the exact
displayed report:

```powershell
uv run jarvis research run "What is Python?" --max-sources 3 --max-fetches 6
uv run jarvis research run "What is Python?" --store
uv run jarvis research list
uv run jarvis research search "Python"
uv run jarvis research export .\jarvis-research-export.json
```

Use `uv run jarvis research --help` for report inspection, source revalidation, unanswered
questions, and exact source deletion. External text and PDFs remain untrusted; stored research is
kept separate from trusted memory.

Install and set up optional local voice support:

```powershell
uv sync --locked --extra voice
uv run jarvis voice setup
uv run jarvis voice devices
uv run jarvis voice select --input-device-id <stable-input-id> --output-device-id <stable-output-id>
uv run jarvis voice doctor
uv run jarvis voice enable
uv run jarvis voice push-to-talk
uv run jarvis voice disable
```

`voice setup` explicitly downloads public STT/wake assets to private application-data storage.
Raw microphone PCM stays in memory for the bounded turn and is discarded. `voice disable` is the
software kill command; text chat keeps working.

If `uv` is not installed and Windows Package Manager is available, installation
can be requested explicitly:

```powershell
./scripts/bootstrap.ps1 -InstallUv
```

The bootstrap script never installs Ollama or downloads a model implicitly.

## Configuration

JARVIS uses environment variables prefixed with `JARVIS_`. Copy the example only
when local overrides are needed:

```powershell
Copy-Item .env.example .env
```

The main settings are:

| Variable | Default | Purpose |
| --- | --- | --- |
| `JARVIS_OLLAMA_MODEL` | `qwen3:0.6b` | Ollama model used for chat |
| `JARVIS_LOCAL_MODEL` | `qwen3:0.6b` | Preferred local-role model; overrides compatibility alias above |
| `JARVIS_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama endpoint |
| `JARVIS_OLLAMA_CONTEXT_TOKENS` | `4096` | Bounded active local context |
| `JARVIS_OLLAMA_MAX_OUTPUT_TOKENS` | `512` | Local generation ceiling |
| `JARVIS_OLLAMA_KEEP_ALIVE` | `5m` | Ollama residency policy |
| `JARVIS_FAST_MODEL` | `openai/gpt-oss-20b` | Groq fast role |
| `JARVIS_PRIMARY_MODEL` | `qwen/qwen3.6-27b` | Groq primary preview role |
| `JARVIS_REASONING_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` | NVIDIA hosted reasoning role |
| `JARVIS_NVIDIA_MAX_OUTPUT_TOKENS` | `1024` | Hosted thinking-request output ceiling |
| `JARVIS_NVIDIA_NON_REASONING_MAX_OUTPUT_TOKENS` | `256` | Hosted non-thinking output ceiling |
| `JARVIS_NVIDIA_REASONING_BUDGET_TOKENS` | `256` | Hosted hidden-reasoning budget when thinking is enabled |
| `JARVIS_NVIDIA_MAX_REQUESTS_PER_MINUTE` | `30` | Conservative local request guard; account cap is shown in NVIDIA UI |
| `JARVIS_NVIDIA_MAX_CONCURRENCY` | `1` | Maximum simultaneous NVIDIA requests |
| `JARVIS_CLOUD_POLICY` | `privacy_aware` | Use cloud only after local public-content classification |
| `JARVIS_MAX_CLOUD_COST_USD` | `0` | Hard Phase 1 budget; any other value is rejected |
| `JARVIS_WEB_HOST` | `127.0.0.1` | Browser/API bind; Phase 1 rejects non-loopback hosts |
| `JARVIS_DATA_DIR` | platform default | Override the private runtime data directory |
| `JARVIS_MEMORY_RETRIEVAL_ENABLED` | `true` | Project committed host memory into bounded local context; `false` preserves data but disables retrieval |
| `JARVIS_RESEARCH_ENABLED` | `true` | Enable bounded public research; `false` retains approved ledger data for recovery |
| `JARVIS_RESEARCH_SEARCH_PROVIDER` | `wikimedia` | Account-free discovery adapter; currently Wikimedia only |
| `JARVIS_RESEARCH_PENDING_TTL_SECONDS` | `900` | Expiry for volatile reports awaiting exact storage approval |
| `JARVIS_LOG_LEVEL` | `INFO` | Application log verbosity |
| `JARVIS_VOICE_STT_MODEL` | `base.en` | Local faster-whisper model downloaded by explicit voice setup |
| `JARVIS_VOICE_STT_CPU_THREADS` | `4` | CPU threads reserved for local transcription |
| `JARVIS_VOICE_MAX_CAPTURE_SECONDS` | `30` | Hard duration limit for one push-to-talk clip |
| `JARVIS_VOICE_BARGE_IN_ENABLED` | `true` | Stop speech output when new host speech is detected |
| `JARVIS_VOICE_ALWAYS_LISTENING_ENABLED` | `false` | Hard-disabled; `true` is rejected by configuration |
| `JARVIS_VOICE_ACOUSTIC_ALWAYS_LISTENING_ENABLED` | `false` | Hard-disabled; `true` is rejected by configuration |

To enable NVIDIA, set `JARVIS_NVIDIA_API_KEY` (or NVIDIA's sample-code alias
`NVIDIA_API_KEY`), `JARVIS_NVIDIA_FREE_TIER_CONFIRMED=true`, and
`JARVIS_NVIDIA_TRIAL_TERMS_ACKNOWLEDGED=true`. The model receives only content
classified public. NVIDIA does not publish one fixed trial limit: the model/account
limit appears in the API Catalog account UI, and HTTP 429 automatically falls back local.

To enable Groq, set `JARVIS_GROQ_API_KEY` and
`JARVIS_GROQ_FREE_TIER_CONFIRMED=true`. To enable Gemini, set
`JARVIS_GEMINI_API_KEY`, `JARVIS_GEMINI_FREE_TIER_CONFIRMED=true`, and
`JARVIS_GEMINI_UNPAID_DATA_TERMS_ACKNOWLEDGED=true`. These confirmations fail
closed; they do not technically inspect provider billing settings. Use credentials
from billing-disabled projects, enable Groq Zero Data Retention, and verify quotas
in provider consoles. Never send sensitive data to unpaid Gemini.

By default, mutable state belongs under current user's local application-data
directory, not this checkout. Prefer OS/process secret storage; never commit `.env`.

## Development

Install the locked environment, then run all local checks:

```powershell
uv sync --locked
./scripts/quality.ps1
```

For voice development, use `uv sync --locked --extra voice` after the base quality script; a plain
sync intentionally restores the lightweight text-only environment.

Formatting changes are opt-in:

```powershell
./scripts/quality.ps1 -Fix
```

The quality gate checks the lock file, formatting, linting, type checking,
tests, dependency vulnerabilities, and—when installed locally—Gitleaks. CI
always performs secret scanning.

## Documentation

- [Phase overview and status](docs/PHASE_OVERVIEW.md)
- [Phase 2 voice completion evidence](docs/phase-reports/PHASE_2_COMPLETION.md)
- [Phase 5 research completion evidence](docs/phase-reports/PHASE_5_COMPLETION.md)
- [Phase 6 planning completion evidence](docs/phase-reports/PHASE_6_COMPLETION.md)
- [Phase 6 bounded task operator guide](docs/BOUNDED_TASKS.md)
- [Codex Sol phase execution playbook](docs/CODEX_PHASE_PLAYBOOK.md)
- [Hands-free control plan](docs/HANDS_FREE_CONTROL.md)
- [Architecture](docs/architecture.md)
- [Security model](docs/security.md)
- [Windows setup](docs/setup-windows.md)
- [Roadmap](docs/roadmap.md)
- [Master roadmap](docs/JARVIS_MASTER_ROADMAP.md)
- [Technology decisions](docs/TECHNOLOGY_DECISIONS.md)
- [Security architecture](docs/SECURITY_MODEL.md)
- [Architecture decisions](docs/adr/0001-modular-monolith.md)

## Project principles

- Privacy-aware hybrid: cloud only after local non-sensitive classification;
  private/offline work remains local.
- Initial cloud cost is exactly `$0`; paid fallback is prohibited.
- Model output is untrusted data, never authorization.
- Tools are deny-by-default and validated before execution.
- Core behavior is testable without a GPU, microphone, model download, or
  network connection.
- Runtime state and large model files remain outside Git.
