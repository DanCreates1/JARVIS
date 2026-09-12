# Phase 10A Live Knowledge and Controlled Maintenance Requirements

Status: implemented foundation
Reviewed: 2026-09-12

## Product outcomes

JARVIS must reduce practical knowledge-cutoff risk through live, cited retrieval when current facts
matter. JARVIS may detect improvement opportunities from sanitized logs and explicit user feedback,
but detection and proposal are never authority to modify production.

These are cross-cutting requirements inherited by wearable clients. A wearable transport cannot
bypass Phase 5 research trust, Phase 3 approval, Phase 6 task bounds, identity, privacy, or audit.

## Live knowledge retrieval

- Current-fact requests route through the existing bounded Phase 5 search/fetch/parse/synthesis
  pipeline, not model memory alone.
- Material claims retain source citations. Each source exposes URL, retrieval time, optional
  publication time, last-check time, and explicit expiration.
- Callers choose a bounded maximum age. The earliest source expiration controls the whole answer.
- Output identifies `live`, `fresh_cache`, or `stale_offline`; cached data is never mislabeled live.
- Online expired data fails with `live_refresh_required`. It must be refreshed before presentation
  as current.
- Offline fallback is explicit and bounded. Unexpired cache may be used as `fresh_cache`; expired
  cache may be used only inside the caller's stale allowance and is labeled `stale_offline`.
  Data beyond that allowance fails with `offline_cache_expired`.
- Conflicting claims keep distinct citations and a visible contradiction summary. Hidden conflicts
  fail closed.
- No design can guarantee current knowledge while offline or when authoritative sources are
  unavailable. Responses must state that limitation instead of inventing freshness.

Implementation: `jarvis.research.freshness` wraps validated Phase 5 `ResearchReport` values. It
does not create network authority, accept paywall bypass, silently store sources, or treat retrieved
text as trusted instructions.

## Controlled self-improvement and feature addition

Default mode is `suggestion`:

1. Detect a bounded issue signal from a sanitized log event or explicit user-feedback reference.
2. Store only evidence identifiers and SHA-256 digests in the proposal boundary.
3. Produce a reviewable proposal. Do not edit, branch, install, execute, merge, deploy, spend, or
   contact anyone.

Optional `restricted_autonomous` mode remains default-off and requires an explicit host allowlist
containing only low-risk categories: documentation, tests, formatting, or static analysis. It may
prepare work only in an isolated `jarvis-maintenance/*` branch and sandbox. It never authorizes
production.

Every isolated candidate requires:

- an exact 40-character base revision, separate candidate revision, and rollback revision equal to
  the reviewed base;
- format, lint, type, unit, security, regression, dependency-audit, and secret-scan receipts;
- unique audit event identifiers covering proposal, implementation, verification, review, and any
  rollback; and
- explicit user approval through the trusted host before merge, deployment, or other production
  change.

Autonomous maintenance can never alter safety rules, permission policy, identity/authentication,
protected core/broker/remote surfaces, CI workflow authority, dependency manifests, or security
documentation. It can never install software, spend money, contact people, accept terms, create
accounts, weaken tests, raise budgets, grant itself permissions, or authorize its own production
change. Those actions are structurally absent or fixed false in `jarvis.maintenance`.

## Acceptance evidence

- Live reports prove citations, source timestamps, expiration, and earliest-expiry aggregation.
- Fresh and stale offline fallback remain distinguishable and bounded.
- Expired online reports demand refresh; over-age offline reports fail.
- Conflicts cannot be hidden.
- Suggestion mode never starts isolated implementation.
- Restricted mode allows only pre-approved category/path pairs.
- Protected paths, path escape, missing checks, duplicate checks, missing audit history, wrong
  rollback revision, production authority, software installation, spending, and external contact
  fail closed.

## Deferred runtime work

Phase 10A defines and tests the boundary. Product-surface routing of ordinary current-fact questions
into Phase 5 and any real maintenance worker/branch creator remain separately reviewed integration
work. No background monitor, production merger, deployer, package installer, payment tool, or
messaging tool is enabled here.
