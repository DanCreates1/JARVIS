# Phase 0 Repository Rebuild Plan

Status: procedure only; **do not execute cleanup during this planning run**  
Repository: `https://github.com/DanCreates1/JARVIS`  
Primary branch: `main`

## 1. Current-state decision

Inspection on 2026-08-19 shows Phase 0 has already been executed:

- `main` is the rebuilt secure core at pre-planning commit `2cd67b3`.
- Remote and local archive branch `archive/pre-jarvis-rebuild-2026-08-18` exists at `465b25f`.
- `main` contains new Python 3.11 source, tests, CI, locked dependencies, `.gitignore`, `.env.example`, and documentation.
- Recent history includes `d6114c8 chore: reset legacy JARVIS implementation`.
- Worktree was clean at planning start.

**Required action in the next implementation run:** verify these facts and mark Phase 0 complete. Do not remove `src/`, `tests/`, `docs/`, or other current files. The destructive reset section below applies only to a repository proven to still contain the unarchived legacy implementation.

## 2. Safety invariants

- Work only in the exact clone of `DanCreates1/JARVIS`.
- Preserve `.git`; never replace or reinitialize it.
- Never use `git reset --hard`, `git clean -fdx`, history rewriting, or force-push.
- Never delete or overwrite a dirty/unreviewed worktree.
- Archive and verify the exact legacy HEAD remotely before cleanup.
- Scan for secrets before pushing an archive. If any real secret exists, stop, revoke it, and use an explicit history-remediation plan; do not publish it in an archive.
- Stage explicit intended paths after the reset. Do not commit model weights, runtime state, private data, or credentials.
- Do not repeat reset steps when the rebuilt markers and remote archive are already verified.

## 3. Step A — Preflight and identity verification

Run from a normal user PowerShell session:

```powershell
Set-Location -LiteralPath 'C:\Users\poyan\OneDrive\Desktop\JARVIS'
git status -sb
git remote -v
git remote get-url origin
git branch --show-current
git rev-parse --show-toplevel
git rev-parse HEAD
git fetch --prune origin
git status -sb
```

Expected:

- repository root equals the intended JARVIS directory;
- `origin` resolves to `https://github.com/DanCreates1/JARVIS.git` or an owner-approved equivalent;
- active branch is `main`;
- worktree is clean;
- `main` is not ahead/behind unexpectedly.

If dirty, list exact changes with `git status --short` and `git diff --stat`; stop until each file is classified. Do not stash, discard, stage, or overwrite unknown changes automatically.

Verify GitHub authentication without printing tokens:

```powershell
git ls-remote --heads origin main
```

`gh auth status` is useful when GitHub CLI is installed, but plain authenticated Git is sufficient for direct branch push. Never paste credentials into a command or repository file.

## 4. Step B — Secret and large-file gate

Inspect tracked names and sizes:

```powershell
git ls-files
git count-objects -vH
git grep -n -I -E '(BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY|api[_-]?key|client[_-]?secret|password|token)'
```

Use Gitleaks if installed:

```powershell
gitleaks git --redact --no-banner
```

Explicitly inspect for:

- `.env`, passwords, tokens, cookies, private keys, certificates;
- personal conversations, databases, logs, screenshots, audio/video;
- `*.gguf`, `*.safetensors`, `*.onnx`, checkpoints, Ollama blobs;
- large generated archives or binaries.

False positives may exist in documentation and `.env.example`; review them. A genuine secret blocks archive push. Revoke it first and create a separately approved history-cleaning incident plan.

## 5. Step C — Detect whether reset is already complete

Run:

```powershell
git log -5 --oneline --decorate
git branch -a -vv
git ls-remote --heads origin 'refs/heads/archive/*'
git ls-files 'src/jarvis/*' 'tests/*' '.github/workflows/*' 'uv.lock' '.env.example'
```

Treat Phase 0 as already complete when all are true:

1. a verified remote archive points to the intended legacy commit;
2. `main` contains the new modular core rather than legacy monolith;
3. baseline tests/CI/configuration exist;
4. history shows an intentional reset/rebuild commit;
5. no requirement says to discard the rebuilt core.

For the current repository, expected archive is:

```text
refs/heads/archive/pre-jarvis-rebuild-2026-08-18 -> 465b25f
```

If the condition is met, **skip Steps D–F**, run validation in Step G, and begin Phase 1 gap work.

## 6. Step D — Create and verify legacy archive (only if not already done)

Preconditions: clean verified legacy `main`, no real secret in history to be pushed, authenticated remote access.

Choose an immutable descriptive name using the actual date:

```powershell
$ArchiveBranch = 'archive/pre-jarvis-rebuild-YYYY-MM-DD'
git switch -c $ArchiveBranch
git push -u origin $ArchiveBranch
git rev-parse HEAD
git ls-remote --heads origin "refs/heads/$ArchiveBranch"
```

The local `git rev-parse HEAD` SHA and remote `git ls-remote` SHA must match exactly. Record both in the implementation log.

If the branch already exists, do not overwrite it. Compare SHAs. If it is the correct archive, use it; if not, stop and choose a new owner-approved archive name.

Return to current remote `main` without rewriting history:

```powershell
git switch main
git pull --ff-only origin main
git status -sb
```

## 7. Step E — Review the exact removal set (legacy only)

Create a tracked-file inventory and classify each top-level path as:

- remove as failed legacy implementation;
- carry forward deliberately (for example license or useful neutral documentation);
- replace with new baseline;
- investigate before action.

Useful read-only commands:

```powershell
git ls-files
git status --short
git diff --no-index -- NUL NUL
```

The final no-op command is optional and not a removal command. The important artifact is a reviewed path list. Do not use a wildcard deletion command or remove untracked files. Move any untracked personal/unknown content to an explicit external quarantine only after owner review.

Approval checkpoint must state:

- exact repository root;
- exact `main` HEAD;
- verified archive branch and SHA;
- top-level paths to remove/replace;
- confirmation that no unrelated or untracked data will be deleted.

## 8. Step F — Reset tracked legacy files and create baseline (legacy only)

This is the destructive section. Execute only after Steps A–E and explicit owner confirmation. `git rm` is recoverable from the verified archive and Git history; it must target tracked repository files only.

Preferred method: remove reviewed top-level legacy paths explicitly, for example:

```powershell
git rm -r -- 'legacy-path-one' 'legacy-path-two'
```

If and only if every tracked path has been classified for full replacement, this broad tracked-file reset may be used:

```powershell
git rm -r -- .
```

That command stages deletion of all tracked working-tree files but preserves `.git`. It is forbidden for the current repository because the rebuilt core already exists. Never pair it with `git clean`, `Remove-Item -Recurse`, or deletion of untracked content.

Create the minimal new baseline through reviewed patches/templates:

```text
.github/workflows/ci.yml
.env.example
.gitattributes
.gitignore
.python-version
README.md
pyproject.toml
uv.lock
docs/
scripts/
src/jarvis/
tests/
```

Baseline requirements:

- Python 3.11 `src/` package and locked `uv` environment;
- modular core contracts and composition root;
- no downloaded model or runtime database;
- safe local defaults in `.env.example`, never credentials;
- ignore rules for secrets, models, runtime state, media, environments, builds;
- unit/integration/contract test skeleton with deterministic fakes;
- Windows CI for format, lint, type, test, dependency and secret checks;
- architecture, security, setup, and roadmap documentation.

Review before commit:

```powershell
git status --short
git diff --stat
git diff --check
git diff --cached --stat
git diff --cached
```

Stage only exact new/changed baseline paths. Avoid `git add -A` in a mixed worktree.

Commit and push only after checks pass:

```powershell
git commit -m 'chore: reset legacy JARVIS implementation'
git push origin main
git status -sb
```

Do not force-push.

## 9. Step G — Validation and fresh-clone proof

For current repository, start here after current-state verification.

Install only required lightweight development tooling according to repository setup, then run:

```powershell
./scripts/bootstrap.ps1
./scripts/quality.ps1
uv run jarvis doctor
git status -sb
```

`doctor` may report Ollama stopped or model missing; it must do so safely and actionably. Planning and ordinary tests must not download a model.

Use a separate explicitly created temporary parent for fresh-clone proof. Verify its resolved path before any later cleanup:

```powershell
$ValidationRoot = Join-Path $env:TEMP 'jarvis-phase0-validation'
New-Item -ItemType Directory -Path $ValidationRoot -ErrorAction Stop
git clone https://github.com/DanCreates1/JARVIS.git (Join-Path $ValidationRoot 'JARVIS')
Set-Location -LiteralPath (Join-Path $ValidationRoot 'JARVIS')
git branch --show-current
git log -1 --oneline
./scripts/bootstrap.ps1
./scripts/quality.ps1
```

Do not recursively delete the validation directory through an unresolved variable. Cleanup is optional; if performed later, resolve and confirm the exact path remains under the intended temp validation parent.

## 10. Step H — Post-push verification

```powershell
git rev-parse HEAD
git ls-remote --heads origin main
git status -sb
git log -3 --oneline --decorate
```

Local and remote `main` SHAs must match. Confirm archive ref again:

```powershell
git ls-remote --heads origin 'refs/heads/archive/*'
```

Record:

- baseline commit SHA and branch;
- archive name and SHA;
- checks run and results;
- files deliberately retained/replaced;
- any unavailable optional check;
- next milestone.

## 11. Current repository Phase 0 checklist

| Requirement | Discovered state | Next-run action |
| --- | --- | --- |
| Correct origin/main | Present | Re-verify |
| Legacy archive | `archive/pre-jarvis-rebuild-2026-08-18` at `465b25f` | Verify remote SHA; do not recreate |
| Reset commit | `d6114c8` | Preserve |
| New secure core | `2cd67b3` before planning commit | Preserve and extend |
| `.gitignore` / `.env.example` | Present | Review only if requirements change |
| Locked dependencies | `uv.lock` present | Run locked validation after `uv` setup |
| CI/tests | Present | Run quality gate |
| Secret/large artifact scan | No obvious tracked suspect found in planning inspection | Run formal scanner when installed |
| Worktree | Clean before planning docs | Ensure only intended implementation changes |

## 12. Phase 0 exit criteria

Phase 0 is done when:

- exact origin, branch, and local/remote SHAs are known;
- clean worktree or every intended change is explicitly classified;
- remote legacy archive is verified and contains no knowingly published secret;
- current modular baseline is present and reproducible;
- CI/quality/secret checks pass or optional-tool absence is documented without hiding failures;
- no model weights, private runtime data, credentials, or unrelated legacy edits are in the diff;
- remote `main` equals the reviewed local commit;
- next work starts from the current core rather than repeating cleanup.

For the repository state discovered on 2026-08-19, Phase 0 should require verification only. The next implementation milestone is Phase 1 text MVP gap closure.
