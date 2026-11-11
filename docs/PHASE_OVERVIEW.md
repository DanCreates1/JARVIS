# JARVIS Phase Overview

Navigation view, **2026-11-10**. [Master Roadmap](JARVIS_MASTER_ROADMAP.md) is the **single status
ledger** and owns scope/dependencies. [Phase Execution](PHASE_EXECUTION.md) owns commands;
[current reports](phase-reports/current/) hold acceptance evidence. Old phase numbers are legacy
aliases; the [crosswalk](JARVIS_MASTER_ROADMAP.md#historical-alias-map) resolves collisions.

## Selected architecture

**One modular Python Core on Windows laptop; PWA first.** Core owns SQLite/FTS5, conversation,
memory, model routing, permissions and audit. Laptop on/reachable is required. Private/uncertain
context stays local; optional public cloud remains gated at $0. Existing approved private HTTPS
and application identity stay intact. [Architecture decision](JARVIS_ARCHITECTURE.md#current-core-decision--2026-10-26).

## Current position

- **Phases 1–5 complete:** mapped PROTO audit, security baseline, runnable text, integrated
  acceptance and recovery/receipt. Original evidence and scope limits remain unchanged.
- **Phase 6 complete:** architecture and flat roadmap consolidation.
- **Phase 7 complete — Text quality and daily-use polish.** Explicit daily text profile;
  repeated 10/10 original and 37/40, 37/40, 36/40 expanded, every safety case passing.
  [Completion evidence](phase-reports/current/PHASE_7_COMPLETION.md) retains failures and limits.
- **Phase 8 complete — Private Garmin workspace.** Large-output pipe cleanup repair passes full gates
  and fresh CI. Explicit opt-in profile; current protected
  Core read and synthetic lifecycle evidence in [completion report](phase-reports/current/PHASE_8_COMPLETION.md).
  Production health scope/enrollment remains separate; no physical acceptance inferred.
- **Phase 9 complete — Files and attachments.** Explicit private-files; current cited PWA/Core
  workflow and recovery/security/release gates pass, with fresh CI.
  [Completion evidence](phase-reports/current/PHASE_9_COMPLETION.md). No production feature activation.
- **Phase 10 complete — Inspectable memory and project context.** Explicit private-memory profile,
  trusted-local exact review, source-explained retrieval and private project context; full gates and
  fresh CI pass. [Completion evidence](phase-reports/current/PHASE_10_COMPLETION.md).
- **Phase 11 complete — Grounded public research.** Explicit public-source excerpts, exact citations,
  current PDF security repair, full working/isolated gates and fresh CI pass.
  [Completion evidence](phase-reports/current/PHASE_11_COMPLETION.md). Wikimedia discovery retains
  its historical authentication blocker; general discovery and optional cloud remain unqualified.
- **Phase 12 complete — Foreground voice.** Explicit local speech/review/Send/text replies;
  current Windows synthetic workflow, full release/security gates and fresh CI pass.
  [Completion evidence](phase-reports/current/PHASE_12_COMPLETION.md). Host controls unchanged.
- **Phase 13 complete — Controlled Windows actions.** Restricted typed CLI
  actions, catalog/cancel and durable exact-policy binding; current app/STOP and separately
  authorized bounded volume retry pass. Built-in speakers retain their existing 100%; original
  headphone default/scalar/mute restored exactly. Earlier headphone readback failure retained;
  arbitrary percentages/all outputs unqualified. Fresh release gates and reviewed publication pass.
  [Completion evidence](phase-reports/current/PHASE_13_COMPLETION.md), [controls](CONTROLLED_WINDOWS.md).
  No production activation or automatic live-effect authority.
- **Phase 14 complete — Bounded tasks and project workflows.** Trusted-local project reviews,
  durable foreground controls, restart/ownership acceptance and full release gates pass. Remote monitoring remains
  read-only. [Completion evidence](phase-reports/current/PHASE_14_COMPLETION.md).
- Progress basis: **15/19 primary phase receipts closed (~79%)**; an
  unweighted management count, not code/effort percentage or full mobile MVP acceptance.
- **Phase 15 implemented-closeout-pending — Email.** Personal Gmail / desktop OAuth / `gmail.readonly`
  selected. Bounded read adapter/protected Windows auth/default-off composition implemented.
  Actual approved setup/auth/protected grant passed. First selected thread exceeded the fixed
  size limit; a second one-message source passed live read/preparation with verified provenance
  and an unsent/unstored draft. Current release/documentation closeout pending. [Setup](GMAIL_SETUP.md),
  [progress](phase-reports/current/PHASE_15_PROGRESS.md),
  [provider/auth decision](EMAIL_PROVIDER_DECISION.md). Local exports remain available; production
  acquisition stays off.
- Historical prototype acceptance stays **100% = 10/10 groups**, corpus **8/10**. Full mobile MVP,
  physical acceptance and production readiness remain unestablished.
- **Phase 16 blocked-external — Calendar and reminders.** Explicit bounded local ICS inspection,
  conflict/change proposals and owner-authored drafts reuse existing Core/foreground reminder
  controls. [Contract](CALENDAR.md), [progress](phase-reports/current/PHASE_16_PROGRESS.md).
  Local foundation gates pass. Google primary on Phase 15's personal account selected;
  inactive read/protected foreground auth/proof commands and [setup review](GOOGLE_CALENDAR_SETUP.md)
  prepared. Setup approval, actual new grant and authorized live-read evidence pending;
  no new scopes or worker activated.

## Remaining delivery map

Phase 17 is **complete**: exact opt-in worker, full source gates, isolated 1,800-tick Windows
soak, task-only source publication and fresh exact-source CI pass.
[Completion](phase-reports/current/PHASE_17_COMPLETION.md), [bounded controls](BACKGROUND_PROACTIVITY.md).
Production activation/external notifications excluded; Phase 18 remains unstarted.

Definitions, exact prerequisites, current status and gates are in the master:

| Current IDs | Planned owner value |
| --- | --- |
| 7 | Text quality and daily-use polish |
| 8 | Private read-only Garmin workspace |
| 9 | Files and attachments |
| 10 | Inspectable memory and project context |
| 11 | Grounded public research |
| 12 | Foreground voice |
| 13 | Controlled Windows actions |
| 14 | Bounded tasks and project workflows |
| 15 | Email read/prepare; external sends independently authorized |
| 16 | Calendar and reminders |
| 17 | Opt-in background scheduling and proactivity |
| 18 | Daily briefing from approved sources |
| 19 | Laptop/PWA integrated release and operations |
| 20–24 | Deferred vision/gestures, native mobile, server, wearables/devices and narrow maintenance assistance |

## Preserved boundaries

Manual phone checks: **skipped by owner; unverified**. No phone request/reminder, pass or physical
acceptance inferred. Native dependency publication hold and unrelated provider changes remain.
Legacy NVIDIA latency, source availability and provider credential/access gates retain their
original unclosed status. Earlier Windows headphone readback failure remains recorded alongside
the bounded current pass. Read the [gate register](JARVIS_MASTER_ROADMAP.md#retained-gates-and-authority-register).
No planning row enables integrations, creates scopes/grants, enrolls a device, deploys, signs,
spends or sends a third-party message. Historical overview: [archive](LEGACY_PHASE_OVERVIEW.md).
