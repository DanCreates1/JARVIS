# Current numbered phase execution

Effective **2026-10-26**. Active commands use the phase IDs in
[Master Roadmap](JARVIS_MASTER_ROADMAP.md), following the owner-selected
[core architecture](JARVIS_ARCHITECTURE.md#current-core-decision--2026-10-26).
This is the sole active execution protocol. [Old playbook](CODEX_PHASE_PLAYBOOK.md), lettered
tracks, mobile MVPs and PROTO IDs are historical references, not competing execution queues.

## Resolve a command

`Initiate Phase N`, `Start Phase N`, `Continue Phase N` and `Finish Phase N` address the current
roadmap, regardless of an old document with the same number. Read this file, the full master
roadmap, current architecture decision, the selected phase references, security/authority rules
and current report before implementation. No fixed 0–11 range applies: use defined IDs only.
An undefined ID needs a roadmap clarification; never invent a new phase from the command.

An explicit `Legacy Phase N`, lettered/mobile/F-series reference or old PROTO command selects
its historical contract and the master's alias map. Name both the alias and current phase in the
report. Never overwrite legacy reports or substitute a new acceptance pass for a failed old gate.
Existing historical implementation is reused; current product acceptance must still be evidenced.

Use **one integer per phase**. Work checklists and resume-safe milestones stay inside that phase's
report; session boundaries do not create `7A`, `7.1` or new roadmaps. Add a subphase only when an
actual independent release/authority boundary requires it, with a recorded reason and updated
master map. Never add subphases solely because work spans several chats.

## Start and resume

1. Inspect Git, code, tests, installed tools and relevant prior reports. Preserve unrelated files;
   distinguish published source from held working changes. Read current primary documentation for
   changing provider, dependency, OS and security facts.
2. Resolve only actual dependencies listed in the master. Numeric order is delivery priority,
   not an invented prerequisite chain. Existing verified contracts can satisfy technical
   prerequisites. If an external input blocks one phase, continue independent work already
   requested; do not silently change release order or start an unrequested feature phase.
3. Create/resume `docs/phase-reports/current/PHASE_N_PROGRESS.md` using
   [current template](phase-reports/current/TEMPLATE.md). Phases 1–5 are mapped historical receipts;
   keep original evidence names, dates, thresholds and limitations.
4. Record deliverables and exclusions, existing code to reuse, exact functional/privacy/security/
   performance/recovery acceptance, required authority and commands. Freeze fixtures and numeric
   targets before live measurement or tuning. Report implementation separately from acceptance.
5. Work one bounded milestone at a time. Fix failed gates under existing authority; never lower a
   threshold, suppress an audit, waive a failure or relabel a skipped check to pass.
6. Update the report after verified milestones. Stop after five elapsed hours; at four hours,
   reserve the remaining hour for gates, evidence, recovery and a resume-safe handoff.

## Design and authority

- Preserve one conversation runtime, canonical store, model router, permission system and bounded
  scheduler. Add ports/adapters before vendor-specific behavior; no empty future modules.
- Model/client/source/tool content is data, never an approval or grant. Enforce schemas, size/time/
  retry/cancel/budget limits, ownership, idempotency, audit and fail-closed degradation outside models.
- Private or uncertain candidate disclosure stays local. Health/provider credentials and raw
  private data never enter cloud requests, client caches, diagnostics or Git. Optional integrations
  and public cloud need their existing settings and approvals; planning enables nothing.
- Apply root [confirmation policy](../AGENTS.md#codex-confirmation-policy). Routine repository
  work, local services, locked setup and in-scope saved-session renewal need no new permission.
  Consequential effects outside existing authority require one concrete, prepared decision.
- Phone checks remain **skipped by owner; unverified**. Never request them or use a skip as a pass.
  Native dependency publication hold remains; no phase command grants deployment/signing authority.
- Keep `prototype-text` as the accepted regression baseline. Future capability expansion must be
  explicit and configuration-driven, with no second Core or automatic feature activation.

## Verification and release

Run focused checks during development, then required release gates before completion:

```powershell
rtk proxy uv lock --check
rtk proxy uv sync --locked --link-mode copy
rtk proxy uv run --locked ruff format --check .
rtk proxy uv run --locked ruff check .
rtk proxy uv run --locked mypy src
rtk proxy uv run --locked python -m pytest --basetemp <new-verified-ignored-runtime-directory>
rtk proxy uv run --locked python -m pip_audit
rtk proxy uv lock --project garmin_sync --check
rtk proxy uv sync --project garmin_sync --locked --link-mode copy
rtk proxy uv run --locked python -m pip_audit --path garmin_sync/.venv/Lib/site-packages
rtk proxy node --test tests/pwa/garmin-lifecycle.test.cjs tests/pwa/pcm-worklet.test.cjs
rtk proxy node scripts/pwa-accessibility-check.cjs
rtk proxy gitleaks detect --source . --redact --no-banner
rtk git diff --check
```

Use `PWA_TEST_PROFILE=prototype-text` for the additional prototype desktop harness. Restore and
audit optional voice/vision extras and verify starting package versions after base sync. Use
module entry points when generated shims are blocked; never bypass OS application policy.
Doctor/live checks must use explicitly isolated state or already-authorized configuration;
never load a real owner store merely to verify documentation. Live inference stays opt-in and
outside ordinary CI. Document-only changes need link/anchor and command-routing review as well.

Include invalid input, timeout, cancellation, malformed response, unavailable provider/device,
restart, duplicate/replay, ownership denial, privacy leakage and safe degradation as relevant.
Required live evidence must be current; an external blocker leaves acceptance incomplete.
An owner-skipped phone check remains separate unverified physical acceptance, never a pass.
Preserve the 85% coverage floor and existing provider-specific latency/security criteria.

## Status and closure

Allowed phase statuses: `not-started`, `in-progress`, `blocked-prerequisite`, `blocked-external`,
`implemented-closeout-pending`, `complete`, `deferred`. `deferred` means deliberately outside the
active release queue; it grants no acceptance credit. Blockers must name attempted fixes, missing
input/access/authority, and independent safe work completed. A failed gate alone is not an external
blocker or permission boundary. The root failed-gates policy applies in every checkout.

`complete` requires all selected scope, applicable current gates, recovery/documentation and
honest evidence. Rename the current progress report to `PHASE_N_COMPLETION.md`; update the master
ledger and short overview together. The master is status authority; overview is a navigation view.
Do not claim native/physical/MVP/production acceptance from repository implementation or a renamed ID.

Under standing publication authority, stage only reviewed safe changes. On dirty shared documents,
isolate this task's hunks; do not sweep provider/native work or private/generated artifacts. Validate
the intended publication source when it differs from the working checkout. No force-push, history
rewrite, unsafe deletion or reset of user work. Verify exact HEAD/tracking/live remote agreement
after push, and fresh relevant CI separately. Initial CI is not evidence for a later commit.

End with outcome, concise checks/limits, progress basis and a final copy-pasteable `Next chat:`
prompt naming the next **current numbered phase**. Planning or that handoff never starts the next
implementation phase automatically. Deferred rows require an explicit owner priority decision.
