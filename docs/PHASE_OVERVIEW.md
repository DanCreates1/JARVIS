# JARVIS Phase Overview

Navigation view, **2026-10-26**. [Master Roadmap](JARVIS_MASTER_ROADMAP.md) is the **single status
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
- **Phase 6 complete:** architecture and flat roadmap consolidation; next feature work not started.
- **Next: Phase 7 — Text quality and daily-use polish.** Fix polite-tone/checklist-format failures
  and freeze expanded evaluation before tuning. Read the master's Phase 7 definition first.
- Progress basis: **6/19 primary phase receipts closed (~32%)**; an
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
