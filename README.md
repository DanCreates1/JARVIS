# JARVIS

JARVIS is a privacy-aware hybrid assistant for Windows. Phase 1 implements a
local deterministic privacy gate, configurable NVIDIA/Groq/Gemini/Ollama roles,
zero-cost fallback routing, durable SQLite state, audited read-only tools, CLI,
and loopback browser chat. Sensitive and uncertain work remains local.

This repository is the source of truth for the project. Local model weights,
runtime databases, logs, generated media, and secrets do not belong in Git.

## Implemented Phase 1

The supported text vertical slice can:

- validate local storage, Ollama, configured cloud credentials, and live model catalogs;
- chat interactively from a terminal;
- chat from a loopback-only browser page and JSON/SSE API;
- send one non-interactive message;
- route safe simple, normal, and difficult work across logical model roles;
- keep credentials, files, memory, communications, personal data, and uncertain content local;
- fall back on quota, model removal, or outage without entering paid service;
- persist and explicitly delete conversations and basic memory records; and
- expose only schema-validated, policy-approved read-only clock, system-status, and allowlisted
  text-file tools with audit records.

Voice, vision, desktop control, a network API, and graphical clients are later
milestones. The core runtime is kept independent of those interfaces so they can
be added without replacing the text assistant.

## Model strategy

| Role | Target default | Use |
| --- | --- | --- |
| `FAST` | Groq `openai/gpt-oss-20b` | Safe simple requests and safe ambiguous intent |
| `PRIMARY` | Groq preview `qwen/qwen3.6-27b` | Safe normal conversation and tool planning |
| `REASONING` | NVIDIA `nvidia/nemotron-3-ultra-550b-a55b` | Safe difficult reasoning, coding, research, long context, and tools |
| `LOCAL` | Ollama `nemotron-3-nano:4b` | Normal/private requests, offline operation, cloud fallback |

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

The default local model is `nemotron-3-nano:4b`. Then verify the installation:

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
| `JARVIS_OLLAMA_MODEL` | `nemotron-3-nano:4b` | Ollama model used for chat |
| `JARVIS_LOCAL_MODEL` | `nemotron-3-nano:4b` | Preferred local-role model; overrides compatibility alias above |
| `JARVIS_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama endpoint |
| `JARVIS_FAST_MODEL` | `openai/gpt-oss-20b` | Groq fast role |
| `JARVIS_PRIMARY_MODEL` | `qwen/qwen3.6-27b` | Groq primary preview role |
| `JARVIS_REASONING_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b` | NVIDIA hosted reasoning role |
| `JARVIS_NVIDIA_MAX_OUTPUT_TOKENS` | `4096` | Local output guard; NVIDIA model maximum is 32,768 |
| `JARVIS_NVIDIA_MAX_REQUESTS_PER_MINUTE` | `30` | Conservative local request guard; account cap is shown in NVIDIA UI |
| `JARVIS_NVIDIA_MAX_CONCURRENCY` | `1` | Maximum simultaneous NVIDIA requests |
| `JARVIS_CLOUD_POLICY` | `privacy_aware` | Use cloud only after local public-content classification |
| `JARVIS_MAX_CLOUD_COST_USD` | `0` | Hard Phase 1 budget; any other value is rejected |
| `JARVIS_WEB_HOST` | `127.0.0.1` | Browser/API bind; Phase 1 rejects non-loopback hosts |
| `JARVIS_DATA_DIR` | platform default | Override the private runtime data directory |
| `JARVIS_LOG_LEVEL` | `INFO` | Application log verbosity |

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

Formatting changes are opt-in:

```powershell
./scripts/quality.ps1 -Fix
```

The quality gate checks the lock file, formatting, linting, type checking,
tests, dependency vulnerabilities, and—when installed locally—Gitleaks. CI
always performs secret scanning.

## Documentation

- [Phase overview and status](docs/PHASE_OVERVIEW.md)
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
