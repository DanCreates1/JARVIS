# JARVIS Phase Overview

Navigation view, **2026-10-31**. [Master Roadmap](JARVIS_MASTER_ROADMAP.md) is the **single status
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
- **Next: Phase 12 — Foreground voice.** No automatic implementation.
- Progress basis: **11/19 primary phase receipts closed (~58%)**; an
  unweighted management count, not code/effort percentage or full mobile MVP acceptance.
- Historical prototype acceptance stays **100% = 10/10 groups**, corpus **8/10**. Full mobile MVP,
  physical acceptance and production readiness remain unestablished.

## Remaining delivery map

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
Legacy NVIDIA latency, live Windows effects, source availability and provider credential/access
gates retain their original unclosed status. Read the [gate register](JARVIS_MASTER_ROADMAP.md#retained-gates-and-authority-register).
No planning row enables integrations, creates scopes/grants, enrolls a device, deploys, signs,
spends or sends a third-party message. Historical overview: [archive](LEGACY_PHASE_OVERVIEW.md).
