# F14 — complete PWA assistant workflows

Status: implementation and automated release gates complete; remote task cancellation
**blocked-external** by existing read-only authority. Safe-source publication follows standing authorization.
Date: **2026-10-19**. Baseline: `96f3294`, `main`, F13 complete within automated/repository scope,
shell **v10 → v11**. [Workflow and setup contract](../PWA_F14_WORKFLOWS.md).
Scope: attachments, Core-owned conversation search/management, task list/details/recovery.

- [x] Inspect Git, instructions, architecture, roadmap and F12/F13 evidence.
- [x] Implement bounded memory staging and explicit-Send Core attachment integration.
- [x] Implement owned, bounded search and matching-history navigation with memory-only drafts.
- [x] Implement task list, details, progress/failure and stale-state recovery.
- [x] Automated functional/security/accessibility workflow acceptance.
- [x] Final full release gate and safe-source publication preparation; exact Git refs verified at close.

Task cancellation blocker: existing remote identity supports `client.tasks.read` only. No remote
task-control scope or approved mutation adapter exists. Scheduler cancellation remains available
on trusted host. PWA Cancel task remains disabled; no new scopes or enrollment authorized.

Manual phone checks: **skipped by owner; unverified**. Physical/MVP acceptance remains incomplete.
Native manifests held unchanged and excluded from publication. $0, private/local processing,
authentication, approvals, default-off controls and native dependency hold remain enforced.

## Delivered milestones

**F14A — attachments:** bounded authenticated uploads into session-owned Core memory, upload
progress/cancellation, safe photo/text/PDF previews and removal, explicit Send before existing
extraction/private persistence. Late upload/cancel/session/navigation/visibility/offline/logout
results cannot restore selections. No upload/model retry or Send is automatic. Accepted requests
retain existing durable idempotency and cancellation; parser failures keep actionable guidance
and text drafts. Existing local vision capability is reused, with unavailable interpretation
reported honestly; no model download or cloud fallback. PWA ceiling is four files at 1 MiB each.

**F14B — search and conversation management:** bounded body-only literal search against exact
Core-owned, attributed device history; readable excerpts, pagination and matching-page navigation.
Separate memory-only drafts survive conversation selection. Current request ownership blocks
switching. Stale query/response/session results are rejected. No private browser persistence/cache.
Migration 018 records PWA attachment-origin provenance while preserving local/email-private denial.

**F14C — task views:** paginated list, details, completed/total steps, attempts, failure class,
completion/cancellation-request/reconciliation state, stale labels, explicit refresh, foreground
30-second checks and authenticated reconnect/event recovery. Model output cannot enable controls.
Arguments, outputs and approval grants are omitted. Remote task cancellation is **blocked-external**
by the authority constraint above; trusted-host scheduler controls remain available.

**F14D — release:** architecture, setup, status and roadmap updated. All safe source is intended
for publication under standing commit/push authorization; exact refs are verified in closing chat.
No production runtime restart/deployment or configuration enablement is part of this bundle.

## Automated evidence

Windows; Python **3.11.9**, Node **24.20.0**, uv **0.12.15**, Edge **155.0.4283.62**.
All new inputs are generated public/synthetic fixtures; no private files or real phone used.

| Gate | Result |
| --- | --- |
| Root lock/base locked sync | Pass; 119 resolved, 69 base packages |
| Garmin sidecar lock/locked sync | Pass; 20 resolved, 16 packages |
| Windows bootstrap | Pass through existing `pwsh`, official CPython 3.11 |
| Ruff format/lint | Pass; 428 files |
| Mypy | Pass; 168 source files |
| Final full strict pytest, unchanged 85% floor | **1,527 passed / 3 existing optional skips**, **85.84%** coverage, **142.23 s**; one existing Starlette deprecation warning |
| New focused Python workflow tests | 7 unit + 15 HTTP cases pass |
| Real-script lifecycle/worklet/cache | **134/134** pass (127 lifecycle + 7 worklet/cache); all 96 prior lifecycle cases retained |
| Desktop layout | **72/72** existing view/font/spacing cases, **12/12** populated F14 cases, six short-viewport cases, existing 12 voice cases |
| Actual browser F14 behavior | Pass; real File/Blob/XHR uploads, text/photo/PDF previews, text-only rendering, named progress, keyboard removal, lifecycle cleanup, disabled cancellation |
| Existing browser behavior | Pass; keyboard/back/forward/AX/contrast/history/selection and synthetic AudioWorklet |
| Root/base and sidecar dependency audits | No known vulnerabilities |
| Restored locked voice extra | 27 pre-existing optional packages restored; audit clean; **63** focused workflow/voice tests pass in **9.47 s** |
| Gitleaks history | Pass; 121 commits scanned, no leaks |
| Documentation links | Pass; **9** changed documents / **118** relative links / zero missing targets |
| Staged secrets / whitespace | Pass; Gitleaks scans **107.32 KB** safe-source diff with no leaks; staged/worktree `git diff --check` clear |
| Doctor | Pass; default-off controls/private boundary intact |
| Transport benchmark | Pass; 100 reconnects / 10,000 events; zero duplicates/gaps/cross-session/offline effects/private retention |
| Attachment benchmark | Pass; 100 retrievals / 20 isolated parses; restart/delete pass; zero cloud/research/tool effects; $0 |

Final transport sample: p50/p95 **0.0402/0.0823 ms**, RSS growth **0.637 MiB**, shell **95,294 bytes**;
unchanged ceilings **25 ms / 50 MiB / 256,000 bytes**. Attachment retrieval p50/p95
**2.642/3.254 ms**, isolated parser **102.434/107.942 ms**, max projection **6,655 characters**.
These are synthetic host measurements, not phone performance. Local vision was not requested.

Initial full gate exposed one migration-inventory test frozen at 017: **1 failed / 1,526 passed /
3 existing optional skips**, **85.82%** coverage, **130.07 s**. Updated expected inventory to include
additive 018; no test/coverage/security threshold relaxed. The final full gate above follows that repair
and final attachment failure/focus fixes.

Commands use RTK and locked environments:

```powershell
rtk uv lock --check
rtk uv sync --locked
rtk uv lock --project garmin_sync --check
rtk uv sync --project garmin_sync --locked
rtk proxy pwsh -NoProfile -File scripts/bootstrap.ps1
rtk uv run ruff format --check .
rtk uv run ruff check .
rtk uv run mypy src
rtk proxy uv run python -m pytest --basetemp runtime/f14-release-20261019-2
rtk proxy node --test tests/pwa/garmin-lifecycle.test.cjs tests/pwa/pcm-worklet.test.cjs
rtk proxy node scripts/pwa-accessibility-check.cjs
rtk uv run python scripts/phase-g-attachments-benchmark.py --enforce
rtk uv run python scripts/phase8c-pwa-benchmark.py --output runtime/mvp4-fixes/f14-transport.json
rtk uv run python -m pip_audit
rtk uv run python -m pip_audit --path garmin_sync/.venv/Lib/site-packages
rtk uv sync --locked --extra voice
rtk uv run --extra voice python -m pip_audit
rtk proxy uv run --extra voice python -m pytest --no-cov tests/unit/test_pwa_workflows.py tests/integration/test_pwa_workflows_web.py tests/integration/test_pwa_voice_web.py tests/unit/test_pwa_voice.py --basetemp runtime/f14-voice-restored-20261019-1 -q
rtk proxy gitleaks detect --source . --redact --no-banner
rtk proxy gitleaks git --pre-commit --staged --redact --no-banner
rtk proxy uv run python -X utf8 -m jarvis doctor
rtk git diff --check
```

Pytest bases were checked fresh, under ignored workspace `runtime/`. Browser profiles/screenshots,
synthetic benchmark JSON and generated helpers remain ignored. Base sync removed optional speech
packages as expected; the pre-existing locked voice extra is restored/audited before closure.
No manifest/lock source changes or downloaded model weights are required.

## Blockers and remaining acceptance

Only unfinished F14 capability: remote task cancellation. There is no existing task-control scope
or approved remote mutation adapter. New enrollment/scopes are explicitly excluded; granting them
through `client.tasks.read`, model output or a new route would violate this bundle's constraints.
The UI explains trusted-host cancellation and stays disabled. No decision blocks independent work.

Phone checks remain **skipped by owner; unverified**, with no acceptance credit. Aggregate MVP 4
and physical acceptance remain incomplete. Native held manifest hashes match baseline:

- `mobile/package.json`: `f1f34cd63792e55bd4db5293d3e9189eac0470d7a8fc81c58dbd895cf89796c4`
- `mobile/package-lock.json`: `acd08d9aa861f1f047b868a49889f3b8f04041539028f7c5ad793b5c2a66bf57`

Both are excluded from publication; their pre-existing native dependency audit hold remains.
Estimated active PWA completion: **96%**, based on verified connection/chat/Garmin/navigation/voice
and F14 attachment/search/task-view milestones. This advances the previous 94% feature estimate;
remote task-control authority and aggregate physical acceptance remain open. No next phase queued.
