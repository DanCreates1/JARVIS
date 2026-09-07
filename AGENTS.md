# JARVIS Codex Instructions

These repository instructions apply to every Codex task in JARVIS.

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

- Use the phase's listed Sol thinking level as the minimum recommendation. Codex cannot change the
  user's selected model or reasoning effort; never claim it did. Continue with maximum available
  diligence unless the user must select a stronger model for a safety-critical decision.
- A request to finish a phase means persist through safe in-scope implementation and verification.
  It does not authorize purchases, paid APIs, account creation, credential changes, remote
  deployment, destructive data operations, messages to third parties, or GitHub pushes.
- Ask only when a missing choice materially changes scope, creates cost, discloses data, grants
  permissions, or causes external/irreversible impact.
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
