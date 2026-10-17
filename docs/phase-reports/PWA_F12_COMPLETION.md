# F12 — Chat / Garmin / Settings navigation

- Status: `complete` within F12's bounded implementation/automated scope, 2026-10-16.
- Started at `0d77f8c` on `main`; shell v8 → **v9**. No subsequent phase queued.
- Scope: [F12 plan](../PWA_F12_NAVIGATION.md); dependency-free PWA navigation only.
- Requested execution: `gpt-6.1-sol`, `xhigh`; model/effort selection belongs to caller/UI.
- Baseline: shell v8; **63/63** real-script lifecycle tests pass.
- Held native package files remain excluded from publication, with baseline SHA-256:
  - `mobile/package.json`: `f1f34cd63792e55bd4db5293d3e9189eac0470d7a8fc81c58dbd895cf89796c4`
  - `mobile/package-lock.json`: `acd08d9aa861f1f047b868a49889f3b8f04041539028f7c5ad793b5c2a66bf57`
- Manual phone checks: **skipped by owner; unverified**. M3C authority remains separate.
- No new scopes, enrollment, credentials, route, health read, deployment or native package changes.

## Milestones and acceptance

- [x] Inspect actual Git/source/test state, prior F11 evidence and owner overrides.
- [x] Build Chat (conversation and tasks), Garmin, Settings (device access and logout) surfaces.
- [x] Add persistent accessible navigation, heading focus, back/forward, narrow/wide layouts.
- [x] Preserve session/stream/request/conversation/draft ownership across selections without effects.
- [x] Extend real-script tests for streaming, retry/cancel, obsolete results, logout and offline.
- [x] Verify desktop geometry, keyboard/focus, accessibility tree and hidden-view behavior.
- [x] Advance public shell/script/worker version together; retain cache/API exclusion.
- [x] Complete locked setup, full quality/security gates and synthetic transport benchmark.
- [x] Update architecture/setup/status documentation; publication uses standing authorization.

## Design

Allowlisted fragment views contain only non-sensitive navigation state. Existing DOM and Core
contracts remain shared. Selecting a view never calls connect/enroll/chat/health/notifications/logout.
Inactive view containers use `hidden`; links expose `aria-current="page"`. View headings receive
focus on deliberate selection/back/forward; initial load leaves focus alone. Chat scroll tracking
must account for hidden elements having no layout while an owned reply continues.

Standards reviewed 2026-10-16: [HTML History API](https://html.spec.whatwg.org/multipage/nav-history-apis.html#the-history-interface),
[hidden attribute](https://html.spec.whatwg.org/multipage/interaction.html#the-hidden-attribute),
[WAI aria-current](https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA26).

## Implementation

- `index.html` groups existing controls into retained view containers. Chat opens by default;
  Settings contains device access, status and logout. Connection output stays shared.
- `app.js` allowlists fragment selection and handles popstate/hashchange without duplicate focus,
  uses null browser-history state and moves focus only on deliberate navigation. No view callback
  performs an API action. Existing session/request/generation guards and Core contracts are intact.
- Hidden chat preserves reader position/follow-latest intent without reading zero layout as the
  latest position. Logout reveals Settings, clears all views and avoids late focus theft.
- `app.css` removes positional panel assumptions; wide Settings has two columns, narrow layouts
  reflow. Navigation labels wrap into complete links. Short viewports use normal scrolling so
  enlarged navigation cannot obscure all content. Links retain 44px minimum product targets.
- Script/worker/cache markers advance together to v9, preserving existing shell-only cache rules.

## Automated evidence

Windows, Python **3.11.9**, Node **24.20.0**, Edge **155.0.4283.45**. All fixtures are synthetic;
no account, private route, real transcript or health data is used by navigation acceptance.

| Gate | Result |
| --- | --- |
| Root lock / locked sync | Pass; 119 resolved / 69 checked |
| Garmin sidecar lock / locked sync | Pass; 20 resolved / 16 checked |
| Windows bootstrap | Pass through existing `pwsh` / official CPython 3.11 |
| Ruff format / lint | Pass; 417 files |
| Mypy | Pass; 166 source files |
| Full strict pytest | **1,464 passed / 3 existing optional skips**, **85.67%** coverage, **137.74s**; one existing Starlette deprecation warning |
| Final focused API/chat/lifecycle/transport checks | **36 passed**, **6.15s**, after the final focus/layout adjustments |
| Real-script lifecycle | **73/73** pass; all 63 original cases retained, 10 new navigation cases |
| Desktop layout | **72/72** pass: 3 views × 6 widths (320/375/390/430/844/1280) × 2 default fonts (16/32px) × normal/WCAG text spacing |
| Short viewport | **6/6** pass at 320×211, 16/32px fonts, all views; focused heading visible, no horizontal overflow, navigation scrolls normally |
| Browser behavior / accessibility | Pass: actual back/forward, Enter/Tab, one aria-current link, shared connection status, hidden controls absent from AX tree, history reading position retained |
| Contrast | Pass; logout text 5.79:1, input boundary 4.60–4.92:1, focus 5.75–10.31:1 |
| Root / sidecar dependency audits | No known vulnerabilities |
| Gitleaks history / staged | Pass; 118 baseline commits (~6.94MB) and staged safe source (~42.56KB), no leaks |
| Documentation links / whitespace | Pass; 9 changed documents, 120 relative links, no missing targets; `git diff --check` clear |
| Doctor | Pass with Python UTF-8 output; no authority/configuration changes |
| Transport benchmark | Pass; **100 reconnects / 10,000 events**, zero duplicates/gaps/cross-session deliveries/offline effects/private state retained |

Final transport sample: p50/p95 **0.0426/0.082ms**, RSS growth **0.66MiB**, shell **65,708 bytes**;
unchanged ceilings **25ms / 50MiB / 256,000 bytes**. These are synthetic transport measurements,
not phone performance. No thresholds, skips or audit policy were relaxed.

Commands (all shell work uses RTK):

```powershell
rtk uv lock --check
rtk uv sync --locked
rtk uv lock --project garmin_sync --check
rtk uv sync --project garmin_sync --locked
rtk proxy pwsh -NoProfile -File scripts/bootstrap.ps1
rtk uv run ruff format --check .
rtk uv run ruff check .
rtk uv run mypy src
rtk proxy uv run python -m pytest --basetemp runtime/pwa-f12-final-20261016-1
rtk proxy node --test tests/pwa/garmin-lifecycle.test.cjs
rtk proxy node scripts/pwa-accessibility-check.cjs
rtk proxy uv run python -m pytest --no-cov tests/integration/test_phase8_pwa_web.py tests/unit/test_pwa_garmin_lifecycle.py tests/unit/test_pwa_chat.py tests/unit/test_phase8_pwa_transport.py tests/unit/test_phase8_pwa_benchmark.py --basetemp runtime/pwa-f12-focused-20261016-1
rtk uv run python scripts/phase8c-pwa-benchmark.py --output runtime/mvp4-fixes/f12-transport.json
rtk uv run python -m pip_audit
rtk uv run python -m pip_audit --path garmin_sync/.venv/Lib/site-packages
rtk proxy gitleaks detect --source . --redact --no-banner
rtk proxy uv run python -X utf8 -m jarvis doctor
rtk git diff --check
```

The fresh pytest base resolved inside the ignored workspace runtime directory and did not exist
before execution. Desktop JSON/screenshots/profiles and benchmark JSON stay ignored under
`runtime/mvp4-fixes/`. Final lifecycle, browser and focused checks cover the last layout/focus
adjustments after the full run. Initial doctor output hit Windows cp1252 `OSError: [Errno 22]
Invalid argument`; `python -X utf8` rerun passed without any Windows policy change.

## Limits and handoff

Manual phone checks are **skipped by owner; unverified**. Desktop/synthetic evidence cannot establish
physical iPhone acceptance, spoken VoiceOver, actual phone/browser zoom or aggregate MVP completion.
Historical phone evidence is preserved. No credential, enrollment, health read, scope, route,
server restart, remote deployment or native package work was performed for F12.

Both held native package hashes still match baseline. Their prior unresolved production audit hold
remains; native aggregate verification is not rerun or claimed passing. M3C access decisions remain
separate. Safe source publication excludes held packages and every ignored/private/generated artifact.

Active PWA completion estimate: **94%**, milestone-based. Verified F12 navigation advances the
previous 92% estimate; skipping manual checks adds no acceptance credit. Aggregate MVP 4 remains
incomplete. Stop at F12's boundary; **no subsequent phase queued**.
