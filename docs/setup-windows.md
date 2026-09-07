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

## Current reproduction evidence and host limits

On 2026-08-31, fresh GitHub `windows-latest` run
[`33467300560`](https://github.com/DanCreates1/JARVIS/actions/runs/33467300560) installed uv 0.12.5
and CPython 3.11.16, resolved 115 locked packages, created the 62-package environment, and ran
`scripts/bootstrap.ps1` successfully. Exact lock, sync, format, lint, mypy, pytest, and pip-audit
commands passed; pytest reported 535 passed, 1 capability skip, and 85.09% coverage. The separate
complete-history Gitleaks job also passed. This supplies independent clean-Windows bootstrap and
repository-gate evidence without relying on this laptop's caches or policy.

The current host rehearsal also passed in a fresh ignored environment. Windows Smart App Control
still rejects generated `mypy`, `pytest`, `pip-audit`, and `jarvis` console shims with OS error
4551, while RTK 0.45.0 and uv run normally. Do not change or bypass that policy. Use the same locked
modules through allowed uv-managed Python entry points and retain both local module results and the
independent exact-command CI evidence.

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

Inspect the effective policy before running scripts:

```powershell
Get-ExecutionPolicy -List
```

Do not use execution-policy bypass, disable Smart App Control, or route around an Application
Control denial. If a reviewed script or locked executable is blocked, stop the affected check
and obtain an approved signed/trusted toolchain or an administrator-approved test environment.
Record the denied path and Code Integrity event; an unexecuted check has not passed. PowerShell 7
may be used when installed and permitted, but does not waive any execution or application policy.

## 3. Create the locked environment

```powershell
./scripts/bootstrap.ps1
```

This command:

- verifies the repository metadata needed for installation;
- asks `uv` to provision Python 3.11;
- requires the committed `uv.lock`; and
- synchronizes the virtual environment from that lock using copies, avoiding OneDrive cache
  hardlink failures (Windows error 396).

It does not install Ollama, pull a model, enable startup tasks, request
administrator privileges, or write outside normal tool-managed locations.

Copy mode uses more disk than hardlinks but does not change package versions or disable checks.
See [uv link modes](https://docs.astral.sh/uv/reference/settings/#link-mode).
For a separate manual sync that encounters error 396, use `uv sync --locked --link-mode copy`.

### Clean Windows verification

A new venv, checkout, or Windows user on an existing developer machine is not clean-machine
evidence. Use a newly installed disposable Windows machine/VM or a fresh supported Windows Sandbox
instance, with its own Python, package cache, and Ollama installation. Windows Home does not
support Sandbox; see [Microsoft's supported editions](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/).
Do not provision a VM, purchase a license, or change host security policy without authorization.

Record the OS image/build and provenance, snapshot/reset state, effective execution policy,
tool versions, source manifest/lock hashes, commands/exit codes, and model digest. Run bootstrap,
the complete quality gate, model setup, doctor, local text smoke, and restart/deletion checks in
the guest. Confirm host environments, caches, secrets, model stores, and runtime databases were
not reused. Preserve sanitized evidence outside the disposable guest before destroying it.

For an uncommitted worktree, an origin clone alone tests older code. Transfer a reviewed,
secret-scanned source snapshot including untracked source/tests, plus a file-hash manifest, into
the authorized guest. Exclude `.env`, `.env.local`, environments, runtime state, caches, and model
weights. Identify the base Git SHA and changed files explicitly; do not commit merely to test.

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
./scripts/setup-model.ps1 -Model "qwen3:0.6b"
$env:JARVIS_OLLAMA_MODEL = "qwen3:0.6b"
```

Ollama stores weights in its own model directory. Do not copy weights into this
repository.

## 5. Verify and run

```powershell
uv run jarvis doctor
uv run jarvis chat
uv run jarvis serve
```

For automation or a quick smoke test:

```powershell
uv run jarvis chat --message "Reply with a short readiness confirmation."
```

`doctor` should report an actionable error when Ollama is stopped or the model is
missing. It must not print environment variables or private data.

Browser chat listens at `http://127.0.0.1:8765` by default. Phase 1 rejects a
non-loopback bind because remote authentication is not implemented.

## Durable memory controls

Phase 4 memory is local, SQLite-backed, and enabled by default. A stable pseudonymous ID derived
from the current Windows user/device partitions records; it is an isolation key, not remote
authentication. Inspect records and retrieval reasons before relying on personalization:

```powershell
uv run jarvis memory list
uv run jarvis memory search "response preference"
uv run jarvis memory conflicts
uv run jarvis memory retention
```

Explicit statements extracted during chat become candidates, not facts. `memory list --state
candidate` shows the exact ID, version, digest, source, and confidence required by `memory promote`.
Use `memory reject` for unwanted candidates. Use `memory remember` only for an explicit host fact;
`memory correct` supersedes an exact committed version and `memory forget` transitively removes
content, FTS rows, provenance, conflicts, and sole-source derived records.

```powershell
uv run jarvis memory remember profile "Prefer concise responses" --key profile.response-style
uv run jarvis memory list --state candidate
uv run jarvis memory set-retention working 1
uv run jarvis memory expire
uv run jarvis memory export .\jarvis-memory-export.json
```

Run `uv run jarvis memory --help` and the subcommand help before correction, confirmation, conflict
resolution, or deletion. Export refuses an existing destination and should be moved to private
storage. Closing JARVIS before copying `jarvis.db`, then restoring only a verified backup and
running `uv run jarvis doctor`, is the manual recovery path. JSON export is for inspection and data
portability; it is not an automatic database restore command.

Set `JARVIS_MEMORY_RETRIEVAL_ENABLED=false` to stop durable prompt projection without deleting
records. Inspection, export, correction, retention, and deletion remain available. Migration 005
is additive; legacy note/profile/task rows are preserved under an isolated legacy scope rather
than silently attributed to a different host. Encrypted cross-device backup/retention remains a
later deployment phase.

## Bounded public research

Phase 5 research is enabled by default and uses an account-free Wikimedia search adapter. Only
public HTTPS sources are eligible. Discovery and acquisition obey fixed source/fetch/domain/byte/
redirect/time limits; HTML, plain text, and PDF parsing occurs in a short-lived isolated worker.
JavaScript rendering, authentication/paywall bypass, file downloads, and OCR are unsupported.

```powershell
uv run jarvis research run "What is Python?" --max-sources 3 --max-fetches 6
uv run jarvis research run "What is Python?" --store
uv run jarvis research list
uv run jarvis research show <report-id>
uv run jarvis research search "Python"
uv run jarvis research revalidate <source-id>
uv run jarvis research export .\jarvis-research-export.json
```

Without `--store`, the report disappears when the process exits. `--store` consumes an exact
one-use approval bound to the displayed report digest; it does not create trusted Phase 4 memory.
Use `research questions` and `research close-question` for approved report gaps. Source deletion is
transitive and requires its exact ID twice:

```powershell
uv run jarvis research delete-source <source-id> --confirm <source-id>
```

Export first if recovery may be needed. Export refuses overwrite and is for inspection/portability,
not automatic restore. Set `JARVIS_RESEARCH_ENABLED=false` and restart to disable new research while
retaining the approved ledger for inspection/export/deletion. Run `jarvis doctor`; the `research
parser sandbox` row verifies the isolated worker and locked PDF dependency.

## Optional local voice

Voice dependencies are locked but excluded from the text-only environment. Install them explicitly:

```powershell
uv sync --locked --extra voice
uv run jarvis voice setup
uv run jarvis voice devices
```

A later plain `uv sync --locked` restores the text-only environment and removes unselected extras;
repeat the `--extra voice` sync before voice use.

Choose the stable IDs for the intended microphone and speaker/headphones. IDs survive backend index
reordering; diagnostics fail clearly if a selected endpoint disappears.

```powershell
uv run jarvis voice select --input-device-id <stable-input-id> --output-device-id <stable-output-id>
uv run jarvis voice doctor
uv run jarvis voice enable
uv run jarvis voice push-to-talk
uv run jarvis voice disable
```

Voice starts software-disabled. Capture begins only after explicit push-to-talk and shows `MIC ON`.
`voice disable` stops current/new capture through a polled control file and leaves text chat usable.
Raw audio and synthesized PCM are bounded, in-memory turn data; they are not stored or sent to cloud
STT/TTS. Models and endpoint settings live under `%LOCALAPPDATA%\JARVIS`, outside Git.
The downloaded openWakeWord code is Apache-2.0, but its bundled pretrained wake model is
CC BY-NC-SA 4.0; JARVIS does not redistribute it. Review the
[upstream license note](https://github.com/dscripka/openWakeWord#license) before commercial use.

On the audited ASUS TUF Gaming F15 FX506HF, the official FX506H-series manual identifies
**Fn+F4** as the microphone on/off hotkey. Confirm its on-screen/keyboard indication before regular
use. A headset hardware mute or Windows **Settings > Privacy & security > Microphone** access control
is a secondary path. Physical mute is independent of JARVIS and cannot be actuated by voice
diagnostics. See the [ASUS FX506H manual](https://dlcdnets.asus.com/pub/ASUS/GamingNB/FX506HM/E18920_FX506H_FX706H_EM_V3.pdf).

Wake-word and acoustic always-listening settings are intentionally fixed to `false`. Do not bypass
them. Phase 2 ships detectors and evaluation evidence, not an always-on service.

## Optional controlled computer access

Phase 3 is default-disabled and requires two reviewed gates. Start by creating only a disabled
policy and dedicated controlled-file root:

```powershell
uv run jarvis computer init
uv run jarvis computer status
```

Review `%LOCALAPPDATA%\JARVIS\computer-access.json`. Enroll exact executable paths with lowercase
SHA-256 digests from `Get-FileHash -Algorithm SHA256`, fixed argument arrays, fixed app groups,
credential-free public HTTPS browser targets, and exact Windows printer queue names. Keep the
policy disabled during editing. The controlled root must remain the dedicated child of the JARVIS
data directory; another root, symlink, or reparse redirect is rejected.

After review:

```powershell
uv run jarvis computer enable
# Set JARVIS_COMPUTER_ACCESS_ENABLED=true in .env, then restart JARVIS.
uv run jarvis computer status
uv run jarvis doctor
```

The model/chat can create a proposal only. Review exact effect/arguments/risk/recovery/expiry in the
local terminal, type the generated fingerprint phrase, then execute the separate one-use grant:

```powershell
uv run jarvis computer pending
uv run jarvis computer approve <approval-id>
uv run jarvis computer execute <grant-id>
uv run jarvis computer audit --kind all --limit 50
```

Kill live authority with `uv run jarvis computer disable`, then return the environment gate to
`false` before the next startup. Enable/disable rotates the policy epoch; earlier grants cannot
revive. The browser/API exposes no approval endpoint.

Use only disposable/public content for initial app/media/volume/clipboard/print checks. A physical
print job, real media key, clipboard replacement, app launch, or volume change affects the current
Windows session and requires deliberate operator approval. Printer discovery/status sends no job.

Full schemas, permission levels, action limits, audit behavior, recovery, and Windows constraints:
[Controlled Computer Access](CONTROLLED_COMPUTER_ACCESS.md).

## Optional free-tier cloud roles

Local Ollama works without cloud credentials. To activate Groq, inject a key from
a billing-disabled/free-tier project and confirm that constraint:

```powershell
$env:JARVIS_GROQ_API_KEY = "<secret>"
$env:JARVIS_GROQ_FREE_TIER_CONFIRMED = "true"
```

To activate unpaid Gemini, also acknowledge its data terms. Never submit
sensitive, personal, credential, file, memory, communication, or device context:

```powershell
$env:JARVIS_GEMINI_API_KEY = "<secret>"
$env:JARVIS_GEMINI_FREE_TIER_CONFIRMED = "true"
$env:JARVIS_GEMINI_UNPAID_DATA_TERMS_ACKNOWLEDGED = "true"
```

Run `uv run jarvis doctor` after configuration. It validates live model catalogs.
Enable Groq Zero Data Retention separately in Groq controls. Confirmation flags
fail closed but cannot technically inspect provider billing settings.

## Configuration

Safe defaults require no `.env`. To override them:

```powershell
Copy-Item .env.example .env
```

Edit only the values needed on that machine. `.env` is ignored by Git. The
default Ollama endpoint is loopback-only and the default model is `qwen3:0.6b`.

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

Run `./scripts/setup-model.ps1` or `ollama pull qwen3:0.6b`, then rerun
`uv run jarvis doctor`.

### Voice setup or endpoint fails

Run `uv sync --locked --extra voice`, `uv run jarvis voice setup`, then
`uv run jarvis voice doctor`. Re-run `voice devices` and `voice select` after Bluetooth reconnects,
driver changes, or endpoint removal. Keep the software kill switch active while recovering.

### Reset local Python dependencies

The virtual environment is disposable. Close running JARVIS processes, remove
only the repository's `.venv` directory, and rerun `./scripts/bootstrap.ps1`.
Conversation data is outside `.venv` and should not be affected.
