# PROTO-1.2 text slice evidence

Date: **2026-10-22**. Starting branch/HEAD: `main`, `4a2494f` (PROTO-1.1; CI passed).
Scope: one opt-in text launch/profile and first runnable local demonstration. Stop before
**PROTO-2.1**. Canonical scope: [Prototype Plan](PROTOTYPE_PLAN.md).

## Delivered behavior

- `scripts/open-local.cmd` runs the existing locked `python -m jarvis serve` entry with
  `prototype-text` and installed `qwen3:0.6b`; optional CLI arguments reuse that module entry.
  [Runbook](PROTOTYPE_TEXT_RUNBOOK.md) fixes startup, existing HTTPS access and recovery.
- Profile enforces local-only routing and loopback model/Core, even with old enabled feature
  flags. Research/automatic search, attachment/email/coding/current-context projections,
  voice/vision/computer effects, task execution and proactive effects are disabled. No Garmin
  sidecar starts. Approved-memory, privacy/policy, authentication, receipts/history and $0 remain.
- PWA presents Chat/Settings, hides optional Garmin/tasks/attachments/voice/notifications, and
  normalizes a Garmin deep link to Chat. Settings provides specific Core/network/model/access
  recovery. Authenticated status shows selected local provider/model/policy without credentials.
  Profile presentation cannot enable Send or replace authenticated stream/history readiness.
- Disabled research emits `research_unavailable` plus explicit nonpersistent missing-evidence
  guidance. UI discloses that external current facts cannot be verified. This is not evidence
  that every model response complies; the mandatory unsupported-fact corpus case remains AC-09.
- Shell cache advances to v13; existing no-API/private-cache and offline microphone denial remain.
  Standard profile retains the optional implementations and existing client contracts.

## Frozen inputs and real local smoke

[Ten-case corpus](PROTOTYPE_CORPUS.md) and facts/formats were written before the session's first
model request. No full corpus scoring, cold/warm percentile run or integrated-browser acceptance
was performed. The clock smoke sits outside those ten cases and uses the existing direct
command `What is the time?`.

`rtk proxy uv run --locked python scripts/prototype-text-smoke.py --live` passed using new ignored
synthetic Core and CLI stores; no owner database, keys, health data or transcripts were copied.
Ollama **0.40.8**, model **qwen3:0.6b**, digest
`7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435`.

| Smoke | Observable result |
| --- | --- |
| Direct clock | Completed in 0.009 s; timezone-aware timestamp between surrounding host-clock samples; no model usage |
| C1 synthetic checklist | 21 actual local token deltas; first runtime delta 0.438 s; completion 0.588 s; 13 words |
| F1 same-conversation follow-up | 10 actual local token deltas; first runtime delta 0.035 s; completion 0.109 s; 9 words; correct blue-box reference |
| Context persistence | Four durable messages for C1/F1 in real SQLite |
| Documented CLI launcher | Exit 0; genuine local solar-eclipse answer using a separate synthetic store |

Timings are `perf_counter` intervals from service-stream invocation to first visible content
delta / terminal frame. Two generated service samples only; model residency was not reset or
classified as cold/warm. They are **not AC-09 timing acceptance** or browser-render timings.
Only local model provider was constructed; no cloud call, spend or task effect.

Smoke assertions check a genuine answer and same-conversation blue-box reference, not the full
rubric. Inspecting synthetic output exposed quality limits: the CLI eclipse answer exceeded the
requested two sentences; F1 identified the blue box but omitted the labeling action/count. Those
samples do not earn full E1/F1 corpus credit. Full fixed scoring and any bounded comparison of
already-installed alternatives remain PROTO-2.1; no model download or acceptance change was made.

The first smoke used `What time is it?`, which is outside the existing deterministic matcher;
the model called the clock tool and the smoke correctly failed its no-model assertion. The smoke
and runbook were corrected to the existing direct phrase before the accepted rerun. None of the
ten frozen corpus inputs or acceptance thresholds changed. No routing/provider edit was needed.

## Existing route and authority boundary

Read-only `tailscale serve status --json` confirms one existing HTTPS route on 443 targeting
`http://127.0.0.1:8765`. TLS-verified GET of its `/app/` returned **502** while no Core owned 8765.
This proves the configured gateway was reachable; it does not establish authenticated PWA success.
No production Core was started/restarted, identity enrolled, route changed, TLS exception added,
or owner store opened. Existing Ollama owner process was reused without restart.
Private hostname, tickets and identity material are omitted. Integrated success is PROTO-2.1.

## Verification

Commands use RTK and locked dependencies; CPython **3.11.9**, uv **0.12.15**.

| Gate | Result |
| --- | --- |
| Root lock / locked base sync / Windows bootstrap | Pass; 119 resolved, 69 base packages |
| Root Ruff format / lint / Mypy | Pass; 440 format files, 168 typed source files |
| Full pytest with preserved provider edits | **1,539 passed, 3 skipped; 85.96% coverage; 126.67 s** |
| Focused profile/runtime/authenticated PWA contract | **54 passed** |
| PWA lifecycle / PCM worklet | **152 passed; 0 skipped** |
| Standard desktop browser harness | **72 cases passed**, keyboard/history/named log/contrast |
| Text profile desktop harness | **9 checks passed**, two navigation choices, dormant controls, deep link, keyboard/focus, specific recovery, readiness, 320/1280 reflow, named log, zero optional navigation requests |
| Publication snapshot format / lint / Mypy | Pass; 439 format files, 168 typed source files |
| Publication snapshot full pytest | **1,540 passed, 3 skipped; 85.92% coverage; 135.08 s** |
| Root base / restored-extras vulnerability audits | Zero known vulnerabilities; no exclusions or suppressions |
| Sidecar lock / fresh locked sync / audits | Pass; 20 resolved, 16 installed; fresh and existing site-packages report zero known vulnerabilities |
| Complete-history Gitleaks | Pass; 124 starting commits, no leaks |
| Whitespace, local links, staged secrets, held-file preservation | Pass; six changed/new documents checked, staged Gitleaks clean, shared-file pre-existing deltas preserved |

Sidecar fresh environment uses the existing explicit CPython **3.12.14** executable under
ignored `runtime/proto12/garmin-venv`; no blocked shim or Windows policy change. Base sync removes
extras; `uv sync --locked --extra voice --extra vision --link-mode copy` restores them.
All **97 installed packages exactly match** the starting version map. No lock/dependency change.
Initial focused test scaffolding omitted runtime startup for auth requests; fixed by exercising
both profiles in the existing initialized synthetic integration fixture. Accepted focused/full
runs supersede that failure. Existing Starlette warning and optional/platform skips remain.

## Publication and remaining work

Starting tree contained **27 dirty paths**. Byte snapshots under ignored `runtime/proto12/baseline`
protect every existing file and the existing deletion. All **24 untouched dirty paths** remain
byte-identical / equally absent. For shared README/setup/config, a separate index reconstructs
HEAD plus only this session's edits; older provider/document changes remain outside publication.
The exported publication tree is checked independently with its own source path and synthetic
pytest base. No global staging, runtime artifacts, private config, enrollment or generated data.

Held native hashes remain:

- `mobile/package.json`: `f1f34cd63792e55bd4db5293d3e9189eac0470d7a8fc81c58dbd895cf89796c4`.
- `mobile/package-lock.json`: `acd08d9aa861f1f047b868a49889f3b8f04041539028f7c5ad793b5c2a66bf57`.

Native audit remains held on prior **51 findings (45 high, 6 moderate)**; no new native result or
acceptance claimed. Provider edits, Groq deletion and older shared-document edits stay unpublished.

AC-08 earns 1/1; **prototype estimate 80% = 8/10 acceptance groups**. PROTO-1.2 completes the
first runnable local slice. AC-09 full model quality/timings and AC-10 integrated authenticated
browser/Core/SQLite/Ollama proof remain open. No prototype, mobile MVP, physical or production
completion claim. Manual phone checks remain **skipped by owner; unverified**.
**PROTO-2.1 not started.**
