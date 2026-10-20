# F15 — PWA daily-use workspace and reliability

Status: **all six authorized F15 milestones complete within repository/automated scope**.
Baseline `29fe496`, `main`, F14 published, shell **v11 → v12**. Date: **2026-10-19**.
Scope: [workspace contract](../PWA_F15_WORKSPACE.md). No subsequent phase queued.

- [x] Inspect Git, instructions, architecture/roadmap/setup and F11–F14 evidence.
- [x] F15A: exact device-owned library, metadata controls, archived browsing and concurrency.
- [x] F15B: bounded safe Markdown/citations/copy and streaming selection/focus stability.
- [x] F15C: Core attachment metadata/provenance/states, deliberate reuse, private idempotency.
- [x] F15D: bounded sanitized task timeline, filters/sorting/pagination/read-only recovery.
- [x] F15E: IME/composer/draft/focus/lifecycle integration and bounded display memory.
- [x] F15F: final full locked quality/security/release gates and documentation; safe-source
  publication under standing authorization, exact refs verified in closing chat.

## Delivered capabilities

- **F15A library:** 20-card Core pages, local bounded titles/excerpts/timestamps, explicit rename,
  pin/unpin, archive/unarchive and archived history. Exact host/device ownership/private denials,
  SQLite read snapshots, optimistic writes and per-device pagination revisions prevent lost/stale
  updates. Search/matching-message navigation and separate drafts/request ownership remain.
- **F15B replies:** text-node-only bounded Markdown subset, readable Core citation markers,
  explicit response/code copy with accessible feedback. No HTML execution, unsafe schemes or
  automatic remote media. Selection/focus/scroll survive streaming and deferred final formatting;
  malformed/oversized formatting falls back to readable text. No new dependency.
- **F15C attachments:** Core-backed metadata/states, content-free request provenance, message source
  hints and explicit ready reuse in the same authorized conversation. Processing/failed/expired/
  unavailable states have recovery, including parser/vision/capacity/interruption. Core validates
  reuse before provider work and fingerprints IDs; private routing/idempotency/quotas stay enforced.
  Four combined files, 1 MiB/file staging retained. No raw download or silent reprocessing.
- **F15D monitoring:** sanitized persisted 50-event timelines, status/verification filters,
  newest/oldest sort, version-guarded list pagination, stable task/earlier-timeline selection and
  reconnect/restart/event-gap recovery. Fixed failure explanations omit arbitrary reason strings,
  private arguments/results/grants. Creation/execution/approval/cancellation remain disabled.
- **F15E integration:** coherent bounded loading/error/empty/stale states; IME-safe deliberate
  submission and multiline editing; twenty nonempty in-session conversation drafts without silent
  eviction; session/logout erasure. History/search/Markdown work and DOM memory are bounded.
- **F15F release:** real auth/SQLite and fake-provider tests, actual Chromium interaction/layout/
  keyboard/AX/copy/selection/memory checks, locked quality/security gates and documentation.

## Automated evidence

Windows; Python **3.11.9**, Node **24.20.0**, uv **0.12.15**, Edge **155.0.4283.62**.
All new account/content fixtures are synthetic. No real histories/files were renamed, archived,
deleted or parsed for testing. Doctor applied/verified normal schema migrations and read readiness;
no production service restart, deployment, control enablement or enrollment was performed.

| Gate | Result |
| --- | --- |
| Root lock/base locked sync | Pass; 119 resolved / 69 base packages |
| Garmin sidecar lock/locked sync | Pass; 20 resolved / 16 packages |
| Windows bootstrap | Pass through existing `pwsh` and official PSF CPython 3.11 |
| Ruff format/lint | Pass; final format check 432 files |
| Mypy | Pass; 168 source files |
| Final strict full pytest, unchanged 85% floor | **1,534 passed / 3 existing optional skips**, **85.91%** coverage, **146.41 s**; one existing Starlette deprecation warning |
| Real-script lifecycle/worklet/cache | **152/152** pass: 145 lifecycle + 7 worklet/cache; 127 original lifecycle cases retained, 18 F15 cases added |
| Focused integrated Core/workflow tests | 53 passed during integration; latest 7 route/lifecycle cases pass |
| Restored pre-existing locked voice extra | 27 optional packages restored; audit clean; **56 focused tests** pass in **8.57 s** |
| Desktop layout/accessibility | Existing 72 view/font/spacing cases, six short-viewport cases, existing 12 F14 + 12 voice cases; new **12 populated F15 width/font cases** pass |
| Actual Chromium interactions | Library paging/rename/pin/archive/unarchive; structured Markdown/citations/copy; IME guard and explicit reuse Send; task timeline paging/focus; named controls/status; disabled task cancellation pass |
| Rendering/DOM/heap stress | 300 short replies retain **200 rows / 1,000 nodes**; 20 large replies retain **5 rows / 500,040 characters / 30 nodes**, post-GC heap growth **511,812 bytes**, below fixed 16 MiB test ceiling |
| Root/base, restored voice, sidecar audits | No known vulnerabilities |
| Gitleaks history | Pass; 122 baseline commits / ~7.19 MB, no leaks |
| Staged secrets / whitespace / document links | Pass; Gitleaks scanned initial **137.87 KB** safe-source diff with no leaks, staged/worktree whitespace clear; **11 changed documents / 99 relative links / zero missing targets** |
| Doctor | Pass; existing private/default-off/$0 boundaries retained |
| Transport benchmark | Pass; **100 reconnects / 10,000 events**, zero duplicates/gaps/cross-session/offline effects/private retention |
| Attachment benchmark | Pass; **100 retrievals / 20 isolated parses**, restart/delete synthetic smoke pass, zero cloud/research/tool effects, $0 |

Final transport: p50/p95 **0.0295/0.0453 ms**, RSS growth **0.719 MiB**, shell **129,872 bytes**;
unchanged ceilings **25 ms / 50 MiB / 256,000 bytes**. Attachment retrieval p50/p95
**4.715/5.188 ms**, parser **110.838/123.111 ms**, max projection **6,655 characters**.
Browser timings/heap and synthetic transport/parser measurements are host evidence, not phone performance.

The first full gate also passed (**1,531 passed / 3 skips**, **85.90%**, **133.56 s**).
Three additional real-middleware expiry/revocation/logout cases and final UI regressions motivated
the final full run above. No test/coverage/security threshold, skip or audit policy was weakened.

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
rtk proxy uv run python -m pytest --basetemp runtime/f15-release-20261019-2
rtk proxy node --test tests/pwa/garmin-lifecycle.test.cjs tests/pwa/pcm-worklet.test.cjs
rtk proxy node scripts/pwa-accessibility-check.cjs
rtk uv run python scripts/phase8c-pwa-benchmark.py --output runtime/mvp4-fixes/f15-transport.json
rtk uv run python scripts/phase-g-attachments-benchmark.py --enforce
rtk uv run python -m pip_audit
rtk uv run python -m pip_audit --path garmin_sync/.venv/Lib/site-packages
rtk uv sync --locked --extra voice
rtk uv run --extra voice python -m pip_audit
rtk proxy uv run --extra voice python -m pytest --no-cov tests/unit/test_pwa_workflows.py tests/unit/test_pwa_workspace.py tests/integration/test_pwa_workspace_web.py tests/integration/test_pwa_voice_web.py tests/unit/test_pwa_voice.py tests/unit/test_pwa_garmin_lifecycle.py -q --basetemp runtime/f15-voice-restored-20261019-1
rtk proxy gitleaks detect --source . --redact --no-banner
rtk proxy gitleaks git --pre-commit --staged --redact --no-banner
rtk proxy uv run python -X utf8 -m jarvis doctor
rtk git diff --check
```

Pytest bases, browser profiles/screenshots/JSON and generated helper scripts stay under ignored
workspace `runtime/`. Base sync removed optional speech packages normally; existing locked voice
extra was restored/audited before closure. No dependency source or model weight was changed/downloaded.

## Integration defects and recovery coverage

Found/fixed asynchronous attachment failure losing accepted composer text: restore original draft
only when empty; preserve newer typing. Added owned read snapshots for attachment/history races.
No coverage/security threshold relaxed. New migration-inventory expectation includes additive 019.

Also cancelled task-list reads across offline/navigation boundaries so an old body cannot reappear
after reconnect. Metadata refresh cannot steal focus from another view/control. Current conversation
and task selections expose `aria-current`. Search/history trimming preserves selected/focused rows;
older history trims the opposite edge so earlier-message navigation still works.

Regression coverage retains F11/F14 response-loss retry, same-ID cancellation races, stalled/stale
bodies, rapid selection, offline/backoff, key-preserving expiry/revocation, logout, Core receipts,
restart and event gaps. F15 adds cross-connection metadata conflicts, archive/private denial, source
reuse/replay/expiry/cross-conversation denial, processing/cancellation metadata, safe event paging/
adapter restart, hostile Markdown/citations/model text, IME and copy failure, stale library/metadata/
timeline bodies, accepted-failure draft restoration and late task-list bodies after reconnect.
Browser fixtures exercise actual DOM/selection/keyboard/AX/XHR/worklet behavior; Python HTTP fixtures
exercise real authentication middleware, SQLite and synthetic identities/providers. Neither fixture
type claims a physical phone or live provider acceptance result.

## External limits, publication and estimate

Remaining authority limits: remote task cancellation lacks authorized control capability;
task schema lacks trustworthy conversation relationship. Both stay disabled/uninferred. Local
vision capability remains dependent on existing host configuration; no model download/enablement.
Manual phone checks **skipped by owner; unverified**. No physical/MVP acceptance claimed.

Held native SHA-256 values match baseline and both files remain excluded:

- `mobile/package.json`: `f1f34cd63792e55bd4db5293d3e9189eac0470d7a8fc81c58dbd895cf89796c4`
- `mobile/package-lock.json`: `acd08d9aa861f1f047b868a49889f3b8f04041539028f7c5ad793b5c2a66bf57`

Production defaults, authentication, approvals, private routing and $0 remain enforced. No real
history/attachment was modified for testing. Synthetic browser artifacts and test databases stay ignored.

F15 authorized scope: **6/6 milestones delivered (100%)**. Active PWA feature estimate: **98%**,
advancing prior 96% on verified library/reply/attachment/monitoring/recovery milestones. Remote
task-control authority, native dependency hold and aggregate physical acceptance remain separate.
Skipping phone checks adds no acceptance credit. No subsequent phase queued.
