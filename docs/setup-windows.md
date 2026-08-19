# Windows setup

## Supported baseline

- Windows 10 or Windows 11
- PowerShell 5.1 or newer
- Git
- `uv`
- Ollama
- Python 3.11, managed by `uv`

A GPU is not required for the Phase 1 text runtime. Model speed and memory use
depend on the selected Ollama model and hardware.

## 1. Clone the repository

```powershell
git clone https://github.com/DanCreates1/JARVIS.git
Set-Location JARVIS
git remote -v
git branch --show-current
```

The expected origin is `https://github.com/DanCreates1/JARVIS.git` and the
production branch is `main`.

## 2. Install uv

Install `uv` using its official instructions, then open a new terminal and check:

```powershell
uv --version
```

If Windows Package Manager is already installed, the bootstrap script can request
the official package explicitly:

```powershell
./scripts/bootstrap.ps1 -InstallUv
```

The script does not download and execute a remote PowerShell script.

If local policy prevents a checked-out script from running, use a process-scoped
policy rather than weakening the machine-wide policy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 3. Create the locked environment

```powershell
./scripts/bootstrap.ps1
```

This command:

- verifies the repository metadata needed for installation;
- asks `uv` to provision Python 3.11;
- requires the committed `uv.lock`; and
- synchronizes the virtual environment from that lock.

It does not install Ollama, pull a model, enable startup tasks, request
administrator privileges, or write outside normal tool-managed locations.

## 4. Install Ollama and the model

Install Ollama for Windows from its official distribution and verify:

```powershell
ollama --version
ollama list
```

Download the default model explicitly:

```powershell
./scripts/setup-model.ps1
```

To select a different Ollama model, pass one argument and configure the same name:

```powershell
./scripts/setup-model.ps1 -Model "qwen2.5:3b"
$env:JARVIS_OLLAMA_MODEL = "qwen2.5:3b"
```

Ollama stores weights in its own model directory. Do not copy weights into this
repository.

## 5. Verify and run

```powershell
uv run jarvis doctor
uv run jarvis chat
```

For automation or a quick smoke test:

```powershell
uv run jarvis chat --message "Reply with a short readiness confirmation."
```

`doctor` should report an actionable error when Ollama is stopped or the model is
missing. It must not print environment variables or private data.

## Configuration

Safe defaults require no `.env`. To override them:

```powershell
Copy-Item .env.example .env
```

Edit only the values needed on that machine. `.env` is ignored by Git. The
default Ollama endpoint is loopback-only and the default model is `qwen2.5:3b`.

Mutable state is stored in the current user's local application-data directory.
For an isolated test, set a temporary data directory for that terminal:

```powershell
$env:JARVIS_DATA_DIR = Join-Path $env:TEMP "jarvis-test-data"
uv run jarvis doctor
```

Do not point `JARVIS_DATA_DIR` at the repository.

## Development checks

```powershell
./scripts/quality.ps1
```

Use `-Fix` only when formatting changes are intended. The script reports when
Gitleaks is unavailable locally; GitHub CI always runs the secret scanner.

## Troubleshooting

### `uv` is not recognized

Open a new PowerShell window after installation and run `uv --version`. Confirm
the installation directory is on the user `PATH`.

### The lock file is missing or stale

Normal setup must not silently replace the lock. A dependency maintainer should
run `uv lock`, review the resulting diff, run the complete quality gate, and
commit `pyproject.toml` and `uv.lock` together.

### Ollama is unreachable

Start Ollama and run `ollama list`. Keep the endpoint at
`http://127.0.0.1:11434` unless a reviewed remote deployment is intentionally
configured.

### The model is missing

Run `./scripts/setup-model.ps1` or `ollama pull qwen2.5:3b`, then rerun
`uv run jarvis doctor`.

### Reset local Python dependencies

The virtual environment is disposable. Close running JARVIS processes, remove
only the repository's `.venv` directory, and rerun `./scripts/bootstrap.ps1`.
Conversation data is outside `.venv` and should not be affected.
