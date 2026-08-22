# Codex Sol JARVIS Phase Playbook

Updated: 2026-08-22  
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
6. Execute without repeatedly asking about ordinary reversible implementation choices.
7. Stop for user input only at the authority boundaries listed below.
8. Finish only after every applicable exit criterion has evidence.

The phrase `finish it` requires persistence, but cannot grant new authority or waive safety.

## 2. Sol model and thinking levels

Recommended model: Codex Sol. Reasoning effort is chosen in the Codex UI or caller configuration;
instructions cannot switch it automatically.

| Phase | Recommended Sol thinking | Reason |
| --- | --- | --- |
| 0 | Medium | Repository, history, reproducibility, and secret checks are bounded but require care |
| 1 | High | Cross-cutting runtime, providers, privacy, persistence, tools, and acceptance evidence |
| 2 | Extra high | Real-time audio, cancellation, device behavior, latency, noise, and GPU contention |
| 3 | Ultra | Computer control, permissions, approval integrity, rollback, and irreversible-action risk |
| 4 | Extra high | Stateful memory, provenance, deletion, conflicts, retrieval quality, and privacy |
| 5 | High | Retrieval, citations, hostile sources, freshness, and measurable research quality |
| 6 | Ultra | Bounded autonomy, durable execution, budgets, recovery, and approval-aware planning |
| 7 | Extra high | Real-time vision, gesture temporal logic, calibration, privacy, and false activations |
| 8 | Ultra | Remote access, authentication, device identity, revocation, TLS, and attack surface |
| 9 | Ultra | Distributed state, migration, backup/restore, identity, network loss, and rollback |
| 10 | Extra high | Real-device capability limits, media privacy, phone bridging, and vendor churn |
| 11 | Ultra | Proactivity, schedules, multi-device autonomy, privacy, cost, and host-control guarantees |

Low thinking is only for mechanical subtasks. Medium is acceptable for isolated known-pattern
subtasks. Never reduce security-boundary design below the listed phase level.

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

## 6. Phase 0 — Repository baseline and reset verification

Recommended thinking: **Medium**  
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

Recommended thinking: **High**  
Baseline status: **implemented; formal closeout pending**

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

Recommended thinking: **Extra high**  
Baseline status: **not started**  
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

Recommended thinking: **Ultra**  
Baseline status: **foundations only**  
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

Recommended thinking: **Extra high**  
Baseline status: **foundations only**  
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

Recommended thinking: **High**  
Baseline status: **not started**  
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

Recommended thinking: **Ultra**  
Baseline status: **foundations only**  
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

Recommended thinking: **Extra high**  
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

Recommended thinking: **Ultra**  
Baseline status: **foundations only (loopback web UI exists)**  
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

Recommended thinking: **Ultra**  
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

Recommended thinking: **Extra high**  
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

Recommended thinking: **Ultra**  
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

## 18. Cross-phase hands-free control track

Hands-free control is not a permission bypass or isolated phase:

- Phase 2 detects local double clap and other acoustic events.
- Phase 7 recognizes calibrated temporal hand gestures.
- Phase 3 is the only component allowed to map those typed intents to Windows actions.
- Phase 11 may later add context-aware suggestions, but never hidden execution.

Minimum hands-free release requires completed Phase 3 broker plus the relevant Phase 2/7 detector,
false-trigger datasets, visible indicators, audit, cooldowns, rate limits, universal cancel, and a
verified kill switch. See `docs/HANDS_FREE_CONTROL.md`.

## 19. Progress and completion reports

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
