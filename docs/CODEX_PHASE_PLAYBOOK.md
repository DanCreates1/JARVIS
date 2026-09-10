# JARVIS Codex Phase Playbook

Updated: 2026-09-08
Owner command: `Initiate Phase X and finish it.`  
Phase range: 0–11

This is the authoritative Codex execution playbook for JARVIS phases. The root `AGENTS.md` loads
this file whenever the user starts, continues, or finishes a phase. The master roadmap describes
product direction; this file tells Codex how to execute and prove the work.

## 1. Command contract

Accepted trigger examples:

```text
Initiate Phase 2 and finish it.
Start phase 3.
Continue Phase 4 from the progress report.
Finish Phase 1 acceptance closeout.
```

On a trigger, Codex must:

1. Parse exactly one phase number from 0–11. If multiple phases are requested, execute only the
   earliest prerequisite phase unless the user explicitly authorizes a multi-phase program.
2. Read this file completely, then read the selected phase references.
3. Inspect reality: Git status, existing implementation, tests, environment, hardware, credentials
   by variable name only, and previous progress/completion reports.
4. Reconcile the documented status with observed evidence.
5. Create a milestone plan and a durable progress report before substantial implementation.
   Name the active lettered subphase from Section 18.
6. Execute without repeatedly asking about ordinary reversible implementation choices.
7. Stop for user input only at the authority boundaries listed below.
8. Finish only after every applicable exit criterion has current evidence.
9. Stop after five elapsed hours, including audit, implementation, tests, documentation, and
   handoff. At four hours, stop starting broad work and reserve the final hour for gates, evidence,
   recovery, and a resume-safe boundary.

The phrase `finish it` requires persistence across bounded sessions, but cannot grant new authority,
waive safety, or permit a five-hour overrun. If discovered work cannot fit its named subphase,
define the next coherent lettered subphase in this playbook and the roadmap before continuing.

## 2. Codex model and reasoning assignments

These are Codex execution models, not JARVIS runtime provider roles. Reasoning effort is chosen in
the Codex UI or caller configuration; instructions cannot switch it. Availability was checked
against this host on 2026-09-08.

| Phase | Recommended model | Reasoning | Reason |
| --- | --- | --- | --- |
| 0 | `gpt-5.6-sol` | `medium` | Bounded repository/reproducibility/secret audit; Astra only when history or provenance is ambiguous |
| 1 | `gpt-6-astra` | `xhigh` | Provider/privacy architecture and difficult hosted-latency diagnosis; Sol handles named routine subphases |
| 2 | `gpt-6-astra` | `xhigh` | Real-time cancellation, device failure, capture privacy, latency, noise, and GPU contention |
| 3 | `gpt-6-astra` | `ultra` | Authorization, approval integrity, OS effects, rollback, and irreversible-action risk |
| 4 | `gpt-6-astra` | `xhigh` | Durable privacy schema, provenance, deletion, conflicts, retrieval quality |
| 5 | `gpt-6-astra` | `xhigh` | SSRF/parser isolation, hostile sources, evidence integrity, and citations |
| 6 | `gpt-6-astra` | `ultra` | Bounded autonomy, durable effects, budgets, recovery, approval-aware planning |
| 7 | `gpt-6-astra` | `max` | Media privacy and perception-to-action false activation |
| 8 | `gpt-6-astra` | `ultra` | Remote identity, revocation, trusted approval, TLS, web attack surface |
| 9 | `gpt-6-astra` | `ultra` | Distributed state, migration, backup/restore, partition and rollback |
| 10 | `gpt-6-astra` | `max` | Cross-device identity, media privacy, vendor limits and live hardware |
| 11 | `gpt-6-astra` | `ultra` | Proactivity, schedules, multi-device ownership, privacy and host-control guarantees |

Exact supported reasoning values for `gpt-6-astra`, `gpt-5.6-sol`, and `gpt-5.6-terra` are `low`,
`medium`, `high`, `xhigh`, `max`, and `ultra`; `gpt-5.6-luna` stops at `max`; `gpt-5.4-mini` stops
at `xhigh`. `Extra high` is retired; use `xhigh`. Luna or Mini may perform isolated mechanical
inventory/docs/test maintenance, never security design or phase closure. A listed setting is the
minimum recommendation. Do not lower it to meet a deadline.

## 3. Authority boundaries

Codex may autonomously perform normal reversible implementation inside the repository: inspect,
design, edit source/docs/tests, install locked development dependencies, run tests, launch local
loopback services, use fake providers, and perform bounded live smoke tests with already-configured
free credentials when public test data is guaranteed.

Codex must request user authority before:

- paying, enabling billing, upgrading a provider plan, or accepting a new material legal term;
- creating accounts, rotating/revoking credentials, changing access control, or exposing a port;
- sending private/sensitive data to any cloud provider;
- deploying to a remote machine, domain, phone, server, wearable, or public environment;
- controlling real applications/devices beyond an already-approved test fixture;
- printing, communicating, purchasing, deleting user data, powering off, or making irreversible
  system changes;
- pushing Git branches/tags/releases, opening PRs, or messaging third parties unless explicitly
  requested;
- broadening the selected phase to complete missing prerequisite phases.

When blocked by one of these boundaries, finish every safe local prerequisite, record the exact
blocker and verification command, then ask one concise question.

## 4. Universal execution protocol

### Step 1 — Establish baseline

- Read `README.md`, `docs/PHASE_OVERVIEW.md`, selected phase references, recent Git history, and
  current progress reports.
- Run `git status --short --branch`; preserve all unrelated changes.
- Inventory relevant source, tests, scripts, migrations, configuration, and hardware/software.
- Validate assumptions against current official primary documentation when facts can change.
- Record baseline failures separately from regressions introduced during phase work.

### Step 2 — Resolve prerequisites

- Confirm prerequisite phases through tests/evidence, not labels.
- If a prerequisite is incomplete but only a small interface stub is needed, implement the minimal
  safe interface within selected phase scope and document the debt.
- If completion requires substantial earlier-phase work, mark selected phase `blocked-prerequisite`
  and request permission to execute that prerequisite phase.

### Step 3 — Define acceptance

- Convert selected phase deliverables and exit criteria into checkboxes in
  `docs/phase-reports/PHASE_X_PROGRESS.md`.
- Add explicit functional, failure, security, privacy, performance, recovery, documentation, and
  clean-install checks.
- Define quantitative targets before tuning. Never move thresholds merely to make tests pass.

### Step 4 — Design boundaries first

- Extend provider-neutral typed contracts before vendor/OS adapters.
- Keep permissions and policy outside model prompts.
- Define timeouts, size limits, retries, cancellation, idempotency, audit, and error taxonomy.
- Threat-model new data flows and side effects before enabling them.
- Prefer feature flags and deny-by-default configuration for unfinished/high-risk paths.

### Step 5 — Implement vertical milestones

- Build the smallest useful end-to-end slice first.
- Add unit and contract tests with fakes before requiring real hardware/services.
- Add real adapter behavior behind the same contract.
- Run targeted checks after each milestone.
- Update progress report after each verified milestone so another Codex session can resume.

### Step 6 — Test failure and abuse

At minimum cover invalid input, missing dependency, timeout, cancellation, quota/capacity loss,
malformed provider/device response, restart, duplicate/replayed request, permission denial, data
boundary violation, and safe degradation. Add phase-specific attacks listed below.

### Step 7 — Run acceptance on real target

- Keep ordinary CI hardware/network-independent.
- Run explicit live tests separately on the Windows laptop and configured free providers/devices.
- Record model/device/runtime versions, settings, cold/warm state, and dated results.
- Never include private sample content in reports.

### Step 8 — Run complete release gate

```powershell
uv lock --check
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv run pip-audit
gitleaks detect --source . --redact --no-banner
git diff --check
uv run jarvis doctor
```

Add phase-specific benchmark/security suites. No skipped mandatory check may be called passing.

### Step 9 — Close documentation

- Update architecture, security, setup, configuration examples, hardware results, and roadmap.
- Update `docs/PHASE_OVERVIEW.md` status and remaining work.
- Convert the progress report to a completion report containing commands, results, known limits,
  deferred scope, and recovery instructions.
- Ensure no documentation claims unverified capability.

### Step 10 — Handoff

- Report outcome first, then tests/evidence, files changed, remaining risks, and exact next phase.
- Keep worktree changes uncommitted unless user authorized commit.
- If commit/push was authorized, verify local HEAD, tracking ref, and remote ref match.

## 5. Universal definition of done

A phase is `complete` only when all apply:

- Every required deliverable has implementation and documentation.
- Acceptance tests demonstrate supported happy paths.
- Failure, privacy, security, cancellation, restart, and recovery paths are tested.
- No model output directly authorizes or constructs privileged execution.
- Mutable data has migration, retention, export/deletion, backup, and recovery behavior as relevant.
- Performance evidence includes p50/p95 or the phase-specified metrics with sample count.
- Setup is reproducible on the target Windows topology.
- Full quality, vulnerability, secret, and Git gates pass.
- Live hardware/provider/device checks pass where required, or external blockers are explicitly
  recorded and phase remains incomplete.
- Documentation and status files match actual behavior.

Allowed status values:

- `not-started`
- `in-progress`
- `blocked-prerequisite`
- `blocked-external`
- `implemented-closeout-pending`
- `complete`

### Audited current state

Audited 2026-09-08 at `96143e7` before this rewrite: Python 3.11 modular monolith; 94 source files,
72 test files, 65 test modules, nine migrations, and 532 static test declarations. Installed tools
included `uv 0.12.5`, Git 2.55.0, Gitleaks 8.30.1, and Node 24.20.0. Bare `python` resolved only to
the disabled Windows Store alias; repository commands use `uv run`.

Actual status, reconciled 2026-09-10: Phase 1 has an external hosted-latency blocker and a fresh
local-cold revalidation miss; Phases 2-3 are implemented with current authorized live effects
pending; Phases 4-7 are complete; Phase 8A-8B identity/browser hardening is complete while 8C-8D remain;
Phase 9 onward is not implemented. No root license exists, so copying external code is
blocked on an owner licensing decision. No external code was copied. See
[External Repository Comparison](EXTERNAL_REPOSITORY_COMPARISON.md).

## 6. Phase 0 — Repository baseline and reset verification

Recommended execution: **`gpt-5.6-sol`, `medium`**
Baseline status: **complete; maintain continuously**

### Read first

- `docs/PHASE_0_REBUILD_PLAN.md`
- `.gitignore`
- `.github/workflows/ci.yml`
- `scripts/bootstrap.ps1`
- `scripts/quality.ps1`

### Objective

Maintain a reproducible, secret-free Git source of truth while preserving intended history and
keeping runtime/private artifacts outside Git.

### Required work

- Verify origin, branches, archive refs, local/remote SHAs, and worktree ownership.
- Confirm Python version, `uv.lock`, bootstrap, model setup, quality script, and CI pins.
- Confirm ignore coverage for secrets, environments, databases, logs, models, media, caches, and
  local configuration.
- Run local and CI secret scans against full relevant history.
- Classify every dirty/untracked file before staging; preserve unrelated user changes.
- Verify bootstrap from a clean clone or clean Windows test environment.
- Document optional-tool absence without hiding mandatory CI enforcement.

### Acceptance and exit

- Fresh clone bootstraps with documented commands.
- Quality and secret gates pass.
- No secret, private runtime data, or model artifact is tracked.
- Reviewed local commit equals intended remote ref when push was authorized.
- Archive/history requirements in rebuild plan remain satisfied.

### Never do

- Never rewrite published history, force-push, delete archives, or remove legacy evidence without
  explicit user authorization.
- Never use a destructive Git reset to clean user changes.

## 7. Phase 1 — Core and first text vertical slice

Recommended execution: **`gpt-6-astra`, `xhigh`**
Baseline status: **blocked-external; hosted latency remains unfixed and current local-cold p50 also requires revalidation**

### Phase 1 latency closure governance

Keep product responsiveness and provider acceptance separate. Tier 0 deterministic/direct paths,
Tier 1 local-first interaction, Tier 2 responsive cloud, context reduction, health-aware fallback,
or voice response ownership may mitigate user impact. None changes a Tier 3 NVIDIA measurement.

The 1D NVIDIA simple/complex p50/p95 thresholds below remain hard provider-specific requirements
under this playbook. The universal definition of done requires a live external gate to pass and says
an external blocker leaves the phase incomplete. Allowed status values contain `blocked-external`
but no completed-with-limitation state. Therefore:

- use `PASS` only when NVIDIA itself meets all fixed 20/20 gates;
- keep `STILL BLOCKED`/`blocked-external` when it does not;
- never report routed local/Groq latency as NVIDIA latency; and
- use `CLOSED WITH EXTERNAL PROVIDER LIMITATION` only after an explicit owner governance revision
  adds that closure state and its evidence requirements. Such a revision is a release-policy
  decision, not benchmark tuning, and must not mark the NVIDIA-specific gate green.

### Read first

- `docs/architecture.md`
- `docs/security.md`
- `docs/HARDWARE_REPORT.md`
- `docs/TECHNOLOGY_DECISIONS.md`
- `docs/JARVIS_MASTER_ROADMAP.md` Phase 1

### Objective

Deliver useful privacy-aware text JARVIS with swappable models, deterministic local routing,
zero-dollar cloud use, local fallback, persistence, safe typed tools, CLI/browser interfaces, and
measurable behavior.

### Required capability

- Provider-neutral model/message/tool/routing/usage contracts.
- Ollama local provider plus configuration-driven NVIDIA/Groq/Gemini adapters.
- Deterministic sensitivity gate before any cloud disclosure.
- Hard `$0` cloud budget, catalog diagnostics, bounded retry, quota/outage/model-removal fallback.
- Bounded conversation/tool loop, structured events/errors, cancellation propagation.
- SQLite migrations, conversations, basic memory/audit records, deletion APIs.
- Typed read-only tools with schema validation, allowlisted roots, risk metadata, and policy.
- One-shot/interactive CLI and loopback-only browser JSON/SSE interface.

### Current closeout work

- Run 20+ representative cold/warm local and hosted samples; record p50/p95, versions, model
  digests, context/output settings, and failure counts.
- Reproduce bootstrap/setup on a clean Windows environment.
- Confirm live NVIDIA quota observations without probing limits destructively.
- Re-run privacy-route, tool-denial, quota, outage, catalog-removal, and zero-spend scenarios.

### Acceptance and exit

- Simple/normal/reasoning/sensitive/override requests choose expected routes.
- Sensitive and uncertain content never crosses cloud boundary.
- Both Nemotron models pass live public smoke tests; offline/local mode works.
- Provider outage/429/removal falls back without paid service.
- Restart preserves authorized state; explicit deletion works.
- Unsupported/side-effecting tools fail closed.
- Full release gate plus dated p50/p95 and clean-machine evidence pass.

## 8. Phase 2 — Voice

Recommended execution: **`gpt-6-astra`, `xhigh`**
Baseline status: **implemented-closeout-pending; current live device evidence requires authority**
Prerequisite: Phase 1 event stream/cancellation stable

### Read first

- `docs/JARVIS_MASTER_ROADMAP.md` Phase 2
- `docs/JARVIS_ARCHITECTURE.md` voice sections
- `docs/HARDWARE_REPORT.md`
- `docs/HANDS_FREE_CONTROL.md`
- Phase 1 completion/progress report

### Objective

Add local-first push-to-talk, then wake-word duplex conversation with streaming speech, barge-in,
text fallback, device diagnostics, and optional clap-event intents.

### Required design

- Ports: `AudioInput`, `VADProvider`, `STTProvider`, `TTSProvider`, `WakeWordProvider`, and local
  acoustic-event detector.
- Start with push-to-talk; do not enable always-listening until privacy/false-trigger gates pass.
- Candidate evaluation: faster-whisper/whisper alternative, Silero VAD, Piper/local TTS,
  openWakeWord, and lightweight local clap detection.
- Typed timestamped partial/final transcript and audio-output events.
- Duplex state machine for listen/transcribe/think/speak/interrupted/error.
- Barge-in cancels queued/current TTS without corrupting conversation state.
- Echo/AEC or render-reference suppression prevents self-triggering.
- Device selection persists; missing/disconnected device degrades to text.
- Visible listening state, software kill switch, and documented physical mute path.

### Testing

- Fixed quiet/noisy/accented speech corpus with WER and end-of-speech latency.
- False accept/reject tests for wake word and double clap across music, TV, typing, and normal room
  noise.
- Interruption, device removal, driver error, timeout, restart, and 30-minute soak tests.
- CPU/GPU/RAM/VRAM measurements while local LLM is loaded.
- Verify private speech never uses cloud STT/TTS without explicit policy/configuration.

### Exit

- Push-to-talk works end-to-end with text fallback.
- Barge-in stops audible output promptly and state recovers.
- Selected devices survive restart or fail clearly.
- WER/latency/false-trigger metrics meet declared thresholds or documented exceptions.
- Always-listening/wake/clap remains disabled until soak, indicator, and kill-path gates pass.

## 9. Phase 3 — Controlled computer access

Recommended execution: **`gpt-6-astra`, `ultra`**
Baseline status: **implemented-closeout-pending; current live OS effects require authority**
Prerequisite: Phase 1 typed tools/policy; local trusted approval interface

### Read first

- `docs/SECURITY_MODEL.md`
- `docs/security.md`
- `docs/HANDS_FREE_CONTROL.md`
- `docs/JARVIS_MASTER_ROADMAP.md` Phase 3
- Phase 1 report and Phase 2 report when audio intents are used

### Objective

Permit narrow authorized Windows actions through deterministic typed tools and a trusted permission
broker. Never expose unrestricted shell, model-generated command strings, or always-admin JARVIS.

### Required design

- Permission levels 0–4 with exact risk semantics.
- Trusted approval broker/UI outside untrusted model/chat content.
- Expiring single-operation grants bound to action, normalized arguments, user/session, and time.
- Audit receipt covering proposal, approval/denial, execution, postcondition, error, and rollback.
- Fixed executable identities and argument arrays; no shell interpolation or `Invoke-Expression`.
- Canonical allowlisted filesystem roots and application identifiers.
- Initial actions: launch configured app/app group, volume/media, bounded clipboard/browser/status,
  read/search, reversible file operations, then printing.
- Hands-free intents map to allowlisted typed actions; gestures never become raw commands.
- API-first app control; isolated UI automation only when no stable API exists.

### Security tests

- Path traversal/symlink/junction escape, argument injection, executable substitution.
- Prompt/tool-output injection and confused-deputy attempts.
- Stale/replayed/cross-session approval tokens.
- Cancellation before/during/after partial effects.
- Idempotency, postcondition mismatch, rollback, application-not-found, printer errors.
- Double-clap/gesture false activation cannot trigger sensitive/destructive actions.

### Exit

- Every shipped tool has schema, risk class, timeout, result cap, approval rule, audit, tests,
  postcondition, and recovery behavior.
- No arbitrary shell or broad filesystem/application permission exists.
- App launch, media/volume, and first reversible action work through broker on Windows.
- Adversarial suite fails closed; gestures alone cannot approve high-risk work.

## 10. Phase 4 — Durable memory and personalization

Recommended execution: **`gpt-6-astra`, `xhigh`**
Baseline status: **complete**
Prerequisite: Phase 1 persistence, audit, host identity

### Read first

- `docs/JARVIS_MASTER_ROADMAP.md` Phase 4
- `docs/JARVIS_ARCHITECTURE.md` memory sections
- `docs/SECURITY_MODEL.md`
- existing migrations/models/store/tests

### Objective

Provide useful inspectable recall without dumping full history into prompts or silently converting
model guesses into facts.

### Required design

- Separate candidate, committed, corrected, expired, and deleted memory states.
- Typed categories for preferences, profile facts, projects/tasks, summaries, and source links.
- Provenance to conversation/message/tool/import; confidence and sensitivity labels.
- Explicit promote/correct/forget/export workflows and configurable retention.
- SQLite FTS5 baseline plus measured embeddings only when retrieval evaluation proves benefit.
- Relevance/recency scoring, deduplication, contradictions, and user-visible retrieval reasons.
- Derived summaries/indexes maintain transitive deletion.
- Per-host/user isolation ready for later remote clients.

### Testing and exit

- Golden retrieval set reports precision/recall and accepted-hit rate.
- Poisoned, injected, stale, and contradictory memories are surfaced, not silently merged.
- Correction supersedes old facts without erasing audit provenance.
- Deletion removes/invalidates all derived indexes and prompt projections.
- Restart, migration, backup/restore, corrupt record, and concurrent access tests pass.
- Memory viewer explains source and retrieval reason.

## 11. Phase 5 — Research and self-education

Recommended execution: **`gpt-6-astra`, `xhigh`**
Baseline status: **complete**
Prerequisite: Phase 4 provenance model; sandboxed browser/retrieval; injection defenses

### Read first

- `docs/JARVIS_MASTER_ROADMAP.md` Phase 5
- `docs/SECURITY_MODEL.md` untrusted-content rules
- Phase 4 memory schema/report

### Objective

Research current topics with citations, source diversity, conflict reporting, freshness awareness,
and safe separation between hostile source content and executable instructions.

### Required design

- Provider-neutral search/fetch/document contracts with URL/type/size/time limits.
- Source provenance, access/publish dates, quoted-word limits, claim-to-source links.
- Primary/authoritative source preference and explicit inference labeling.
- Untrusted page/PDF text treated as data; never tool/policy instructions.
- Sandboxed parsing, safe redirects, private-network/localhost denial, download/content limits.
- Research plan, evidence table, contradictions, uncertainty, and citation-complete answer.
- Store only approved research artifacts; do not silently create trusted memory.

### Testing and exit

- Benchmark tasks measure citation coverage, claim entailment, source diversity, freshness, conflict
  handling, and reproducibility.
- Prompt injection, malicious links/files, SSRF, oversized content, paywall/login, and unavailable
  source cases fail safely.
- Every material current claim has nearby supporting citation or explicit uncertainty.
- Basic cited browser research satisfies MVP closure target.

## 12. Phase 6 — Planning and bounded agents

Recommended execution: **`gpt-6-astra`, `ultra`**
Baseline status: **complete**
Prerequisites: Phase 3 permissions, Phase 4 memory, Phase 5 research

### Read first

- `docs/JARVIS_MASTER_ROADMAP.md` Phase 6
- `docs/JARVIS_ARCHITECTURE.md` tasks/agents sections
- `docs/SECURITY_MODEL.md`
- completion reports for Phases 3–5

### Objective

Execute bounded multi-step tasks with durable state, explicit budgets, approvals, cancellation,
resumption, and recovery. Plans never expand permissions.

### Required design

- Typed task graph with dependencies, state machine, owner, provenance, deadlines, and budgets.
- Limits for steps, wall time, tokens, provider requests, retries, tools, cost, and concurrency.
- Checkpoint before/after each external effect; idempotency and reconciliation on restart.
- Planner proposes; deterministic scheduler validates and executes allowed nodes.
- Approval tokens remain operation-specific and cannot be reused by later plan nodes.
- Bounded parallelism only for independent read-only work.
- Cancel/pause/resume, partial-success reporting, compensating action, and orphan recovery.
- No self-modifying policy, recursive unbounded delegation, or hidden background activity.

### Testing and exit

- Golden task graphs test ordering, dependencies, budgets, retries, cancellation, and resumption.
- Crash/restart at every state transition reconciles without duplicate side effects.
- Prompt injection cannot add nodes, tools, permissions, recipients, or budgets.
- Exhausted budget stops clearly and preserves resumable state.
- Supported multi-step tasks meet completion/recovery targets with full audit trail.

## 13. Phase 7 — Vision and gestures

Recommended execution: **`gpt-6-astra`, `max`**
Baseline status: **not started**  
Prerequisite: Phase 3 permission broker and media privacy controls

### Read first

- `docs/JARVIS_MASTER_ROADMAP.md` Phase 7
- `docs/HANDS_FREE_CONTROL.md`
- `docs/JARVIS_ARCHITECTURE.md` vision sections
- Phase 3 completion report

### Objective

Add low-latency local screen/camera perception and configurable hand gestures, escalating to an
expensive multimodal model only for permitted public content and when local fast paths are
insufficient.

### Required design

- Camera/screenshot ports with explicit source, region, frame rate, purpose, and retention.
- Visible camera/screen indicators and technically enforced off state.
- OpenCV preprocessing and MediaPipe Hand Landmarker candidate.
- Temporal gesture state machine, confidence, debounce, cooldown, calibration, handedness, and
  rate limits.
- Initial gestures: closed-fist cancel, open-palm media, pinch mute, clockwise/counter-clockwise
  finger-roll volume, then optional swipe/navigation/approval signals.
- Mapping store is `gesture -> typed intent`; Phase 3 alone maps intent to allowed action.
- OCR/object/scene local paths; cloud image disclosure requires separate privacy classification.

### Testing and exit

- Recorded/live datasets cover lighting, distance, occlusion, skin tones, backgrounds, handedness,
  camera positions, similar movements, and absence of a hand.
- Report accuracy, precision/recall, false activations/hour, latency, CPU/GPU use, and thermals.
- Thirty-minute soak has no action storm or resource leak.
- Camera off means no capture; ambiguous/conflicting gesture does nothing.
- Gestures cannot exceed permission grant or approve sensitive/destructive work.

## 14. Phase 8 — Secure phone/PWA access

Recommended execution: **`gpt-6-astra`, `ultra`**
Baseline status: **8A-8B complete; 8C-8D not started (listener remains loopback-only)**
Prerequisites: stable internal API/events; Phase 3 permissions; device identity model

### Read first

- `docs/JARVIS_MASTER_ROADMAP.md` Phase 8
- `docs/JARVIS_ARCHITECTURE.md` network/API sections
- `docs/SECURITY_MODEL.md` remote-access sections
- current `src/jarvis/web.py` and tests

### Objective

Provide a secure authenticated phone/PWA client without exposing JARVIS directly to the public
internet or weakening local privacy/permission boundaries.

### Required design

- Private network/Tailscale-first topology, TLS, application authentication, and device enrollment.
- Per-device keys/tokens, secure storage, rotation, revocation, expiry, and session management.
- CSRF/origin checks, strict CORS, CSP, secure cookies/tokens, input/body/rate limits.
- Conversation/task streaming with reconnect/resume and no cross-session leakage.
- Permission prompts bind to trusted device identity and action; sensitive approvals may require
  local confirmation.
- PWA install/offline shell, clear connectivity state, notification controls, and remote kill.
- Audit login, revocation, approval, denial, and suspicious activity without logging secrets.

### Testing and exit

- Threat tests cover brute force, token replay/theft, CSRF, XSS, origin confusion, device spoofing,
  revoked sessions, network loss, and malicious payload size/rate.
- No unauthenticated non-loopback access.
- Enrollment/revocation works on real phone and Windows host.
- Network loss degrades safely; private/local functions remain available on laptop.

## 15. Phase 9 — Dedicated server migration

Recommended execution: **`gpt-6-astra`, `ultra`**
Baseline status: **not started**  
Prerequisite: stable internal ports, Phase 8 identity/network model

### Read first

- `docs/JARVIS_MASTER_ROADMAP.md` Phase 9
- architecture/security deployment sections
- Phase 8 completion report

### Objective

Move selected compute/state to a dedicated server through configuration and adapters while the
laptop retains defined offline capability and no business-logic rewrite is required.

### Required design

- Explicit topology: local-only, split, or server-primary with documented data ownership.
- Mutual service identity, encrypted transport, certificate/key rotation, and least privilege.
- Version/capability negotiation and compatible migrations.
- State ownership preventing split-brain; reconciliation after partition.
- Encrypted backup, restore, disaster-recovery objectives, health/telemetry, and capacity plan.
- Deployment/update/rollback automation and laptop offline fallback.

### Testing and exit

- Same acceptance suite passes local and split topologies.
- Simulate latency, packet loss, partition, server crash, stale version, disk full, and restore.
- Migration and rollback are rehearsed from verified backup.
- Network loss never silently discloses data or duplicates side effects.
- Core location changes through configuration/deployment only.

## 16. Phase 10 — Wearables and Meta glasses

Recommended execution: **`gpt-6-astra`, `max`**
Baseline status: **not started; lower priority**  
Prerequisites: Phase 8 secure client protocol; Phase 7 media controls

### Read first

- `docs/JARVIS_MASTER_ROADMAP.md` Phase 10
- Phase 7 and Phase 8 completion reports
- current official device/vendor documentation and program terms

### Objective

Support at least one wearable interaction through generic device interfaces without making the
core depend on Meta or any single vendor.

### Required design

- Generic wearable capability negotiation for audio, display, camera, notifications, and input.
- Phone bridge when direct device API is unavailable.
- Per-capability permission, enrollment, revocation, visible camera/mic state, and bystander policy.
- Battery/network-aware streaming and explicit unsupported-capability errors.
- Vendor adapter isolated from core protocols; simulator/fakes for CI.

### Testing and exit

- Confirm real-device capability matrix from current official APIs, not marketing assumptions.
- Test revocation, network loss, phone bridge loss, battery constraints, media indicators, and
  unsupported features.
- One real wearable interaction works through generic interface.
- Removing vendor adapter leaves core behavior intact.

## 17. Phase 11 — Advanced JARVIS

Recommended execution: **`gpt-6-astra`, `ultra`**
Baseline status: **not started; long-term**  
Prerequisites: dependable permissions, memory, research, agents, clients, and observability

### Read first

- `docs/JARVIS_MASTER_ROADMAP.md` Phase 11
- all prerequisite completion reports
- current security, privacy, cost, and autonomy policies

### Objective

Add proactive, scheduled, multi-device, and deeper multimodal assistance only after on-demand
JARVIS is safe, reliable, inspectable, and easy to disable.

### Required design

- User-authored schedules/triggers with scope, timezone, expiry, quiet hours, and rate limits.
- Candidate proactive suggestions separated from autonomous execution.
- Per-feature autonomy budgets and default-off controls.
- Cross-device coordination with single ownership, deduplication, and visible active-task state.
- Notification relevance controls, snooze, disable, deletion, and feedback.
- Cost, privacy, power, and attention budgets enforced outside models.
- Full provenance explaining why JARVIS acted/suggested and which data/tools were used.

### Testing and exit

- Simulated clock/timezone/DST, duplicate events, restart, offline device, stale memory, and noisy
  trigger tests.
- Proactive features meet explicit host usefulness/annoyance/privacy thresholds.
- Disable switch stops new proactive activity and cancellation handles active work.
- Disabling/removing proactive features does not degrade core on-demand JARVIS.

## 18. Five-hour phase and subphase execution matrix

The phase sections above provide aggregate objective, scope, prerequisites/dependencies,
deliverables, testing, security/privacy, acceptance, and exit. Universal Steps 1-10 provide the
sequence and documentation requirements. This table makes session count, split order, exclusions,
and exact model assignments explicit.

| Phase | Sequence and expected sessions | Aggregate exclusions | Aggregate documentation and exit | Model rationale |
| --- | --- | --- | --- | --- |
| 0 | One audit session per material baseline change | History rewrite, archive deletion, private/generated Git data | Rebuild/setup/overview/report; clean clone, scans, refs and gates pass | `gpt-5.6-sol` `medium`: bounded audit |
| 1 | 1A -> 1B -> 1C -> 1D; four build sessions plus one per external retry | Paid/privacy downgrade, effects, public bind, provider-specific core | Architecture/security/setup/hardware/technology/report; all fixed route/reliability/TTFT gates pass | Astra for privacy and hard latency; Sol for known implementation |
| 2 | 2A -> 2B -> 2C; three sessions | Default continuous listening, retained audio, unapproved cloud speech, voice approval | Voice/setup/hardware/hands-free/report; current live device, quality, kill and soak gates pass | Astra for duplex/capture safety; Sol for ports/closeout |
| 3 | 3A -> 3B -> 3C; three sessions | Shell, generated commands, admin, broad grants, gesture/voice approval | Security/controlled access/hands-free/setup/report; full tool control records and current live evidence pass | Astra ultra/max for authorization and OS effects |
| 4 | 4A -> 4B -> 4C; three sessions | Silent/cross-host memory, unmeasured vectors, private Git/cloud memory | Architecture/security/config/report; lifecycle, retrieval, isolation, deletion gates pass | Astra for durable privacy/retrieval; Sol for closeout |
| 5 | 5A -> 5B -> 5C; three sessions | Login/paywall bypass, arbitrary/private fetch, source authority, silent memory | Architecture/security/research/report; bounded cited lifecycle benchmark passes | Astra for network/parser/synthesis trust; Sol for ledger closeout |
| 6 | 6A -> 6B -> 6C; three sessions | Swarm, recursion, hidden daemon, self-policy, planner tools, paid work | Architecture/bounded-tasks/security/report; zero bad states/effects/budget violations | Astra for autonomy; Sol for bounded interfaces/evidence |
| 7 | 7A -> 7B -> 7C; three sessions | Hidden capture, biometrics, raw commands, unclassified cloud images, gesture approval | Architecture/security/hands-free/hardware/report; fixed live/recorded metrics and soak pass | Astra where media crosses authority; Sol for bounded CV evaluation |
| 8 | 8A -> 8B -> 8C -> 8D; four sessions | Public unauthenticated API, weak device trust, approval bypass, multi-replica | Threat/API/enrollment/deployment/report; real private phone, revoke, scan, offline pass | Astra for identity/security/deploy; Terra for bounded PWA |
| 9 | 9A -> 9B -> 9C; three sessions | Premature services/databases, multi-primary, public admin, one-way migration | Topology/ownership/operations/DR/report; local/split parity and restore/rollback pass | Astra ultra/max for distributed trust/data |
| 10 | 10A -> 10B -> 10C; three sessions | Marketing assumptions, hidden media, vendor core, unapproved unofficial connector | Feasibility/license/adapter/privacy/report; real generic flow and adapter-removal pass | Sol for feasibility; Astra for cross-device/live privacy |
| 11 | 11A -> 11B -> 11C -> 11D; four sessions | Hidden activity, model authority/budgets, unbounded agents, surveillance, unjustified training | Autonomy/operations/privacy/evaluation/report; fixed long-duration and removal gates pass | Astra ultra/max because autonomy compounds every boundary |

Every subphase row explicitly uses: O objective; S scope; P prerequisites/dependencies; D
deliverables; X exclusions; Q implementation sequence; T functional/failure tests; SP security and
privacy; M documentation; A acceptance; E exit criteria; N expected sessions; R exact model,
reasoning, and rationale. Universal requirements still apply.

### Completed and closeout subphases

- **1A Contracts/config/persistence (`complete`)** — O/S: owned messages, roles, events, settings,
  migrations, conversations, explicit memory/audit/delete. P: Phase 0/SQLite. D: contracts, stores,
  tests. X: cloud/rich memory/privileged tools. Q: schema -> migration/store -> restart/delete. T:
  validation, upgrade, concurrency, corruption, bounds. SP: private defaults, host isolation,
  redacted errors. M: architecture/setup/report. A: offline state works. E: restart/delete/gates.
  N: 1. R: `gpt-5.6-sol` `high`, mature cross-cutting patterns.
- **1B Providers/routing/privacy (`complete`)** — O/S: adapters, stream/usage, local classification,
  catalog, free/local fallback. P: 1A and optional configured keys/terms. D: router/contract tests.
  X: prompt authorization, paid/privacy downgrade. Q: threat -> adapters -> router -> live. T: route
  matrix, malformed SSE, timeout, 429/outage/removal/quota/cancel. SP: classify first, uncertain
  local, content-free logs. M: dated provider/privacy/config. A/E: observable safe swap/fallback.
  N: 1. R: `gpt-6-astra` `xhigh`, interacting trust boundaries.
- **1C Tools/interfaces (`complete`)** — O/S: bounded orchestration/personality, read tools, CLI,
  loopback web/SSE. P: 1A-B. D: schemas, roots, risk, caps, cancel, audit, UI. X: shell/effects/
  non-loopback. Q: policy/fakes -> tools -> CLI -> web -> abuse. T: iteration, traversal, output,
  injection, disconnect, session. SP: output cannot change policy; session isolation. M: README,
  architecture/security/setup. A/E: offline interfaces fail closed. N: 1. R: `gpt-5.6-sol`
  `high`, mature integration.
- **1D Performance/closeout (`blocked-external`)** — O/S: reproduce setup/fixed benchmark. P: 1A-C,
  Ollama, public NVIDIA. D: dated safe metrics/completion report. X: private prompts, quota probing,
  threshold weakening. Q: freeze settings -> 20/state -> diagnose -> tune -> gate. T: route/fallback/
  privacy and first-visible-token harness. SP: public fixtures, zero spend. M: hardware/overview/
  roadmap/report. A/E: p50/p95 deterministic 300/800 ms, local 1,500/3,000, hosted simple
  1,000/2,500, hosted complex 3,000/7,000; 20/20 each. N: 1/retry. R: `gpt-6-astra` `max`, hard
  external latency diagnosis.
- **2A Push-to-talk/adapters (`complete`)** — O/S/D: capture -> VAD/STT -> core -> TTS, ports/events/
  workers/devices. P: Phase 1. X: continuous capture. Q: fakes -> local adapters -> health/fallback.
  T: WER, absent/removed device, malformed audio, timeout/crash/cancel/restart. SP: local, bounded
  buffers, no retention. M: voice/config/setup/report. A/E: end-to-end plus text fallback. N: 1.
  R: `gpt-5.6-sol` `high`, known concurrent adapters.
- **2B Duplex/wake safety (`complete`)** — O/S/D: state machine, interruption, echo, wake/clap,
  indicator/kill behind default-off. P: 2A. X: action authority/continuous release. Q: threat/state
  -> cancel -> duplex -> detector -> soak. T: every transition, music/TV/typing/noise, stuck worker/
  leak. SP: acoustic input untrusted; kill dominates. M: voice/hands-free/security. A/E: prompt stop,
  recovery, detector bounds. N: 1. R: `gpt-6-astra` `xhigh`, races plus capture privacy.
- **2C Device closeout (`implemented-closeout-pending`)** — O/S: current Windows device proof. P:
  2A-B plus mic/render authority. D: sanitized evidence/report. X: personal recordings/hidden
  enablement. Q: inventory -> live/loss/barge/kill -> load/soak -> gates. T: selection/reconnect/
  offline/LLM contention. SP: consent, visible/ephemeral, cloud off. M: hardware/setup/overview/
  roadmap/report. A/E: all current device gates. N: 1. R: `gpt-5.6-sol` `high`, evidence closeout.
- **3A Permission broker (`complete`)** — O/S/D: levels, proposals, atomic exact grants, receipts,
  durable store. P: Phase 1/host identity. X: OS effects. Q: threat -> contracts/store -> trusted UI
  seam -> replay/race. T: deny/expire/revoke/duplicate/restart/corrupt/audit/cross-host. SP: model/
  chat cannot approve; redact receipts. M: schema/security/report. A/E: one exact valid grant required.
  N: 1. R: `gpt-6-astra` `ultra`, core authority boundary.
- **3B Actions/recovery (`complete`)** — O/S/D: fixed identities/arrays/canonical roots, idempotency,
  postcondition, compensation. P: 3A/disposable fixtures. X: shell/admin. Q: read-only -> reversible
  -> app/media -> optional print. T: missing/collision/partial/cancel/retry/restart/mismatch. SP:
  execution revalidation/result caps. M: action/recovery matrix. A/E: complete control record/tool.
  N: 1. R: `gpt-6-astra` `ultra`, real effects and rollback.
- **3C Adversarial/live closeout (`implemented-closeout-pending`)** — O/S: attack chain and named
  minimal effects. P: 3A-B/live authority. D: corpus/benchmark/receipts. X: broader effects. Q:
  audit -> adversarial -> restart/rollback -> exact live -> gates. T: aggregate attacks/false intents.
  SP: fixed args/expiring grants. M: security/hardware/overview/report. A/E: current adversarial/live
  pass. N: 1. R: `gpt-6-astra` `max`, cross-OS security.
- **4A Schema/lifecycle/provenance (`complete`)** — O/S/D: memory states, sources, conflicts,
  retention, ownership, migration/APIs. P: Phase 1. X: retrieval/auto-confirm. Q: threat/data model
  -> migration -> lifecycle. T: transitions, duplicate/conflict/expiry/rollback/corrupt/concurrent.
  SP: candidate quarantine, least data, host predicates. M: schema/security/report. A/E: durable,
  isolated, reversible lifecycle. N: 1. R: `gpt-6-astra` `xhigh`, durable privacy schema.
- **4B Retrieval/interfaces (`complete`)** — O/S/D: FTS5 scoring/reasons, inspect/promote/correct/
  forget/export, bounded projection. P: 4A. X: unjustified vectors. Q: golden set -> retrieval ->
  explanation -> UI -> abuse. T: relevance/stale/conflict/poison/output/concurrency. SP: retrieved
  text untrusted; sensitivity gates cloud. M: architecture/user controls/report. A/E: explained,
  privacy-safe recall. N: 1. R: `gpt-6-astra` `xhigh`, retrieval/privacy interaction.
- **4C Evaluation/deletion (`complete`)** — O/S/D: quality/performance, transitive delete, export,
  backup/restore. P: 4A-B. X: vector dependency. Q: benchmark -> adversarial -> deletion -> restore
  -> gates. T: precision/recall/cold/warm/scale/derived cleanup. SP: exact export, content-free
  tombstones. M: overview/roadmap/report. A/E: all fixed gates. N: 1. R: `gpt-5.6-sol` `high`,
  bounded closeout.
- **5A Acquisition/parsing (`complete`)** — O/S/D: URL/type/size/time contracts, IP/SNI pinning,
  redirects, subprocess parsers. P: Phase 4. X: private addresses/scripts/active content. Q: threat
  -> fixtures -> network policy -> parsers -> hostile corpus. T: reserved/mapped IP, rebind,
  redirect, bomb, malformed, crash/hang. SP: data only; pre-parse limits; no local pivot. M: source
  policy/report. A/E: safe provenance and bounded hostile failure. N: 1. R: `gpt-6-astra`
  `xhigh`, SSRF/parser boundary.
- **5B Evidence/synthesis (`complete`)** — O/S/D: claim links, conflict, uncertainty, cited answer/
  fallback. P: 5A. X: uncited material claim/source-driven tool. Q: schema -> synthesis -> injection/
  citation. T: missing/conflicting/stale/unsupported/malicious/malformed/quote. SP: source cannot
  alter policy; inference labeled; sensitive local. M: workflow/citations/report. A/E: fixed
  coverage/entailment/diversity/freshness. N: 1. R: `gpt-6-astra` `high`, untrusted synthesis.
- **5C Ledger/closeout (`complete`)** — O/S/D: exact approval, ledger/search/supersede/queue/
  revalidate/export/delete, CLI/web/benchmark. P: 5A-B/Phase 4. X: automatic trust. Q: ledger -> UI
  -> lifecycle -> 30 samples. T: isolate/duplicate/concurrent/restart/conflict/export/delete/replay.
  SP: approved reports only; content-free operations. M: overview/roadmap/report. A/E: fixed quality/
  security/release gates. N: 1. R: `gpt-5.6-sol` `high`, durable closeout.
- **6A DAG/validator/store (`complete`)** — O/S/D: proposal, dependencies, budgets, states/events/
  versions/owner/handlers, migration. P: Phases 3-5. X: execution/planner authority. Q: threat/state
  -> contracts -> store -> property/restart. T: cycle/missing/budget/stale/duplicate/concurrent/
  corrupt. SP: host resolves authority/cost and scope. M: schema/security/report. A/E: invalid or
  authority-expanding graph cannot persist. N: 1. R: `gpt-6-astra` `xhigh`, durable invariants.
- **6B Scheduler/recovery (`complete`)** — O/S/D: bounded execution/retry/checkpoint/grant/cancel/
  compensate/reconcile. P: 6A/Phase 3. X: background/unbounded effect parallelism. Q: read-only ->
  budgets -> effects -> recovery -> safe parallel. T: crash each state/partial/timeout/retry/cancel/
  pause/orphan/deny/exhaust. SP: grant recheck/node/args. M: recovery/security/report. A/E: zero
  unauthorized/duplicate effect; exact stops. N: 1. R: `gpt-6-astra` `ultra`, bounded autonomy.
- **6C Interfaces/benchmark (`complete`)** — O/S/D: preview/run/control/status/export/delete and
  evidence. P: 6A-B. X: daemon. Q: UI -> golden/recovery/scale -> lifecycle -> gates. T: terminal
  states/version/restart/tombstone. SP: preview is not approval; UI cannot alter authority/budget.
  M: guide/overview/roadmap/report. A/E: fixed 100-run/100-scenario benchmark. N: 1. R:
  `gpt-5.6-sol` `high`, bounded evidence.

### Future subphases

- **7A Capture/privacy/contracts (`not-started`)** — O/S/D: purpose/region/fps/retention capture
  ports/fakes/adapters/indicator/kill. P: Phase 3/live authority/current library license review. X:
  recognition/retention. Q: threat -> contracts -> fake/OS -> privacy. T: deny/switch/loss/stale/
  cap/timeout/restart/off. SP: explicit active state, least frames, local. M: capture policy/setup/
  report. A/E: no capture outside state/limits. N: 1. R: `gpt-6-astra` `xhigh`, media boundary.
- **7B Temporal gestures/calibration (`not-started`)** — O/S/D: local landmarks, confidence/
  debounce/cooldown, fist/palm/pinch/finger-roll, calibration. P: 7A/licensed candidate. X: tool
  execution. Q: diverse dataset -> candidate benchmark -> state machine -> soak. T: lighting,
  distance, occlusion, skin tones, handedness, no-hand, drop/conflict/contention. SP: uncertainty no
  intent; ephemeral features. M: detector/dataset/hardware/report. A/E: fixed precision/recall/
  latency/false/resource targets. N: 1. R: `gpt-5.6-sol` `high`, bounded CV evaluation.
- **7C Intent mapping/closeout (`not-started`)** — O/S/D: `gesture -> typed intent -> Phase 3`,
  rate/cancel/audit/live proof. P: 7A-B/exact grants/live authority. X: gesture approval/risk raise.
  Q: mapping -> broker fakes -> adversarial -> live -> gates. T: stale/conflict/storm/replay/expiry/
  false/cancel. SP: execution recheck. M: hands-free/controlled/overview/report. A/E: fixed metrics
  without escalation/storm; 30-minute soak. N: 1. R: `gpt-6-astra` `max`, perception meets effects.
- **8A API/identity/enrollment (`complete`)** — O/S/D: versioned API/events and device key/
  session secure storage/rotate/revoke/replay/audit. P: Phase 1/3 and current crypto/TLS docs. X:
  exposure. Q: threat -> contracts -> lifecycle -> middleware -> abuse. T: token type/audience/
  device, expiry/revoke/rotate/nonce/skew/restart. SP: cover method/authority/path/query/body/date/
  nonce where signed; no secrets in model/log. M: ADR/API/recovery/report. A/E: strict request/
  subscription scope. N: 1. R: `gpt-6-astra` `ultra`, remote identity.
- **8B Trusted approval/web hardening (`not-started`)** — O/S/D: device/session/action decisions,
  atomic winner, effect preview, CSRF/CORS/CSP/cookie/body/rate controls. P: 8A/Phase 3. X: local-
  required bypass. Q: matrix -> execution recheck -> API/UI -> abuse. T: stale/race/cross-device/
  origin/CSRF/XSS/oversize/confused deputy/audit. SP: required audience; empty scope denies; owner
  data withheld. M: security/UX/API/report. A/E: no grant expansion/session leak. N: 1. R:
  `gpt-6-astra` `ultra`, authorization plus web surface.
- **8C PWA/stream/reconnect (`not-started`)** — O/S/D: responsive client, offline shell, desired
  subscriptions/cursors/logout clearing/private notifications. P: 8A-B. X: offline effects/content
  cache. Q: state -> typed client -> auth -> reconnect -> offline/accessibility. T: flap/duplicate/
  order/expiry/zombie/logout/cache/tabs. SP: minimal cache, clear secrets/subscriptions. M: install/
  troubleshooting/report. A/E: resume without duplicate/leak. N: 1. R: `gpt-5.6-terra` `high`,
  known UI after Astra contracts.
- **8D Private deployment/closeout (`not-started`)** — O/S/D: approved TLS/private topology,
  phone, runbook/backup/rollback/live proof. P: 8A-C/exposure authority. X: public/multi-replica.
  Q: bind/firewall/TLS -> deploy -> enroll/loss/revoke -> scan/rollback -> gates. T: lost phone,
  partition/restart/revoked stream/certificate/offline. SP: app/network deny; one replica while
  replay/session/rate state is local. M: setup/security/deployment/overview/report. A/E: real phone,
  immediate revoke, no listener, laptop offline. N: 1. R: `gpt-6-astra` `max`, cross-system deploy.
- **9A Topology/protocol/identity (`not-started`)** — O/S/D: topology roles, one-owner map,
  authenticated version/capability protocol. P: Phase 8/measurements. X: migration/scale. Q: measure
  -> threat/ADR -> protocol fakes -> downgrade/replay. T: stale/skew/revoke/mismatch/loss/fallback.
  SP: least privilege/audience/owner. M: architecture/security/topology/report. A/E: one owner and
  negotiated capability. N: 1. R: `gpt-6-astra` `ultra`, distributed trust.
- **9B Migration/backup/reconciliation (`not-started`)** — O/S/D: reversible transfer/cutover,
  manifests/checksums/backup/restore. P: 9A/capacity/keys. X: cutover before rehearsal/unjustified
  database. Q: classify -> backup/restore -> shadow/check -> cutover/rollback. T: interruption,
  duplicate/order/stale writer/disk/corrupt/schema/partition. SP: encryption/key separation/no split
  brain. M: migration/RPO/RTO/report. A/E: verified invariants and real rollback. N: 1. R:
  `gpt-6-astra` `ultra`, data-loss risk.
- **9C Deployment/resilience (`not-started`)** — O/S/D: pinned deployment/update/health/telemetry/
  offline/runbooks. P: 9A-B/deploy authority. X: floating/privileged containers. Q: staging -> chaos
  -> upgrade/rollback -> gates. T: crash/TLS/partition/overload/disk/bad release/offline. SP:
  non-root/read-only/drop capabilities/process/network limits; shared replay/session/rate before
  replicas. M: operations/security/overview/report. A/E: local/split parity and rollback. N: 1.
  R: `gpt-6-astra` `max`, deployment resilience.
- **10A Feasibility/license/contract (`not-started`)** — O/S/D: dated vendor access/capability/
  license matrix, generic audio/display/camera/input/notification/health contract/fakes, ADR. P:
  Phases 7-8, official sources/device. X: marketing/inaccessible claims. Q: sources -> inventory ->
  threat/license -> contract. T: missing/version/deny/simulator/remove. SP: capability grants
  nothing; classify health/media. M: ADR/matrix/report. A/E: feasible legal slice or external
  blocker. N: 1. R: `gpt-5.6-sol` `high`, evidence-heavy research.
- **10B Adapter/phone bridge (`not-started`)** — O/S/D: chosen adapter behind generic contract,
  enrollment/revoke/resource limits/CI fake. P: 10A/Phase 8/SDK. X: vendor core/unapproved
  unofficial path. Q: contract -> enrollment -> bridge -> limits -> removal. T: disconnect/revoke/
  version/battery/network/phone/duplicate. SP: scoped grants, secure storage, visible capture,
  minimal retention. M: setup/security/recovery/report. A/E: fake and bounded device fixture pass.
  N: 1. R: `gpt-6-astra` `xhigh`, cross-device identity/streaming.
- **10C Real-device closeout (`not-started`)** — O/S/D: functional/privacy/resource sanitized
  proof. P: 10A-B/live authority. X: personal health/media retention or unapproved cloud. Q: freeze
  versions -> live/loss/revoke/indicator -> battery/latency -> remove -> gates. T: aggregate real
  matrix. SP: indicator/bystander/delete/disconnect. M: hardware/privacy/overview/report. A/E: one
  real generic flow and adapter-removal pass. N: 1. R: `gpt-6-astra` `max`, live media/vendor risk.
- **11A Trigger/proactivity policy (`not-started`)** — O/S/D: user schedules/triggers,
  suggestions, timezone/expiry/quiet/rate/attention, deterministic policy/preview. P: Phases 4/6.
  X: runner/model-created grant. Q: threat/usefulness -> contracts/store -> controls -> clock abuse.
  T: DST/skew/duplicate/noise/stale/expiry/disable/delete/restart. SP: suggestion not authority; host
  budgets. M: policy/config/report. A/E: trigger cannot execute/outlive scope. N: 1. R:
  `gpt-6-astra` `ultra`, autonomy boundary.
- **11B Durable runner/notifications (`not-started`)** — O/S/D: bounded evaluation/task handoff/
  dedup/notify/snooze/cancel/recovery/checkpoints. P: 11A/Phase 6/8 when remote. X: hidden work or
  sensitive preview. Q: clock fake -> candidate -> task boundary -> notify -> recovery. T: restart/
  duplicate/offline/failure/cancel/budget. SP: audience classification/fresh grants/private preview.
  M: operations/controls/report. A/E: single candidate ownership/no duplicate effect. N: 1. R:
  `gpt-6-astra` `ultra`, time-driven effects.
- **11C Multi-device/adapters (`not-started`)** — O/S/D: single ownership/handoff/dedup/visible
  state and approved scoped adapters. P: 11A-B/relevant 7-10. X: broad discovery/new capability.
  Q: ownership fakes -> handoff -> one adapter -> partition/revoke. T: simultaneous/stale owner,
  partition/heal/revoke/conflict/removal. SP: scope intersection, required audience, local kill.
  M: architecture/device/recovery/report. A/E: no split ownership/effect/leak. N: 1. R:
  `gpt-6-astra` `ultra`, system-wide coordination.
- **11D Long-duration closeout (`not-started`)** — O/S/D: usefulness/annoyance/correctness/privacy/
  cost/power/recovery/removal evidence. P: 11A-C, frozen thresholds, authorized run. X: post-result
  weakening. Q: freeze -> simulation -> bounded soak -> incidents/kill/removal -> gates. T:
  aggregate phase and core regression. SP: minimal telemetry; explain why/data/tools/audience;
  delete evaluation state. M: evaluation/operations/overview/report. A/E: fixed thresholds and
  removal leaves on-demand core intact. N: 1. R: `gpt-6-astra` `max`, residual-risk judgment.

## 19. Cross-phase hands-free control track

Hands-free control is not a permission bypass or isolated phase:

- Phase 2 detects local double clap and other acoustic events.
- Phase 7 recognizes calibrated temporal hand gestures.
- Phase 3 is the only component allowed to map those typed intents to Windows actions.
- Phase 11 may later add context-aware suggestions, but never hidden execution.

Minimum hands-free release requires completed Phase 3 broker plus the relevant Phase 2/7 detector,
false-trigger datasets, visible indicators, audit, cooldowns, rate limits, universal cancel, and a
verified kill switch. See `docs/HANDS_FREE_CONTROL.md`.

## 20. Progress and completion reports

Use `docs/phase-reports/TEMPLATE.md`. Keep checkboxes and evidence current after each milestone.
Reports must never contain credentials, private prompts, recordings, screenshots, personal paths,
or unredacted provider responses.

A completion report must contain:

- final status and date;
- implemented scope and explicitly deferred scope;
- architecture/security decisions;
- migrations/configuration/dependencies;
- automated test commands/results and coverage;
- live hardware/provider/device evidence;
- benchmark sample count, p50/p95, errors, versions, and settings;
- known limitations and recovery/rollback;
- quality, vulnerability, secret, and Git evidence;
- exact next recommended phase.
