# Prototype Scope Triage

Audit date: **2026-10-22**. Delivery sequence/acceptance belongs only to
[PROTOTYPE_PLAN.md](PROTOTYPE_PLAN.md). This file holds evidence and scope dispositions, not another
roadmap. Original planning audit only: no application implementation, deletion or dependency upgrade.

**2026-10-22 follow-up:** PROTO-1.1 repaired the root/sidecar dependency baseline; current audits
pass. [PROTO_1_1_EVIDENCE.md](PROTO_1_1_EVIDENCE.md) records versions, gates and publication isolation.
The audit results below remain historical starting evidence, including the native failure/hold.
PROTO-1.2 has not started. Manual phone checks remain **skipped by owner; unverified**.

## Audited baseline and evidence limits

Checkout: `C:\Users\poyan\Desktop\JARVIS Desktop`; branch `main`; local HEAD and tracking ref
`fb5ef47` at audit start. Recent history: F15 `fb5ef47`, F14 `29fe496`, F13 `96f3294`, F12 `7517e6a`.
No fresh upstream fetch is substituted for publication verification. There are **168 Python source
files, 144 Python test files, 19 SQL migrations**, a dependency-free PWA, separate native npm
workspace and isolated Garmin Python 3.12 environment. Counts describe the current worktree,
including pre-existing provider edits, not a clean checkout of HEAD.

Read root AGENTS/RTK instructions; README; complete numerical playbook; master/overview; both
architecture documents; technology decisions; checkpoint; expansion; PWA F11–F15 contracts and
completion/progress evidence; Garmin connector/MVP3 evidence; mobile architecture/milestones and
M1/M2/MVP1 evidence; relevant core, memory, identity, provider, research, task, wearable and
proactivity reports. Followed setup, security/ownership and dependency references where relevant.
Inspected entry points, composition, routing/configuration, PWA assets/cache, durable chat stores,
authentication middleware, Garmin subprocess boundary, native screens, test suites and CI.

Status vocabulary:

- **Implemented and verified:** named behavior present and current automated evidence supports it;
  historical live evidence is identified by date, not silently renewed.
- **Implemented but unverified:** code exists but the relevant current target/usefulness proof did
  not run. Fakes do not establish live provider/device acceptance.
- **Partially implemented:** missing user-facing capability or an unfinished aggregate path.
- **Planned only:** no production implementation found for the claimed workflow.
- **Deferred or blocked:** held outside this prototype or prevented by a specific unresolved gate.

### Current verification (this run)

| Check | Result and limit |
| --- | --- |
| Root `uv lock --check` / `uv sync --locked` | Pass; 119 resolved. Base sync removes optional extras by design; existing voice/vision extras restored before closure |
| Garmin lock check | Pass; 20 resolved; no live Garmin read, login, token inspection/import or enrollment |
| Ruff format / lint | Pass; 433 files at baseline; no source formatting applied |
| Mypy | Pass; 168 source files |
| Full pytest | **1,533 passed, 3 skipped, 85.97% coverage, 168.54 s**; unchanged 85% floor; one existing Starlette warning |
| Pytest launcher | `uv run pytest` blocked by App Control, OS error **4551**; allowed `uv run python -m pytest --basetemp runtime/proto-audit-pytest-20261022 --tb=short` passes. No Windows policy changed |
| Desktop PWA harness | `node scripts/pwa-accessibility-check.cjs` passes: 72 layout cases plus assertions for navigation, keyboard, accessibility tree, voice/attachment/workspace fixtures and bounds. Synthetic APIs; not real-model or phone acceptance |
| Root dependency audit | **FAIL: 44 advisories in 3 packages**: certifi 2026.7.22, Pillow 12.3.0, pypdf 6.19.0. Historical clean audits are dated only |
| Garmin environment audit | **FAIL: 1 advisory**, certifi 2026.7.22 (`PYSEC-2026-4320`); independent of live account availability |
| Held native lock-only production audit | **FAIL: 51 findings: 45 high, 6 moderate, 0 critical**, using `npm audit --package-lock-only --omit=dev --audit-level=high --json`; no install/fix performed; not a native verification pass |
| Gitleaks history | Pass; 123 commits, about 7.33 MB, no leaks; final changed-document review is separate |
| Planning documents / preservation | Pass; 14 documents, 157 relative links, zero missing targets; whitespace clear; docs Gitleaks scan clean. All 20 pre-existing dirty paths outside edited documents byte-identical (including held native files/deletion); 12 shared documents receive additions only; index remains empty |
| Workstation readiness | Ollama listens on `127.0.0.1:11434`; `qwen3:0.6b` installed. No listener on 8765 at observation; Core not started during audit |
| Live product checks | No model generation, owner-data mutation, provider login, Garmin read, production route change or physical phone check performed. Current useful-answer quality and complete real PWA/Core/Ollama path remain unverified |

Commands invoked through RTK. Python is 3.11.9. Current tests exercise the dirty working snapshot;
do not label them exact-HEAD or future-commit evidence. Existing optional/platform skips remain
skips; no mandatory test was disabled. Headless browser artifacts and pytest fixtures stay under
ignored `runtime/`. Root quality passed except vulnerability audit; there is no aggregate release
pass and no commit/push in this planning run while that mandatory gate remains failed.

Official dependency information reviewed for **planning**, not an upgrade authorization/result:
[pypdf changelog](https://pypdf.readthedocs.io/en/stable/meta/CHANGELOG.html) lists current 6.21.2
security work; [Pillow 13.0.0 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html)
list security fixes and incompatible API changes, including removal of Python 3.10 support.
The audit's suggested fixes require compatibility review. Current `Pillow <13`
constraint means an ordinary lock refresh cannot solve all reported findings. Recheck current
advisories and Python 3.11 wheels in PROTO-1.1; do not assume a major update is drop-in.

### Verified state by product area

| Area | Classification | Evidence and precise limit |
| --- | --- | --- |
| Core text, local privacy/router, deterministic tools | Implemented and verified automatically | `core/runtime.py`, `llm/routing.py`, `security/policy.py`, `tools/`; current runtime/routing/contract/policy tests. Current real answer quality/timing unverified |
| PWA identity, session, stream and chat recovery | Implemented and verified automatically | `remote/{service,browser,signing,pwa,chat,chat_store}.py`, `web.py`; current integration/security/lifecycle tests. Historical physical Phase 8 and partial F11 evidence retained |
| F12 navigation / F14 search / F15 library | Implemented and verified automatically | Real `pwa/app.js`, shell v12, migrations 017–019, workspace/web tests and desktop harness; no fresh physical acceptance |
| Conversation and durable memory | Implemented and verified automatically | Shared SQLite stores, migrations 001–005, FTS5 and exact promotion/delete tests. PWA history is not a full memory administration UI |
| PWA voice / attachments | Implemented; automated verification current, live use unverified here | `voice/pwa.py`, `remote/attachments.py`, `attachments/`; F13 historical synthetic-audio local STT; features default off. No current microphone or private document use |
| Task engine and PWA monitoring | Partially implemented as an interactive PWA task product | `planning/` scheduler and read-only projection exist; no chat-to-task creation/control UX. `client.tasks.read` cannot cancel. No trustworthy persisted task/conversation relationship |
| Controlled OS actions | Implemented but current live closeout unverified | `computer/`, broker/permissions, adversarial tests; Phase 3 report explicitly `implemented-closeout-pending` despite its COMPLETION filename |
| Research | Implemented and verified with fixtures; live source access blocked historically | `research/`, freshness/projector, Phase C report; last Wikimedia smoke returned `authentication_required`; no configured reviewed SearXNG endpoint. No new live claim |
| Garmin | Protected Core path historically verified; full phone path partial/deferred | `garmin/service.py`, `bridge.py`, `garmin_sync/`; M3B 2026-10-08 protected import and bounded live summary passed. M3C health scope authority separate; physical checks skipped/unverified |
| Native client | Partial; held | M1/M2 auth/pairing/status/rotation implemented; current `mobile/app/index.tsx` and `garmin.tsx` are placeholders. Native build unverified, current dependency audit fails |
| Gestures/vision | Implemented; automatic regression and historical device evidence | `vision/`, `gestures/`; dated Phase 7 real camera/soak evidence. Dormant; no new capture this run |
| Email | Partial | Local exported-email read/prepare in `email/`, tested; no live email adapter. Phase IB blocked on provider/account authority; sending absent |
| Calendar/background briefing | Planned only | Expansion J/L/M; existing proactivity runner is explicit foreground suggestion processing, not a resident worker or integrated morning briefing |
| Proactivity/maintenance | Implemented bounded foundation; broader autonomy planned/deferred | `proactivity/`, `maintenance.py`; current tests, dated Phase 11 evidence. No background autonomous effects, merge/deploy or external-send authority |
| Distributed topology | Implemented repository boundary; live activation blocked/deferred | `remote/{topology,migration,resilience,deployment}.py`, Phase 9 report; no authorized target/live split proof. Local-only remains prototype |
| Generic wearables | Contract/fake implemented; real adapter planned/deferred | `wearables/{contracts,models,fake}.py`; Phase 10B/C owner-deferred. No production glasses/watch bridge |

## Scope cuts

“Remove from prototype dependency” means it need not be installed, enabled, connected or accepted
to demonstrate the selected workflows. It does **not** mean delete implementation, its tests,
migrations, reports, credentials or runtime data. Shared packages still subject to repository/CI
audits must be repaired even when their feature is dormant.

| Area | Evidence/current state | Keep now / Simplify / Hold / Remove candidate | Reason | Prototype impact | Reactivation condition |
| --- | --- | --- | --- | --- | --- |
| PWA vs native | v12 PWA has real chat/workspace; native chat/Garmin placeholders, held package audit | **Keep now PWA; Hold native** | Reuse verified flow; avoid duplicating auth/UI/device work | One primary client; no Expo/npm build prerequisite for PWA | Required native-only capability, passing audit, authorized build/signing path |
| Legacy CLI/browser | Both call same Core; root loopback UI differs from `/app/` | **Keep now CLI; Simplify product guidance** | Useful operator fallback without another product UI effort | One advertised PWA; no screen parity work | Specific operator need |
| Provider proliferation | Worktree has Ollama/NVIDIA/Gemini; pre-existing Groq removal not published; HEAD still differs | **Simplify: one local model; Hold cloud roles** | Avoid credentials, quota, terms and hosted latency on critical path | $0 offline-capable inference; preserve privacy/fallback contracts | Fixed local corpus demonstrates a public-task gap and current provider terms/cost pass |
| Model upgrades/large local models | Ten model tags installed; current small-model usefulness unknown | **Hold until measured** | Installed weight is not usable response evidence | Benchmark default first; no download requirement | Failure of fixed corpus; bounded existing-candidate comparison |
| Memory | Mature Core lifecycle/FTS5; PWA owns history projection only | **Keep now storage/context; Hold new UI/vector infrastructure** | Reuse recall boundaries; avoid second memory owner | Durable conversation continuity; no profile feature expansion | Measured workflow/retrieval gap |
| Advanced agent autonomy | Durable DAGs, inert proposals, foreground proactivity exist | **Hold execution/daemon/swarm** | Task/control UX and authority add no text-demo value | No worker, schedule, autonomous effects or recursive delegation | Explicit useful task, bounded budget and exact grants/evaluation |
| Task views | Read-only timelines/filtering exist; cancellation disabled | **Hold from required prototype surface** | Disabled control is not an implementation bug to bypass | Avoid new task scope and misleading controls | Owner selects task-monitoring workflow; control requires separately approved boundary |
| Gestures/vision | Optional OpenCV/Pillow capture/detector and historical proof | **Hold** | Camera, calibration, device/performance effort unrelated to text | No capture/model asset setup; source and tests remain | Specific hands-free workflow and applicable capture/effect gates |
| Voice | Local Windows voice and PWA STT draft path implemented, default off | **Hold as optional completed feature** | More audio/device/model readiness without essential text value | No voice extra/model download/phone mic prerequisite | Text prototype useful and owner prioritizes foreground input |
| Attachments/OCR | Text/PDF/image flow implemented, optional vision, default off | **Hold required workflow; retain implementation** | Parser/resource/security burden; existing real feature need not be removed | Avoid file setup and weak multimodal quality as demo blocker | Explicit document workflow after patched parser/image stack and local model checks |
| Email/calendar | IA local exports complete; IB and J unimplemented/blocked | **Hold** | OAuth/accounts/private communication disclosure and write authority | No account or message-send prerequisite | Owner-selected workflow/provider and exact authority |
| Garmin/health | Protected session and bounded summary historically pass; health-scoped phone path unfinished | **Hold first-demo dependency** | New scope plus vendor/session/freshness path not needed for text proof | Removes sidecar/live health read from runtime demo; mandatory repo sidecar audit still applies | After prototype, owner prioritizes read-only health and grants only needed scopes |
| Standalone Garmin reporter | `scripts/garmin_report.py`, `garmin/report.py` and ignored connector generate broader local reports | **Hold; preserve** | Competing token refresh owners can diverge | Core remains sole protected-session owner; do not run two copies | Explicit standalone diagnostic with safe session ownership; no automatic reimport |
| Other wearables/health analytics | Generic simulator; Meta/glasses/watch and analytics not active | **Hold** | Vendor access, hardware, privacy and bridge complexity | No hardware/account dependency | Proven capability/terms, explicit scope, useful post-prototype workflow |
| Research/current web | Fixture-verified acquisition; live Wikimedia failure preserved | **Hold live research; Keep freshness honesty** | Search service repair should not gate local text | Explicit unavailable-evidence response; no fabricated live citations | Reviewed working source and existing public-only privacy/citation gates |
| Distributed topology | Mature manifests/backup/receipts; live server unverified | **Hold placement/cutover** | One owner/writer is enough | No server, WSL, Docker, network DB, shared replay service or migration | Measured capacity/availability need and authorized target |
| Deployment variants | Tailscale Serve/private TLS exists; native/systemd/container variants documented | **Keep now existing private route; Hold variants** | Fewer deployable components and operating modes | No public hosting, Funnel, signing, App Store, new service installation | Explicit deployment requirement plus authority and security gates |
| Core dependencies | 12 declared runtime packages; Pillow/pypdf shared by dormant parsers/vision; audits now fail | **Keep and patch; Hold optional extra installation for fresh prototype setup** | Removing packages without refactoring consumers breaks gates; hidden feature is not security remediation | Preserve minimal base; no new dependency. Patch actual installed/audited stack first | Packaging split only if measured install/security benefit beats compatibility work |
| Overlapping planning | Numerical, lettered, native, Garmin and F-series tracks disagree on next action | **Simplify to canonical PROTO plan; Remove candidate: duplicate active roadmap prose** | Repeated status maintenance caused stale gates and percentages | One sequence; keep reports and technical references | Legacy track only on explicit request; do not auto-resume |
| Broad cleanup/refactor | Large `web.py`, CLI, compact PWA JS and many existing adapters | **Hold** | Rewrite/deletion introduces risk without proving a faster demo | Fix named AC gaps only | Repeated concrete defect or measured maintainability bottleneck |

### Garmin recommendation

Garmin is **not essential to first demonstration**. It is a different value proposition—health
summary access—than dependable private assistant conversation. M3A/M3B are valuable completed
work and should remain dormant, not be redone. Core already owns the protected session; do not
rediscover/reimport it, inspect token values or run the standalone copy. No health data reaches
model providers. M3C's unresolved health enrollment authority is not waived; outstanding physical
checks remain **skipped by owner; unverified**, never queued as prototype prerequisites.

## Conflicts and stale guidance

| Location | Conflict verified | Resolution for active work |
| --- | --- | --- |
| `PHASE_OVERVIEW.md`, `JARVIS_MASTER_ROADMAP.md` | F15 says no next phase and 98%; mobile definition still requires Garmin/full phone acceptance | Canonical PROTO scope/acceptance wins for delivery; keep dated 98% and old MVP definition as history |
| `JARVIS_CHECKPOINT.md`, `AGENTIC_ASSISTANT_EXPANSION.md` | Next IB email conflicts with mobile/PWA order; audit gap table predates attachments/automatic research | Explicit historical/backlog banner; no IB work queued |
| `CODEX_PHASE_PLAYBOOK.md` | Section 13 labels Phase 7 “9A complete, 9B next”; section 18 still marks 7A–C/9C not started, contradicting reports/source | Preserve as legacy text; do not derive prototype prerequisites from stale rows. Reports + current tests determine behavior |
| `README.md`, `PWA_GARMIN.md`, older handoffs | v11/v9/v8/v10 claims coexist with actual `jarvis-shell-v12`; native pairing described pending despite later evidence | Source v12 plus dated reports identified in canonical plan; old sections explicitly historical, not current readiness |
| `MOBILE_ARCHITECTURE.md` | Calls PWA fallback despite active PWA-first path | Banner explicitly makes PWA primary and native body historical/held |
| `MOBILE_PHASES.md`, older phone runbooks | Native M2C/physical actions appear prerequisite; fresh routine permission wording lingers | Root override applies; no phone requests/reminders or routine permission renewal; consequential gates persist |
| `JARVIS_ARCHITECTURE.md` | Conceptual module names and continuous wake latency advice exceed actual layout/defaults | Target-design history only; actual owners in PROTO plan and implementation architecture |
| `architecture.md` | Says camera/screen future despite implemented Phase 7; Phase G paragraph excludes PWA uploads while F14 adds them | Historical phase-local statements are not current capability absence; actual code/reports govern |
| `TECHNOLOGY_DECISIONS.md` | Historical Groq roles remain beneath pre-existing removal notice; optional cloud roles presented as defaults | Current working edits are unpublished; prototype local-only policy independent of that change |
| `docs/roadmap.md` | Stops at Phase 6/older local latency and phase statuses | Superseded planning pointer; retain dated evidence, no parallel updates |
| Completion filenames | Phase 3 COMPLETION still pending live effects; Phase C COMPLETION retains live endpoint failure | Classify body/evidence, not filename; preserve failures |
| Security/data ownership | Master roadmap's generic “memory-only bearer” language differs from browser cookie design | Distinguish native signed bearer from browser HttpOnly cookie/CSRF; do not merge identity types |

No historical failed latency sample, skipped phone row, audit result or incomplete legacy phase
is reclassified as passed by the new plan. No pending permission request is repeated as planning.

## Deletion and dependency recommendations

**No code, package, report, runtime or user-data deletion is justified for immediate prototype
delivery.** Exact candidates and consequences below are deliberately conditional. No deletion
performed. Consolidating active guidance through banners/pointers delivers the benefit now.

| Exact paths | Consumers / coupling verified | Recommendation and migration consequence |
| --- | --- | --- |
| `src/jarvis/llm/groq.py` (already deleted in pre-existing dirty worktree) | HEAD bootstrap/diagnostics/config, `llm/__init__.py`, cloud-provider/config tests, `.env.example`, provider docs; current source search finds no Groq consumer | Do not restore as a prototype requirement or claim this run deleted it. Existing removal needs its own provenance review/gates/publication. It shares httpx, so no independent package saving |
| `docs/roadmap.md` | README links it; historical documents use broader roadmap references | Candidate to replace duplicate active prose with a short canonical pointer later; keep the path to avoid broken links. Preserve historical text in Git/history/reports; no deletion needed now |
| `docs/AGENTIC_ASSISTANT_EXPANSION.md`, `docs/JARVIS_CHECKPOINT.md` | README, playbook, overview/master, `TOKEN_CONTINUITY.md`, Phase F and other historical contracts reference them | Keep paths and evidence; supersede active sequencing. Deleting breaks historical navigation and recreates migration work without prototype benefit |
| `mobile/`, `mobile/package.json`, `mobile/package-lock.json`, `.github/workflows/mobile-ci.yml` | Native routes/auth/crypto/UI, tests, mobile CI, Dependabot npm config and native docs | Hold intact. Deletion would require retiring CI/dependency updates/docs and loses reusable signed identity work; no PWA speed benefit. Never publish held candidates by staging the directory |
| `garmin_sync/`, `src/jarvis/garmin/`, `scripts/garmin_report.py`, `scripts/garmin_core_check.py` | `web.py` imports normalized Garmin service; report reuses bridge normalization; tests and Python CI lock/sync/audit the sidecar | Remove only from required demo setup/refresh. Literal deletion breaks imports/tests/CI and risks session ownership; keep source, token store and reports intact |
| `pypdf` and `pillow` declarations in `pyproject.toml`, corresponding `uv.lock` entries | `attachments/_worker.py`, `research/_parser_worker.py`, diagnostics, image/capture paths and tests | Patch current vulnerabilities first. Optional packaging split is a later measured candidate, requiring lazy-import/install/parser/CI/extra coverage. Deleting dependency lines alone is not remediation |
| `voice` / `vision` optional groups in `pyproject.toml`; `src/jarvis/voice/`, `vision/`, `gestures/` | CLI lazy voice/capture commands, web voice service, computer hands-free typed contracts and tests | Do not require extras on a fresh text-only setup. Do not delete modules/groups; removing shared types breaks nonvoice imports. Restore workstation extras removed by routine base sync |
| `src/jarvis/proactivity/`, `planning/`, `email/`, `wearables/`, remote topology modules; migrations 001–019 | Composition, CLI, schema migrations, runtime security and broad regression tests | Dormant, not dead code. No removal without independent consumer/migration proof; never drop historical tables/migrations to make prototype smaller |

Do not create a mass cleanup phase. Only remove a dependency/component later when an actual
prototype blocker demonstrates net benefit and exact consumer migration tests are included.

## Existing work and publication boundary

At start **27 dirty paths** existed: 25 tracked modifications/deletion and two untracked files.
Nothing was staged. They are independent of the requested planning work:

- Provider/removal/support changes: `.env.example`, `src/jarvis/bootstrap.py`, `config.py`,
  `current_context.py`, `diagnostics.py`, `llm/__init__.py`, `llm/gemini.py`, `llm/nvidia.py`, deleted
  `llm/groq.py`; `tests/contract/test_cloud_providers.py`, `tests/integration/test_attachment_web.py`,
  `tests/unit/test_config.py`; untracked `src/jarvis/llm/http_errors.py`, `docs/GROQ_DEFERRED.md`.
- Shared pre-existing documentation edits: README, expansion, playbook, hardware report, both
  architecture documents, security model, technology decisions, old roadmap, security and setup.
  This run adds explicit planning banners/links only; their older edits remain separate.
- Held native `mobile/package.json` and `mobile/package-lock.json` match F15's recorded SHA-256:
  `f1f34cd63792e55bd4db5293d3e9189eac0470d7a8fc81c58dbd895cf89796c4` and
  `acd08d9aa861f1f047b868a49889f3b8f04041539028f7c5ad793b5c2a66bf57` respectively.

Before-document snapshots and dirty-file hashes were saved under ignored `runtime/proto-audit/`
to verify preservation and isolate future hunks. They contain source/document evidence, not copied
runtime databases or credentials. They are not publication artifacts. Mandatory audit failure
held the planning run's commit/push. PROTO-1.1 isolates the planning banners against these snapshots
and publishes only reviewed planning/dependency/evidence changes. Held native files, provider edits
and older shared-document edits remain unpublished; their working bytes/deletion are preserved.

## Material uncertainties

- Local small-model usefulness and current cold/warm latency: must measure, not assume historical
  TTFT means acceptable answers. Alternative installed models may cost RAM/latency.
- Dependency compatibility was resolved in PROTO-1.1 using current primary advisories, locked
  installs and parser/image regressions; see the follow-up evidence. No parser API rewrite needed.
- Existing production PWA identity/HTTPS route readiness: not inspected through private credentials
  or changed. Synthetic integration can proceed without a new production enrollment. Core was
  stopped at observation; prototype operational startup is still required.
- Current browser + real auth + real model integrated behavior: layer tests are strong but do not
  prove this combined current configuration. PROTO-2.1 owns that proof.
- Native security and health enrollment remain separate holds; neither is a blocker for the
  selected text prototype. Outstanding phone checks: **skipped by owner; unverified**.

No missing information currently changes architecture. No phone tasks, reminders, new credentials,
health access or public deployment are requested by this plan.
