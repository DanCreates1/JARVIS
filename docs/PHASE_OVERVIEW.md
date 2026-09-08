# JARVIS Phase Overview

Updated: 2026-09-08

This is the concise execution view of the master roadmap. Status describes implemented code,
not just design work. Model/reasoning values are Codex execution recommendations, not JARVIS
runtime providers.

To execute a phase with Codex, use `Initiate Phase X and finish it.` Root `AGENTS.md` then loads
the full [Codex phase execution playbook](CODEX_PHASE_PLAYBOOK.md), including prerequisites,
implementation protocol, acceptance gates, safety boundaries, and completion reporting.

## Model guide

| Model | Use |
| --- | --- |
| `gpt-6-astra` | Architecture, security, difficult debugging, cross-system work, migration, high-risk decisions |
| `gpt-5.6-sol` | Strong general implementation, evaluation, closeout |
| `gpt-5.6-terra` | Bounded known-pattern implementation and UI |
| `gpt-5.6-luna` / `gpt-5.4-mini` | Isolated mechanical work only; never security design or phase closure |

## Phase status

| Phase | Scope | Status | Active subphase | Model / reasoning |
| --- | --- | --- | --- | --- |
| 0 | Repository baseline | Complete | Continuous audit | `gpt-5.6-sol` / `medium` |
| 1 | Privacy-aware text core | Blocked external | 1D hosted latency closeout | `gpt-6-astra` / `max` |
| 2 | Local-first voice | Implemented; closeout pending | 2C authorized device closeout | `gpt-5.6-sol` / `high` |
| 3 | Controlled computer access | Implemented; closeout pending | 3C authorized live closeout | `gpt-6-astra` / `max` |
| 4 | Durable memory | Complete | 4A-4C complete | `gpt-6-astra` / `xhigh` aggregate |
| 5 | Research | Complete | 5A-5C complete | `gpt-6-astra` / `xhigh` aggregate |
| 6 | Bounded tasks | Complete | 6A-6C complete | `gpt-6-astra` / `ultra` aggregate |
| 7 | Vision and gestures | Not started | 7A capture/privacy | `gpt-6-astra` / `xhigh` |
| 8 | Secure phone/PWA | Loopback foundation only | 8A API/identity/enrollment | `gpt-6-astra` / `ultra` |
| 9 | Dedicated server migration | Not started | 9A topology/protocol/identity | `gpt-6-astra` / `ultra` |
| 10 | Generic wearables | Not started; lower priority | 10A feasibility/license/contracts | `gpt-5.6-sol` / `high` |
| 11 | Advanced proactive/multimodal | Not started; long-term | 11A trigger/proactivity policy | `gpt-6-astra` / `ultra` |

## Recommended order

1. Retry Phase 1 hosted NVIDIA latency gate only when free endpoint tail latency improves; all four
   hosted states already have 20 successful observations. Retain the passing local, privacy,
   zero-cost, and independent clean-Windows gates.
2. With separate authority, repeat Phase 2 live device and Phase 3 live application/device smokes.
3. Maintain completed Phase 4 memory and the safe local Phase 2/3 baselines.
4. Maintain completed Phase 5 research and its untrusted-evidence/storage-approval boundary. Phase
   1 NVIDIA latency is an accepted known limitation, but its unchanged formal gate remains
   `blocked-external`.
5. Maintain completed Phase 6 bounded tasks and its default-off, foreground-only execution boundary.
6. Add Phase 7 vision and gestures, then phone, server, wearables, and proactive behavior in
   Phases 8–11.

Hands-free control is a cross-phase track: Phase 2 detects claps, Phase 7 recognizes hand
gestures, and Phase 3 alone authorizes and executes the mapped computer action. See
[Hands-Free Control Plan](HANDS_FREE_CONTROL.md).

Each lettered subphase is one session capped at five elapsed hours. See the playbook for exact
scope, tests, security/privacy, documentation, acceptance, exit, and per-subphase assignments.
