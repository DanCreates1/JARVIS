# Windows setup

## Supported baseline

- Windows 10 or Windows 11
- PowerShell 5.1 or newer
- Git
- `uv`
- Ollama
- Official Python Software Foundation CPython 3.11; `uv` manages locked dependencies

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

During Phase 8D, Windows App Control rejected the uv-managed CPython executable and generated
console shims with OS error 4551. No security policy was changed. Official PSF CPython 3.11.9 was
installed through the `Python.Python.3.11` WinGet package, the blocked environment was preserved in
ignored runtime storage, and the locked environment was rebuilt from that interpreter. `jarvis`,
`pytest`, and `mypy` then executed normally through `uv run`.

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
the official uv and PSF Python packages explicitly:

```powershell
./scripts/bootstrap.ps1 -InstallUv -InstallPython
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
- locates executable PSF CPython 3.11 and rejects unsigned/non-PSF substitutes;
- requires the committed `uv.lock`; and
- synchronizes the virtual environment from that lock using copies, avoiding OneDrive cache
  hardlink failures (Windows error 396), while disabling uv-managed Python fallback and downloads.

It does not install Ollama, pull a model, enable startup tasks, request
administrator privileges, or write outside normal tool-managed locations.

Copy mode uses more disk than hardlinks but does not change package versions or disable checks.
See [uv link modes](https://docs.astral.sh/uv/reference/settings/#link-mode).
For a separate manual sync that encounters error 396, pass the exact approved interpreter with
`uv sync --locked --link-mode copy --python <approved-python.exe> --no-managed-python --no-python-downloads`.

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

Browser chat listens at `http://127.0.0.1:8765` by default. JARVIS rejects a non-loopback bind
until Phase 8D supplies reviewed private-network/TLS deployment configuration and authority.

### Latency routing and NVIDIA evidence

Current defaults keep simple/normal/voice-sensitive work local, use configured Groq roles for
responsive public cloud work, and reserve NVIDIA for difficult public reasoning. Tune UX budgets
without changing Phase 1 acceptance thresholds:

```dotenv
JARVIS_CONTEXT_RECENT_MESSAGE_LIMIT=8
JARVIS_CONTEXT_SUMMARY_MAX_CHARS=2000
JARVIS_SIMPLE_LOCAL_LATENCY_BUDGET_MS=3000
JARVIS_NORMAL_VOICE_LATENCY_BUDGET_MS=2500
JARVIS_FAST_CLOUD_LATENCY_BUDGET_MS=2500
JARVIS_DEEP_REASONING_LATENCY_BUDGET_MS=7000
JARVIS_PROVIDER_HEALTH_WINDOW_SIZE=50
JARVIS_PROVIDER_DEGRADATION_SECONDS=120
```

These are routing/health budgets, not replacements for fixed Phase 1 p50/p95 gates. Run public
NVIDIA evidence only with existing free-tier authorization and compiled public fixtures:

```powershell
uv run python scripts\phase1-benchmark.py --work-dir runtime\phase1-nvidia --profiles hosted-simple hosted-complex --samples 20 --warmups 1 --include-hosted --confirm-public-fixtures --nvidia-reasoning-matrix --nvidia-reasoning-budgets 64 128 256
```

The report stores fixture hashes and operational metrics, not prompt/response text. Preserve failed
or incomplete runs. Routing around degraded NVIDIA protects product response time but does not make
the NVIDIA benchmark pass.

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

## Optional bounded vision capture

Vision dependencies are locked but excluded from the base environment:

```powershell
uv sync --locked --extra vision
uv run jarvis vision setup
uv run jarvis vision status
uv run jarvis vision doctor
```

These inspection commands do not open a camera or read the screen. Capture requires both a
process-start host gate and persistent software control, plus an explicit foreground command:

```powershell
uv run jarvis vision enable
# Set JARVIS_VISION_CAPTURE_ENABLED=true, then start a new foreground process.
uv run jarvis vision capture --source camera --source-id camera:0 --x 0 --y 0 --width 640 --height 480 --fps 10 --frames 1 --duration-ms 1000
uv run jarvis vision gestures --source-id camera:0 --width 640 --height 480 --fps 10 --frames 300 --duration-ms 30000
uv run jarvis vision disable
```

Use exact coordinates with `--source screen --source-id screen:desktop` for screen-region capture.
Frames are immediately discarded and never printed or saved. Before any live test, close private
windows, confirm Windows **Settings > Privacy & security > Camera > Let desktop apps access your
camera**, and verify the webcam shutter/indicator. `vision disable` is the persistent software kill
path; the physical shutter and Windows privacy control remain independent.

No continuous listener starts. `vision setup` is the only model-download path and never opens a
source. The bounded `vision gestures` command processes locally, prints only content-free events,
clears pixels/landmarks, and proposes or executes nothing. Use optional `--exposure -4` only when a
reviewed camera cannot sustain 10 FPS under automatic exposure. See [Vision Capture Privacy
Boundary](VISION_CAPTURE.md) and [Local Gesture Recognition](GESTURE_RECOGNITION.md).

Phase 7C adds no listener. Its bridge exists only when a foreground gesture pipeline
is explicitly composed. The computer policy keeps `volume_step`, `media_play_pause`, `mute_toggle`,
`media_track_navigation`, and `cancel_session` false by default. Enabling a flag permits only a
reviewable Level 1 proposal; it does not enable capture, approve a grant, or execute an action.

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

## Optional bounded task execution

Phase 6 plan creation and inspection work with execution disabled. Create a current-deadline JSON
proposal, then inspect immutable handler resolution and budgets:

```powershell
uv run jarvis task create .\plan.json
uv run jarvis task list
uv run jarvis task show <task-id>
uv run jarvis task events <task-id>
```

Only after review, enable explicit foreground runs for current process or in `.env`:

```powershell
$env:JARVIS_TASK_EXECUTION_ENABLED = "true"
uv run jarvis task run <task-id>
```

No background scheduler starts. Computer effect nodes still require both Phase 3 gates plus one
exact pre-existing grant bound with `task bind-approval`; task commands cannot approve actions.
Use pause/resume/cancel and explicit reconciliation as documented in
[Bounded Tasks](BOUNDED_TASKS.md). Return `JARVIS_TASK_EXECUTION_ENABLED=false` to restore safe
default. `jarvis doctor` reports current execution state and host ceilings.

## Phase 8A remote identity administration

Phase 8A remains local-only. Keep `JARVIS_WEB_HOST=127.0.0.1`; do not add a firewall exception,
port forward, reverse proxy, or Tailscale Serve rule. Network/TLS deployment is Phase 8D.

From a trusted local PowerShell terminal, create an exact five-minute enrollment grant:

```powershell
uv run jarvis remote enroll "My phone" `
  --type phone `
  --scope identity.read `
  --scope events.read `
  --scope session.revoke `
  --scope key.rotate
```

The challenge prints once. Transfer it privately to client software that generated its own Ed25519
key. Never place the challenge or private key in Git, logs, model context, or browser local storage.

Inspect and recover from the local host:

```powershell
uv run jarvis remote devices
uv run jarvis remote audit DEVICE_ID --after 0 --limit 100
uv run jarvis remote revoke DEVICE_ID --confirm-device-id DEVICE_ID
uv run jarvis doctor
```

Revocation immediately disables the device and every session. Full protocol/client requirements
are in [Remote Identity and API Boundary](REMOTE_ACCESS.md).

## Phase 8B trusted browser configuration

Browser session bootstrap remains deny-by-default. Do not configure an origin until an exact HTTPS
origin exists. Phase 8D owns TLS/private-network deployment and any firewall/Tailscale change.

For local integration tests or a later reviewed gateway, use a JSON array of exact origins:

```powershell
$env:JARVIS_TRUSTED_BROWSER_ORIGINS = '["https://jarvis.example.internal"]'
$env:JARVIS_REMOTE_PUBLIC_REQUESTS_PER_MINUTE = '20'
$env:JARVIS_REMOTE_AUTHENTICATED_REQUESTS_PER_MINUTE = '240'
$env:JARVIS_REMOTE_RATE_LIMIT_ENTRIES = '4096'
uv run jarvis doctor
```

Enroll a browser-capable device only from the trusted local terminal. Add `approval.review` only
when the device may show exact low-risk prompts:

```powershell
uv run jarvis remote enroll "My browser" `
  --type browser `
  --scope browser.session `
  --scope identity.read `
  --scope session.revoke `
  --scope approval.review `
  --risk-ceiling 1
```

## Phase 8C PWA client

Phase 8C packages the offline-safe shell at `/app/` but does not expose it beyond loopback. Preview
the static shell locally after `uv run jarvis serve`:

```text
http://127.0.0.1:8765/app/
```

Full cookie authentication requires the exact HTTPS origin configured above. Do not weaken the
origin validator to use HTTP, add a firewall rule, bind a LAN address, or configure a reverse
proxy/Tailscale Serve rule during Phase 8C. Phase 8D owns those changes and real-phone validation.

For a later reviewed HTTPS origin, enroll the PWA from the trusted local terminal with only its
required scopes:

```powershell
uv run jarvis remote enroll "My PWA" `
  --type browser `
  --scope browser.session `
  --scope identity.read `
  --scope events.read `
  --scope session.revoke `
  --scope client.chat `
  --scope client.tasks.read `
  --scope client.status.read `
  --risk-ceiling 1
```

Paste the one-time JSON ticket into `/app/`. The browser generates a non-exportable Ed25519 private
key in dedicated IndexedDB. The service worker caches only static `/app/` assets; it never caches
`/api/*`, messages, tasks, credentials, or notification text. Notifications require an explicit
button press and contain generic text only. Remote voice stays disabled.

Use **Logout and erase this device** while online. It revokes the browser session and clears the
cookie, IndexedDB key, CSRF/cursor/subscription state, notification setting, shell cache, and
service-worker registration. If the phone is lost or offline, run the trusted-local `remote revoke`
command instead; offline browser erasure cannot revoke the server session, which otherwise expires
within 15 minutes.

Private keys belong in platform secure storage, never `localStorage`, IndexedDB plaintext, Git,
logs, model context, or URLs. Keep returned CSRF value only in memory. Close/rebootstrap after
reload; local device revocation is the lost-device recovery path.

## Phase 8D private phone deployment

Phase 8D keeps `JARVIS_WEB_HOST=127.0.0.1` and uses Tailscale Serve for private HTTPS. Install the
official Windows client and authenticate the laptop and phone to the reviewed tailnet. Before
enabling HTTPS, review the machine name: its exact `.ts.net` FQDN will appear in public Certificate
Transparency logs. Remove any tailnet allow-all rule and restrict the intended source to this
JARVIS host on TCP 443. Never enable Funnel.

Run preflight, then the foreground launcher:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\phase8d-private.ps1 `
  -Action Preflight
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\phase8d-private.ps1 `
  -Action Run `
  -AcknowledgeCertificateTransparency `
  -AcknowledgePrivateGrant
```

`-ExecutionPolicy Bypass` is process-local and does not change Windows policy. Normal `Ctrl+C`
removes the owned Serve route. After a hard interruption, run the same command with `-Action Stop`.
The script refuses to remove an unowned or changed Serve configuration. See
[Phase 8D private deployment](PHASE_8D_DEPLOYMENT.md) for phone enrollment,
reconnect/restart, external scan, revocation, loss, and rollback gates.

## Phase 9A topology safety

Phase 9A adds topology and negotiation contracts only. Keep these defaults:

```powershell
$env:JARVIS_TOPOLOGY_PROFILE = 'local-only'
$env:JARVIS_TOPOLOGY_NODE_ID = 'node:local-core'
$env:JARVIS_TOPOLOGY_EPOCH = '1'
uv run jarvis doctor
```

`jarvis doctor` must report one local node, eleven single-owner domains, protocol `1.0`, and no
remote writer. `split` and `server-primary` are design manifests but are rejected by executable
settings. Do not enroll a real remote `topology.negotiate` peer, move a database, start a remote
core, or add another
replica during 9A. Phase 9B requires verified backup/restore, shadow comparison, cutover, and
rollback before this configuration can widen. Full ownership and protocol details are in
[Phase 9A Topology and Protocol Boundary](PHASE_9A_TOPOLOGY.md).

## Phase 9B migration rehearsal

Phase 9B adds `uv run jarvis remote migration --help`. It creates reviewed topology manifests,
encrypted no-overwrite SQLite bundles, authenticated restores, exact logical shadow comparisons,
and chained cutover/rollback receipts. Migration keys must be random 256-bit files stored and
transferred separately from bundles. Never put a key, bundle, restored database, receipt with local
paths, or runtime evidence in Git.

Completing a receipt does not activate `split` or `server-primary`. Keep the runtime settings above,
keep one local process, and do not start a remote writer. Follow the exact stop, RPO/RTO, key,
backup, restore, drift, cutover, and rollback sequence in
[Phase 9B Migration and Recovery](PHASE_9B_MIGRATION.md). Phase 9C must enforce the reviewed receipt
before deployment can widen runtime placement.

## Phase 9C receipt-gated runtime

Local Windows startup remains unchanged because `JARVIS_DEPLOYMENT_ENFORCED=false`. A remote
profile is rejected unless enforcement is true and topology/deployment/state/release paths plus
both expected digests are complete. Server core additionally requires the Phase 9B ownership
receipt. Validation occurs before any SQLite store opens.

Use `uv run jarvis remote deployment --help` to create, activate, verify, stage, promote, and roll
back reviewed artifacts. Do not set remote values on this laptop merely to test them. The complete
Linux systemd/Tailscale procedure, health checks, partition policy, update order, RPO/RTO, and live
authority boundary are in [Phase 9C Deployment and Recovery](PHASE_9C_DEPLOYMENT.md).

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
