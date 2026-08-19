# JARVIS

JARVIS is a local-first assistant for Windows. The Phase 1 rebuild provides a
small, testable text runtime around a local Ollama model, durable SQLite
conversation history, and a deny-by-default tool boundary.

This repository is the source of truth for the project. Local model weights,
runtime databases, logs, generated media, and secrets do not belong in Git.

## Phase 1

The first supported workflow is deliberately narrow:

- validate the local installation and configured Ollama model;
- chat interactively from a terminal;
- send one non-interactive message;
- persist conversation data outside the repository; and
- expose only explicitly registered, schema-validated tools.

Voice, vision, desktop control, a network API, and graphical clients are later
milestones. The core runtime is kept independent of those interfaces so they can
be added without replacing the text assistant.

## Requirements

- Windows 10 or Windows 11
- PowerShell 5.1 or newer
- Git
- [`uv`](https://docs.astral.sh/uv/)
- [Ollama for Windows](https://ollama.com/download/windows)

Python 3.11 is selected by `.python-version` and can be installed by `uv`. Do not
install Python packages globally.

## Quick start

```powershell
git clone https://github.com/DanCreates1/JARVIS.git
Set-Location JARVIS
./scripts/bootstrap.ps1
./scripts/setup-model.ps1
```

The default model is `qwen2.5:3b`. Then verify the installation:

```powershell
uv run jarvis doctor
```

Start an interactive session:

```powershell
uv run jarvis chat
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
| `JARVIS_OLLAMA_MODEL` | `qwen2.5:3b` | Ollama model used for chat |
| `JARVIS_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama endpoint |
| `JARVIS_DATA_DIR` | platform default | Override the private runtime data directory |
| `JARVIS_LOG_LEVEL` | `INFO` | Application log verbosity |

By default, mutable state belongs under the current user's local application
data directory, not under this checkout. Never place credentials in `.env` and
never commit `.env`.

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

- [Architecture](docs/architecture.md)
- [Security model](docs/security.md)
- [Windows setup](docs/setup-windows.md)
- [Roadmap](docs/roadmap.md)
- [Architecture decisions](docs/adr/0001-modular-monolith.md)

## Project principles

- Local by default and explicit about every external dependency.
- Model output is untrusted data, never authorization.
- Tools are deny-by-default and validated before execution.
- Core behavior is testable without a GPU, microphone, model download, or
  network connection.
- Runtime state and large model files remain outside Git.
