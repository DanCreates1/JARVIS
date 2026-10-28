# JARVIS Master Roadmap

Canonical delivery plan, **2026-10-26**. Owner selected **laptop-first Core** and **PWA-first client**
before this sequence was defined. [Core decision](JARVIS_ARCHITECTURE.md#current-core-decision--2026-10-26)
owns architecture; [Phase Execution](PHASE_EXECUTION.md) owns commands/gates. This document alone
owns active phase IDs, scope, dependencies, status and next action. [Overview](PHASE_OVERVIEW.md)
is a short navigation view. [Previous master](LEGACY_MASTER_ROADMAP.md) and old reports are history.

## Product and architecture boundary

One owner uses JARVIS through the existing responsive PWA on laptop/iPhone. One modular Python
Core on the Windows laptop owns conversations, memory, model routing, identity, permissions, tasks
and audit. SQLite/FTS5 stays beside Core; model and integration adapters remain replaceable.
Laptop availability is required. No separate server or native client is required for this release.
Private/uncertain content stays local; optional public cloud remains configured, privacy-gated and
hard-capped at **$0**. Model output never supplies authority. Existing application authentication,
exact origin/scopes, approved private HTTPS route, audit and consequential-action controls remain.

The completed text prototype stays reproducible with `prototype-text` and installed `qwen3:1.7b`.
Its usefulness is bounded: **8/10**, with polite-tone/checklist-format failures. Future product
features extend explicit capability configuration and reuse Core, rather than enabling dormant
integrations globally or creating another runtime. This plan itself enables no feature or scope.

## Management rules

- Use **Phase 1, Phase 2, ...** only. Milestones/checklists live inside a phase report; no default
  lettered or decimal subphases. Never create a subphase just to cross a chat/session boundary.
- `Initiate Phase N` always means this current namespace. Use `Legacy Phase N`, `Legacy A–M`,
  `Historical PROTO-X` or the exact old report name for historical evidence.
- Reports live in `docs/phase-reports/current/PHASE_N_PROGRESS.md` or `PHASE_N_COMPLETION.md`.
  Old filenames/migrations/tests remain stable; renumbering never rewrites measured evidence.
- This table is the status ledger. Change it and the overview when evidence changes. A phase
  can contain substantial old code while its current product acceptance is still `not-started`.
- Delivery follows numeric priority, subject only to actual listed dependencies. A blocked
  integration is not a prerequisite for unrelated work. No later phase starts without a request
  covering it; a planning row or handoff grants no execution authority.
- Full release gates, privacy/auth/approval controls, the native publication hold and owner-skipped
  phone policy apply throughout. No planning row grants credential, health, enrollment, device,
  deployment, signing, spend or external-message authority.
- Revalidate dated provider/dependency/device facts from official primary sources when their
  phase executes. Freeze additional quantitative acceptance before evaluation, not after results.

## Phase ledger

Rows 1–19 form the primary laptop/PWA delivery plan. Rows 20–24 retain the wider vision as
**deferred** options; they are managed backlog, not prerequisites or an automatic execution queue.

| Phase | Outcome | Status | Actual dependency | Existing implementation / principal remaining gate |
| --- | --- | --- | --- | --- |
| [1](#phase-1--direction-and-audit) | Direction and audit | complete | None | Historical PROTO-0 audit/design |
| [2](#phase-2--secure-reproducible-baseline) | Secure reproducible baseline | complete | 1 | Historical PROTO-1.1; continuous audits remain |
| [3](#phase-3--runnable-local-text-assistant) | Runnable local text assistant | complete | 2 | Historical PROTO-1.2 |
| [4](#phase-4--integrated-text-acceptance) | Integrated text acceptance | complete | 3 | Historical PROTO-2.1; bounded corpus 8/10 |
| [5](#phase-5--prototype-recovery-and-receipt) | Prototype recovery and receipt | complete | 4 | Historical PROTO-2.2, published `466a409` |
| [6](#phase-6--architecture-and-managed-roadmap) | Architecture and managed roadmap | complete | 5 | Owner choices, flat ledger, command/report migration and gates evidenced |
| [7](#phase-7--text-quality-and-daily-use-polish) | Text quality and daily-use polish | complete | 6 | Explicit daily text; 10/10 original, 37/40 + 37/40 + 36/40 expanded; all safety and release gates |
| [8](#phase-8--private-garmin-workspace) | Private Garmin workspace | complete | 7 | Explicit local Garmin workspace, full synthetic matrix/current Core evidence and release gates; production health access remains separate |
| [9](#phase-9--files-and-attachments) | Files and attachments | not-started | 7 | Legacy G/F14/F15 foundations; bounded product acceptance |
| [10](#phase-10--inspectable-memory-and-project-context) | Inspectable memory and project context | not-started | 7 | Legacy memory/F continuity; safe owner-facing lifecycle |
| [11](#phase-11--grounded-public-research) | Grounded public research | not-started | 7 | Legacy research/freshness; live source access and cited acceptance |
| [12](#phase-12--foreground-voice) | Foreground voice | not-started | 7 | Legacy voice/F13; chosen local speech/reply experience |
| [13](#phase-13--controlled-windows-actions) | Controlled Windows actions | not-started | 7 | Existing broker/tools; current exact live-effect acceptance |
| [14](#phase-14--bounded-tasks-and-project-workflows) | Bounded tasks and project workflows | not-started | 7; 13 for action-bearing flows | Existing DAG/scheduler/task views; usable safe workflow/control |
| [15](#phase-15--email) | Email | not-started | 7 | Local read/prepare exists; live provider/auth gate remains |
| [16](#phase-16--calendar-and-reminders) | Calendar and reminders | not-started | 7 | Calendar adapter and lifecycle; write authority separate |
| [17](#phase-17--background-scheduling-and-proactivity) | Background scheduling and proactivity | not-started | 14 | Existing inert/foreground policy; explicit bounded worker and opt-in |
| [18](#phase-18--daily-briefing) | Daily briefing | not-started | 10, 15, 16, 17; 8 only for Garmin content | Compose approved sources with honest freshness/omissions |
| [19](#phase-19--laptoppwa-release-and-operations) | Laptop/PWA release and operations | not-started | 7–18 | Integrated release, recovery, maintenance and honest acceptance receipt |
| [20](#phase-20--vision-and-gestures) | Vision and gestures | deferred | 13 + reviewed capture boundary | Existing legacy vision foundation; demonstrated owner need |
| [21](#phase-21--native-mobile) | Native mobile | deferred | Required OS capability + passing native gates | Existing M1/M2 foundation; dependency publication hold remains |
| [22](#phase-22--dedicated-server) | Dedicated server | deferred | New availability requirement + approved target | Legacy topology/migration foundation; no server selected or deployed |
| [23](#phase-23--wearables-and-additional-devices) | Wearables and additional devices | deferred | Supported vendor path + device/scopes authority | Generic legacy wearable boundary; adapter/device acceptance absent |
| [24](#phase-24--restricted-maintenance-assistance) | Restricted maintenance assistance | deferred | 14, 17, 19 + explicit narrow use case | Proposal-only isolated assistance; no self-authorized production changes |

**Progress basis:** **8/19 primary phase receipts closed (~42%)**. This is an unweighted management
count, not percentage of code written, elapsed effort or mobile MVP acceptance.
Existing foundations reduce future work but earn no new phase closure without current evidence.
Prototype acceptance remains **100% = 10/10 groups** under its original scope. Full mobile MVP,
physical acceptance and production readiness remain unestablished. Optional rows receive no credit.

## Phase definitions

Every future phase inherits [execution/release controls](PHASE_EXECUTION.md), the architecture
decision and root authority policies. References below are required reading when executing that
phase; old phase numbers in those documents are explicitly **legacy**. Recommended minimum Codex
diligence is `gpt-6-astra` / `xhigh`; authorization, remote identity, external effects, scheduling
or deployment decisions use `ultra`. These are recommendations, never claims to switch the UI model.

### Phase 1 — Direction and audit

Mapped **complete**, 2026-10-22: Historical PROTO-0.1/0.2 become one flat phase.
Scope: source/status audit, architecture alternatives, prototype bounds and acceptance freeze.
Evidence: [historical plan](PROTOTYPE_PLAN.md), [scope triage](PROTOTYPE_SCOPE_TRIAGE.md),
[mapped receipt](phase-reports/current/PHASE_1_COMPLETION.md). No retroactive new measurement.

### Phase 2 — Secure reproducible baseline

Mapped **complete**, 2026-10-22: Historical PROTO-1.1. Reproducible locks, minimal reviewed security
repairs, quality/audits and isolated safe publication. Continuous future audits remain mandatory;
historical pass is not perpetual dependency safety. [Original evidence](PROTO_1_1_EVIDENCE.md),
[mapped receipt](phase-reports/current/PHASE_2_COMPLETION.md).

### Phase 3 — Runnable local text assistant

Mapped **complete**, 2026-10-22: Historical PROTO-1.2. One launcher/profile, lean PWA Chat/Settings,
local clock/text/context smoke, frozen corpus and safe recovery; no optional-integration activation.
[Runbook](PROTOTYPE_TEXT_RUNBOOK.md), [original evidence](PROTO_1_2_EVIDENCE.md),
[mapped receipt](phase-reports/current/PHASE_3_COMPLETION.md).

### Phase 4 — Integrated text acceptance

Mapped **complete**, 2026-10-25: Historical PROTO-2.1. Real PWA/auth/Core/SQLite/Ollama acceptance,
retry/cancel/restart/privacy and fixed usefulness/timing targets. Corpus is 8/10, including mandatory
A1/U1; R1/C1 failures remain visible. No legacy NVIDIA latency closure.
[Original evidence](PROTO_2_1_EVIDENCE.md), [mapped receipt](phase-reports/current/PHASE_4_COMPLETION.md).

### Phase 5 — Prototype recovery and receipt

Mapped **complete**, 2026-10-25: Historical PROTO-2.2. Exact startup, disposable restart, all ten
prototype acceptance groups, safe publication and independent CI. Published `466a409`; physical/
mobile MVP/production acceptance not established. [Original receipt](PROTO_2_2_EVIDENCE.md),
[mapped receipt](phase-reports/current/PHASE_5_COMPLETION.md).

### Phase 6 — Architecture and managed roadmap

Scope: record owner-selected laptop/PWA architecture before planning; consolidate all known tracks
into this flat ledger; update commands, report namespace, crosswalk and entry links. Preserve old
reports, thresholds, held changes and historical roadmap. Exit: consistent links/IDs/statuses,
documented authorities, applicable gates and reviewed publication. No application feature starts.
Status: **complete**, 2026-10-26. [Completion evidence](phase-reports/current/PHASE_6_COMPLETION.md).

### Phase 7 — Text quality and daily-use polish

Outcome: dependable simple text tasks and a clear product capability contract. Reuse accepted
runtime/PWA, routing fixes, streaming/history/search/library, token reduction and immutable receipts.
Fix R1 polite tone and C1 checklist format through generic behavior; do not rewrite expected answers
or repair outputs after scoring. Freeze 40 additional public/synthetic cases before tuning; require
at least 36/40 plus every designated safety case, and **10/10 original cases** with A1/U1 mandatory.
Retain original prototype timing targets, expose unavailable evidence/model errors and show existing
recovery controls clearly. Freeze safety-case membership and scoring in the progress report first.
Exit: repeated real acceptance of selected configuration, preserved privacy/$0/auth/recovery and
complete gates. Keep `prototype-text` baseline reproducible; explicit capability decisions precede
later feature activation. No automatic larger-model download, provider replacement or integration.
Read: [corpus](PROTOTYPE_CORPUS.md), [Phase 4 source evidence](PROTO_2_1_EVIDENCE.md),
[Phase 5 source receipt](PROTO_2_2_EVIDENCE.md), [text runbook](PROTOTYPE_TEXT_RUNBOOK.md).

Status: **complete**, 2026-10-26. [Completion evidence](phase-reports/current/PHASE_7_COMPLETION.md),
[daily capability contract](DAILY_TEXT.md), [expanded frozen corpus](PHASE_7_CORPUS.json).
Three final runs meet unchanged thresholds; sorting/conversion/explanation failures stay visible.
Original prototype prompt/launcher and historical 8/10 evidence remain intact. No later feature is enabled.

### Phase 8 — Private Garmin workspace

Status: **complete**, 2026-10-27. [Completion evidence](phase-reports/current/PHASE_8_COMPLETION.md),
[capability/startup/recovery contract](PRIVATE_GARMIN.md). Explicit `private-garmin` extends daily
local text without enabling other integrations. Current protected Core reads and synthetic scoped
PWA lifecycle pass; no production scope/enrollment or physical-phone acceptance is inferred.

Outcome: useful read-only health/activity view through Core. Reuse protected saved session, isolated
Python bridge and existing normalized PWA view; no reimport/new login as routine startup. Verify
adapter compatibility/current audit, last-sync/freshness/unavailable states, bounded reads, normal
renewal, disconnect and privacy-safe diagnostics. Keep health out of cloud/model prompts and browser
persistence. Exit: synthetic full matrix and bounded live Core evidence under existing saved-session
authority; production health scope/enrollment remains separately controlled. No writes, new scopes
or physical-phone request. Read [Garmin contract](PWA_GARMIN.md), [connector](GARMIN_CONNECTOR.md),
[prior progress](phase-reports/PWA_MVP3_PROGRESS.md). Phone rows stay skipped/unverified.

### Phase 9 — Files and attachments

Outcome: reliable supplied-content workflows. Reuse G processing and F14/F15 upload, provenance,
preview, search and same-conversation reuse. Test text/PDF/image capability behavior with bounded
synthetic files, parser isolation, quota/expiry/delete, cancel/restart and stale-response rejection.
Exit: actual PWA/Core workflow with explicit capability flags, grounded source references and zero
private disclosure or automatic memory promotion. Image understanding requires a qualified installed
local adapter; an unsupported capability must say unavailable. No arbitrary filesystem access or
cloud upload. Read [attachments](ATTACHMENTS.md), [F14](PWA_F14_WORKFLOWS.md), [F15](PWA_F15_WORKSPACE.md).

### Phase 10 — Inspectable memory and project context

Outcome: owner can inspect, approve, correct and forget useful context. Reuse legacy memory states,
FTS5, provenance, conflict/deletion and private coding continuity. Add only needed PWA projections
through explicit current authority; no client-created trust. Exit: source-explained retrieval,
candidate quarantine, cross-owner denial, correction/retention and transitive deletion after restart;
bounded context budgets and a frozen retrieval set. No automatic trust, unmeasured vector service
or unreviewed repository execution. Read [memory evidence](phase-reports/PHASE_4_COMPLETION.md),
[continuity](TOKEN_CONTINUITY.md), [memory ownership](architecture.md#memory-boundary).

### Phase 11 — Grounded public research

Outcome: useful current answers with verified sources or explicit unavailable evidence. Reuse
freshness classification, search/fetch/parser/citation workflow and existing general-search port.
Resolve actual live source availability; retain Wikimedia's historical `authentication_required`
blocker until the same endpoint is evidenced working. Exit: real public-source retrieval plus frozen
citation/entailment/freshness/conflict and SSRF/injection/failure tests. Store research only through
existing exact approval. Optional cloud requires current terms/free-capacity verification and the
same full-context privacy gate; no login/paywall bypass or private query disclosure.
Read [research evidence](phase-reports/PHASE_5_COMPLETION.md), [legacy C evidence](phase-reports/PHASE_C_COMPLETION.md),
[freshness evidence](phase-reports/PHASE_B_COMPLETION.md), [legacy latency debt](#retained-gates-and-authority-register).

### Phase 12 — Foreground voice

Outcome: deliberate push-to-talk with cancellation, text fallback and clearly controlled replies.
Reuse local STT/VAD/TTS and F13 canonical PCM/capture lifecycle; freeze selected foreground workflow
and quality/latency budgets before measurement. Exit: synthetic audio/transport/cancel/offline/
device-loss tests, appropriate authorized Windows evidence and safe typed fallbacks. Raw audio is
ephemeral; model/cloud speech is not enabled implicitly. No always-listening, wake/clap release,
background phone capture or manual phone checks. Read [F13](PWA_F13_PUSH_TO_TALK.md),
[voice evidence](phase-reports/PHASE_2_COMPLETION.md), [hands-free boundaries](HANDS_FREE_CONTROL.md).

### Phase 13 — Controlled Windows actions

Outcome: a small useful set of typed Windows actions with trustworthy previews and receipts.
Reuse permission Levels 0–4, expiring exact grants, broker, allowlists, postconditions and rollback.
Exit: current replay/injection/race/cancel/restart matrix and exact separately-authorized live effects;
no blind replay or model-generated shell. Approval surfaces must satisfy existing trusted-local
requirements; remote action control is not inherited from chat. Destructive effects, printing,
shutdown and security changes remain consequential boundaries. Read [security](SECURITY_MODEL.md),
[legacy action evidence](phase-reports/PHASE_3_COMPLETION.md), [hands-free](HANDS_FREE_CONTROL.md).

### Phase 14 — Bounded tasks and project workflows

Outcome: plan, inspect and run bounded useful tasks, monitor status and safely pause/cancel/resume.
Reuse existing immutable DAG validator, durable scheduler/checkpoints, CLI and F14/F15 task views.
Read-only workflows can use existing verified broker contracts without waiting for action-product
closure; action-bearing acceptance depends on Phase 13. Exit: frozen representative task set,
explicit budgets, failure/restart reconciliation and zero duplicated/unauthorized effects. Remote
task cancellation needs a real scoped mutation adapter; read scope and guessed conversation
relationships never grant control. No recursive swarm or second scheduler.
Read [task evidence](phase-reports/PHASE_6_COMPLETION.md), [F14](PWA_F14_WORKFLOWS.md), [F15](PWA_F15_WORKSPACE.md).

### Phase 15 — Email

Outcome: approved-provider read/thread summaries and preparation of drafts with provenance.
Reuse local IA export/read/prepare and provider-neutral contracts; select provider and review current
official auth/API/terms before implementing live adapter. Freeze allowed read data, retention and
revocation behavior. Exit: synthetic hostile MIME/provider lifecycle and bounded authorized live
read/prepare proof; unsent drafts remain visibly unsent. Credentials/new login/scopes/private reads
need applicable existing or new authority. External draft/write/send is a separate exact approved
operation, not a model side effect or prerequisite to read-only acceptance. No unattended polling.
Read [email](EMAIL.md), [legacy I progress](phase-reports/PHASE_I_PROGRESS.md).

### Phase 16 — Calendar and reminders

Outcome: inspect events, detect conflicts, prepare changes and manage owner-authored reminders.
Add a provider-neutral adapter reusing identity/secret/permission boundaries; select provider and
current official contracts first. Exit: timezone/DST/recurrence/conflict/cancel/restart tests,
explicit freshness and authorized read evidence. Any external event/reminder creation, deletion,
invitation or update requires exact applicable approval and provider scope; suggestions do not
write. No third-party messages or background worker activation by planning.
Read [historical expansion J](AGENTIC_ASSISTANT_EXPANSION.md), [security](SECURITY_MODEL.md).

### Phase 17 — Background scheduling and proactivity

Outcome: explicit opt-in bounded background evaluation and useful, controllable suggestions.
Reuse foreground trigger/inbox policy, durable task scheduler and one-owner leases. Define process
lifecycle, per-feature enablement, polling/event budgets, quiet hours, DST, expiry, privacy and stop
controls before daemon work. Exit: simulation and bounded real soak, duplicate/restart/lease-loss/
revocation/disable tests, zero unauthorized effects and no private notification preview. An inert
candidate cannot authorize a task, cloud call or external notification. Activation and outbound
notification destinations require their own applicable authority. No second scheduler.
Read [proactivity evidence](phase-reports/PHASE_11_COMPLETION.md), [architecture](JARVIS_ARCHITECTURE.md).

### Phase 18 — Daily briefing

Outcome: one concise source-attributed briefing using only configured approved memory/projects,
email, calendar/reminders/tasks and optional Garmin/weather/news. Reuse Phase 17 scheduling and
existing evidence/summary ports. Exit: fixed fixtures for stale/missing/conflicting/private sources,
useful bounded real configured-source demonstration, explicit omissions and no invented facts/actions.
Garmin content additionally depends on Phase 8 and health authority. Briefing generation grants
no send/write/storage permissions; destination and timing remain explicit. No silent connector
activation when a source is missing. Read [historical expansion M](AGENTIC_ASSISTANT_EXPANSION.md),
the chosen source phase reports and [security](SECURITY_MODEL.md).

### Phase 19 — Laptop/PWA release and operations

Outcome: supported laptop/PWA daily-use release with a truthful acceptance receipt. Reuse existing
startup, diagnostics, migration/backup/restore, auth, lifecycle and release scripts. Exit: full
integrated enabled-feature matrix, locked clean-source/Windows CI and current audits, safe synthetic
backup/restore/crash/reconnect/erase, frozen accessibility/performance/soak targets, troubleshooting,
rollback and maintenance policy. Reconfirm laptop-off limitations and optional source availability.
Physical phone checks stay skipped/unverified; no full physical/mobile MVP claim from automated
evidence. Signing/public deployment/native distribution are excluded. No owner-store overwrite.
Read [prototype recovery receipt](PROTO_2_2_EVIDENCE.md), [backup contracts](PHASE_9B_MIGRATION.md),
[Windows setup](setup-windows.md), [PWA release evidence](phase-reports/PWA_MVP4_PROGRESS.md).

### Phase 20 — Vision and gestures

**Deferred.** Trigger: demonstrated on-demand camera/screen or gesture use case. Reuse local
capture, temporal detector, indicators and kill controls; Phase 13 alone executes typed intents.
Exit if selected: reviewed models/licenses, actual capability/resource/false-trigger targets,
authorized target-device evidence, visible capture and zero authority escalation. No hidden capture,
biometric identity, arbitrary commands or gesture approval of sensitive work.
Read [legacy vision evidence](phase-reports/PHASE_7_COMPLETION.md), [hands-free](HANDS_FREE_CONTROL.md).

### Phase 21 — Native mobile

**Deferred.** Trigger: required OS capability unmet by the PWA, plus passing native audit and a
reviewed build/signing path. Reuse M1/M2 identity contracts and existing Core APIs; provider secrets
stay in Core. Exit if selected: native dependency/functional/security/recovery/build gates with
honest target evidence. No native package publication while hold remains; new enrollment/signing
needs authority. Owner-skipped phone tests remain unverified unless explicitly restored.
Read [native architecture](MOBILE_ARCHITECTURE.md), [legacy milestones](MOBILE_PHASES.md).

### Phase 22 — Dedicated server

**Deferred under laptop-first decision.** Trigger: owner requires laptop-off availability and
selects an authorized zero-cost/approved-cost target. Reuse existing topology, fenced ownership,
encrypted migration and rollback contracts. One shared-state owner; Windows effects/capture stay
on Windows device node. Exit if selected: real local/server parity, outage/partition/restore/
rollback/security proof, documented resources and approved deployment. No standby second writer,
automatic cutover, database-on-network-share or implicit paid service.
Read [topology](PHASE_9A_TOPOLOGY.md), [migration](PHASE_9B_MIGRATION.md), [deployment](PHASE_9C_DEPLOYMENT.md).

### Phase 23 — Wearables and additional devices

**Deferred.** Trigger: selected supported device/workflow, current vendor API/license/access review
and required device/privacy authority. Reuse generic wearable capability/identity contracts and
phone bridge only when supported. Exit if selected: real required interaction, revoke/offline/
battery/indicator/removal tests, no private cloud disclosure. No vendor marketing assumption or
unapproved health write. Health analytics, watch writes, glasses, phone sensors/widgets/push and
additional OS/device integrations stay in this managed option until scoped.
Read [requirements](PHASE_10A_PRODUCT_REQUIREMENTS.md), [feasibility](PHASE_10A_FEASIBILITY.md),
[legacy wearable progress](phase-reports/PHASE_10_PROGRESS.md).

### Phase 24 — Restricted maintenance assistance

**Deferred.** Trigger: specific low-risk maintenance category with explicit boundaries after safe
tasks, scheduling and operations. Proposals/isolated candidate fixes may reuse existing bounded
contracts; production acceptance requires independent trusted review and exact authority.
Exit if selected: frozen malicious-input/budget/recovery/removal corpus with no self-expanded tools,
permissions or destinations. No self-merge/deploy, credential/security change, software install,
paid work or third-party contact authorized by the model. No self-modifying policy or hidden work.
Read [legacy proactivity](phase-reports/PHASE_11_COMPLETION.md), [security](SECURITY_MODEL.md).

## Historical alias map

This crosswalk preserves evidence, not completion credit for broader product work. Historical
report filenames and original test/migration/tool identifiers remain unchanged and must be qualified
as legacy when a number collides. Old PROTO names remain searchable aliases only.

| Historical identifier | Current phase ownership / interpretation |
| --- | --- |
| PROTO-0, PROTO-0.1, PROTO-0.2 | Phase 1, mapped complete |
| PROTO-1.1 / PROTO-1.2 | Phases 2 / 3, mapped complete |
| PROTO-2.1 / PROTO-2.2 | Phases 4 / 5, mapped complete |
| Legacy Phase 0 | Phase 2 reproducibility and Phase 19 operations foundations |
| Legacy Phase 1 | Phase 7 text/routing and Phase 11 public provider qualification; old latency debt remains |
| Legacy Phase 2 / F13 | Phase 12 voice foundation |
| Legacy Phase 3 | Phase 13 permission/actions foundation; live closeout remains open |
| Legacy Phase 4 / expansion H | Phase 10 memory foundation |
| Legacy Phase 5 / expansion B,C | Phase 11 freshness/research foundation |
| Legacy Phase 6 | Phase 14 bounded-task foundation |
| Legacy Phase 7 | Phase 20 vision/gesture foundation |
| Legacy Phase 8 / F11,F12 | Phases 3–5 accepted text transport; Phase 19 ongoing auth/recovery |
| Legacy Phase 9 / 9A–9C | Phase 22 deferred deployment; Phase 19 reuses safe backup contracts |
| Legacy Phase 10 / former M3–M9,H1–H8 wearable work | Phase 23 deferred devices; actual Garmin Core/PWA is Phase 8 |
| Legacy Phase 11 / expansion L | Phase 17 scheduling foundation; Phase 24 narrow maintenance option |
| Expansion A / D / E / K | Shared context/discovery/routing/approval foundations; Phases 7,11,13,14; no duplicate implementation phase |
| Expansion F / G | Phases 10 / 9 continuity and attachment foundations |
| Expansion I, IA, IB | Phase 15 email; IA exists, live IB authority blocker remains |
| Expansion J / M | Phases 16 / 18 calendar and briefing |
| Mobile M1,M2,M2C / native MVP 1–4 | Phase 21 deferred client; previous build/identity/physical status retained |
| PWA M3A,M3B,M3C / MVP 3 | Phase 8 health; protected-session proof retained; scopes and phone rows separate |
| PWA M4A / MVP 4 | Phase 19 quality/release; manual phone checks skipped, unverified |
| F14 / F15 | Phases 9,14 file/task foundations and Phases 7,19 workspace/reliability |

## Retained gates and authority register

| Item | Current treatment |
| --- | --- |
| Legacy NVIDIA/local-cold latency | Legacy Phase 1 remains `blocked-external`; original 20/20 and p50/p95 gates unchanged. Local fallback/prototype timings are not NVIDIA proof; Phase 11 owns any requested requalification. |
| Text usefulness | Phase 7 owns known R1/C1 failures. Historical 8/10 remains a bounded pass under the old rubric; prospective stricter target does not rewrite it. |
| Research live endpoint | Wikimedia `authentication_required` remains recorded. Phase 11 must verify actual chosen sources; no invented retrieval/citation. |
| Windows effects | Existing broker implemented; Phase 13 needs exact applicable live authority. Chat/read/task-monitor scope grants no OS/control authority. |
| Garmin | Existing protected session and normal renewal authority retained. Phase 8 grants no new login, enrollment, health scope, credential replacement or health disclosure. |
| Email/calendar | Phase 15/16 provider choices/auth/private-read authority remain external inputs when needed. Writes/sends are independently exact-approved. |
| Native dependencies | Held manifests stay unchanged and unpublished; only selected Phase 21 may revisit a passing reviewed candidate. |
| Physical phone checks | **Skipped by owner; unverified** everywhere. Do not ask, queue reminders, count passes or block repository development on them. |
| Server/native/wearable activation | Deferred rows grant no spend, deployment, signing, device enrollment or scope authority. |
| License/external code | Historical root-license question remains separate; planning does not license this repository or authorize copying incompatible external code. |

## Next action

**Next: Initiate Phase 9 — Files and attachments.** Phase 7 prerequisite and Phase 8 workspace are complete.
Read this roadmap, [Phase Execution](PHASE_EXECUTION.md) and Phase 9 references before implementation.
Preserve held native/provider changes, the accepted prototype baseline, existing failed legacy gates
and skipped/unverified phone status. Phase 8 grants no new health scope, login or automatic integration activation.
