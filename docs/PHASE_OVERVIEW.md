# JARVIS Phase Overview

Updated: 2026-09-11

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
| 1 | Privacy-aware text core | Blocked external | 1D NVIDIA gate plus local-cold revalidation | `gpt-6-astra` / `max` |
| 2 | Local-first voice | Implemented; closeout pending | 2C authorized device closeout | `gpt-5.6-sol` / `high` |
| 3 | Controlled computer access | Implemented; closeout pending | 3C authorized live closeout | `gpt-6-astra` / `max` |
| 4 | Durable memory | Complete | 4A-4C complete | `gpt-6-astra` / `xhigh` aggregate |
| 5 | Research | Complete | 5A-5C complete | `gpt-6-astra` / `xhigh` aggregate |
| 6 | Bounded tasks | Complete | 6A-6C complete | `gpt-6-astra` / `ultra` aggregate |
| 7 | Vision and gestures | Complete | 7A-7C complete | `gpt-6-astra` / `max` |
| 8 | Secure phone/PWA | Complete | 8A-8D complete | `gpt-6-astra` / `max` |
| 9 | Dedicated server migration | Implemented; live closeout pending | 9A-9C local gates complete; authorized server cutover pending | `gpt-6-astra` / `max` |
| 10 | Generic wearables | Not started; lower priority | 10A feasibility/license/contracts | `gpt-5.6-sol` / `high` |
| 11 | Advanced proactive/multimodal | Not started; long-term | 11A trigger/proactivity policy | `gpt-6-astra` / `ultra` |

## Phase 1 latency disposition

Phase 1 remains `blocked-external`, not complete. Current governance makes the hosted NVIDIA
numbers a hard provider-specific acceptance gate: simple 1,000/2,500 ms and complex 3,000/7,000 ms
p50/p95, with 20 successful observations per cold/warm state. It has no external-dependency closure
status. Adaptive routing therefore improves JARVIS product responsiveness but cannot make that gate
green.

The evidence categories are deliberately separate:

| Category | Current status |
| --- | --- |
| JARVIS product responsiveness | Protected by deterministic Tier 0, local-first Tier 1, responsive cloud Tier 2, and degraded-provider fallback |
| Local latency | Prior 20/20 cold/warm gate passed; two 2026-09-08 revalidations passed deterministic/warm but cold p50 regressed to 2,383.312 and 2,305.991 ms |
| Fast-cloud latency | Configuration-driven Groq Tier 2; no replacement measurement is used as NVIDIA evidence |
| NVIDIA-specific latency | Preserved 80/80 run misses targets; fresh phase-resolved run remained tens of seconds and stopped fail-closed on capacity |
| Provider-controlled tail | Fresh successful requests spent roughly 42–58 seconds waiting for response headers, then only about 0.1–0.2 seconds to first visible output |

NVIDIA free-endpoint p95 remains above target and is not technically fixed. NVIDIA stays available
for explicit deep reasoning where latency is acceptable. Revalidate after provider behavior or the
endpoint changes. Phase 7 may be developed as an independent next milestone because its declared
dependency is Phase 3/media privacy, but it must not be described as following a completed Phase 1.

## Recommended order

1. Keep Phase 1 formally blocked. Retry the fixed NVIDIA gate only when free-endpoint tail latency
   improves, and recheck the fresh local-cold regression. Retain all prior evidence rather than
   replacing it with routed product latency.
2. With separate authority, repeat Phase 2 live device and Phase 3 live application/device smokes.
3. Maintain completed Phase 4 memory and the safe local Phase 2/3 baselines.
4. Maintain completed Phase 5 research and its untrusted-evidence/storage-approval boundary. Phase
   1 NVIDIA latency is an accepted known limitation, but its unchanged formal gate remains
   `blocked-external`.
5. Maintain completed Phase 6 bounded tasks and its default-off, foreground-only execution boundary.
6. Maintain completed Phase 7 capture, local detection/gesture, and default-off Phase 3 mapping
   boundaries. Keep model downloads explicit, capture foreground-only, and all action authority in
   Phase 3. Preserve the explicit Phase 1 blocker.
7. Maintain completed Phase 8 identity, signed API, durable browser cookie,
   origin/CSRF/CORS/CSP, rate-limit, local-only sensitive approval, offline-safe PWA, scoped product
   transport, bounded reconnect, tailnet-only TLS deployment, real-phone revocation, and rollback
   boundaries. Phase 9A topology/protocol/identity and Phase 9B migration/recovery are complete:
   runtime remains hard-locked local-only, and encrypted snapshots, exact shadow checks, fenced
   ownership receipts, and rollback rehearsal are verified. Phase 9C adds receipt-gated startup,
   hardened single-replica service specs, immutable release rollback, minimal health, and passing
   local chaos gates. Real server cutover remains pending separate deployment authority.

Hands-free control is a cross-phase track: Phase 2 detects claps, Phase 7 recognizes hand
gestures, and Phase 3 alone authorizes and executes the mapped computer action. See
[Hands-Free Control Plan](HANDS_FREE_CONTROL.md).

Each lettered subphase is one session capped at five elapsed hours. See the playbook for exact
scope, tests, security/privacy, documentation, acceptance, exit, and per-subphase assignments.
