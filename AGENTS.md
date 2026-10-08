# JARVIS Codex Instructions

These repository instructions apply to every Codex task in JARVIS.

## Cross-chat handoff

- After completing a task or subphase, end the final reply with a standalone, copy-pasteable
  **Next chat:** prompt. Make it the last text in the reply.
- Name the exact next phase/subphase (for example, `Initiate phase 4` or `Initiate mobile subphase
  M2C`) and include only essential repository state, prerequisite, and blocker context so a new
  chat can resume without this conversation. Do not include credentials, tickets, or private data.
- A handoff prompt is not permission to start the next subphase in the current chat. Respect each
  subphase's scope. Apply the confirmation policy below; do not renew routine permissions at
  each subphase or chat boundary.
- If no next phase is planned, end with `Next chat: No phase queued.` rather than inventing work.
- While the mobile MVP is active, include an estimated app-completion percentage or progress bar
  after every work session. State the estimate's basis and keep the handoff prompt last.

## Codex confirmation policy

- Owner instruction (2026-10-08): proceed with requested work; ask permission only for important
  consequential actions. Existing explicit approval persists within its scope across turns/chats.
- Do not ask again for routine repository reads/edits, locked setup, tests, local services,
  configured free integrations within the requested task, or publication covered by standing
  commit/push instructions.
- Requested Garmin saved-session work includes offline import from the selected explicit local
  file into an empty protected store, bounded Core reads, required profile/settings reads during
  saved-session authentication, and normal same-account token renewal. No separate per-run
  permission is needed. Ask for a missing source path as information, not authorization.
- Confirm consequential actions only when not already explicitly approved: spending/billing or
  material legal commitments; destructive user-data operations or history rewrites; new credential
  login/MFA, account recovery, token replacement/revocation; device enrollment, new scopes or other
  security/access changes; signing, remote/public deployment; private-data disclosure beyond the
  task's intended service; messages to third parties. Group related actions into one concrete
  reviewable approval. Never repeat an unanswered permission request as new preparation work.
- This policy supersedes older routine fresh/per-session Codex permission gates in repository
  documents. Historical evidence remains historical. Application authentication, policy approvals,
  privacy routing, allowlists, audit and security tests remain enforced.

## Phase command trigger

When the user says `initiate phase X`, `start phase X`, `continue phase X`, `finish phase X`,
or an obvious equivalent where `X` is 0–11:

1. Read `docs/CODEX_PHASE_PLAYBOOK.md` completely before planning or changing files.
2. Read the target phase section plus every target-phase reference listed by the playbook.
3. Inspect current code, tests, Git state, installed tools, and prior phase reports. Never assume the
   roadmap status is still accurate.
4. Follow the playbook's universal execution protocol and target phase gates.
5. Create or resume `docs/phase-reports/PHASE_X_PROGRESS.md` from the supplied template.
6. Work milestone-by-milestone until the phase exit criteria pass or a genuine external blocker
   requires user action.
7. Do not declare the phase complete because code exists. Run the required acceptance, security,
   quality, hardware, and documentation checks and preserve evidence.
8. When complete, rename/update the report to `PHASE_X_COMPLETION.md`, update
   `docs/PHASE_OVERVIEW.md`, `docs/JARVIS_MASTER_ROADMAP.md`, and relevant architecture/setup
   documentation.

## Phase execution rules

- Use the phase/subphase's listed Codex model and reasoning level as the minimum recommendation. Codex cannot change the
  user's selected model or reasoning effort; never claim it did. Continue with maximum available
  diligence unless the user must select a stronger model for a safety-critical decision.
- A request to finish a phase means persist through safe in-scope implementation and verification.
  Use existing authority and the confirmation policy above; normal saved-session renewal is part
  of requested integration work. Purchases, new accounts and consequential effects require explicit
  approval if the existing request does not already cover them. GitHub publication follows the
  standing instruction below.
- Ask for missing information only when it materially affects execution. Permission questions are
  reserved for the consequential actions above; routine external reads are not permission gates.
- Never bypass privacy routing, approvals, tool schemas, allowlists, audit, authentication, cost
  limits, or security tests to satisfy a phase deadline.
- Preserve unrelated user changes. Never reset, discard, or overwrite a dirty worktree.
- Do not put secrets, model weights, runtime databases, logs, recordings, screenshots, or private
  user data in Git.
- Use current official primary documentation for dependencies, provider behavior, security rules,
  Windows APIs, and hardware-sensitive implementation.
- Keep code provider-neutral and configuration-driven. Model output is untrusted data, never
  authorization.
- Run the narrowest relevant checks during development and the complete phase gate before closure.
- Standing user authorization (2026-09-07): after completed repository work and required gates,
  commit and push all current safe source changes to the configured GitHub upstream. This does not
  authorize secrets, private runtime data, generated artifacts, destructive Git, history rewrites,
  or force-pushes. Preserve and report any unsafe or ambiguous artifact instead of publishing it.

## Repository quality commands

Use the repository scripts and locked environment. On this workstation, follow the global RTK shell
requirement as well.

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
```

If Windows pytest temporary-directory permissions fail, use a new verified workspace-local
`--basetemp` directory under ignored `runtime/`; do not weaken or skip the test gate.
