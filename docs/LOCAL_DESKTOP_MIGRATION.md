# Local Desktop migration — 2026-10-07

Status: **local checkout operational; full migration blocked**. Source removal is withheld because
42 original pytest/cache directories cannot be read. Native mobile verification also has an
unresolved upstream dependency-audit gate. No next Garmin integration phase was started.

## Active paths and commands

- Operational repository: `C:\Users\poyan\Desktop\JARVIS Desktop`
- Connector: `runtime/integrations/garmin/python-garminconnect/` beneath that repository
- Private reports: `runtime/garmin/reports/`
- Private migration evidence and preserved environments: `runtime/migration-20261007/`
- Desktop shortcut: `C:\Users\poyan\Desktop\JARVIS Desktop.lnk`

The shortcut opens a local command terminal through `scripts/open-local.cmd`. It does not start
a server or expose a remote route. The command launcher also works where Windows PowerShell's
script execution policy blocks `.ps1` files. Existing launch scripts already derive their root
from their own location. No existing JARVIS shortcut, scheduled task, or persistent environment
variable referencing the old checkout was found. No JARVIS runtime process needed stopping.

```powershell
Set-Location -LiteralPath 'C:\Users\poyan\Desktop\JARVIS Desktop'
uv run jarvis doctor
uv run jarvis chat
uv run python scripts/garmin_report.py
```

Windows Application Control blocks the installed RTK executable. The owner authorized native
PowerShell/tools for this migration; RTK configuration and Windows security policies were left
unchanged. Historical phase reports retain their original paths and evidence.

## Copy and preservation evidence

The canonical input was `C:\Users\poyan\OneDrive\Desktop\JARVIS`, clean at published commit
`63b9455`. The separate `C:\Users\poyan\Desktop\JARVIS` checkout was at `2bc80b9`, with one
untracked cleanup script. The destination did not exist and its local Desktop parent was not a
reparse point. Hidden files, `.git`, environments, ignored runtime data, reports, and package
caches were included in copies. Existing destination files were not overwritten by the merge.

| Copy | Verification |
| --- | --- |
| Canonical | 98,834 accessible files/links; 7,260,757,351 file bytes; zero SHA-256 mismatches |
| Separate checkout archive | 90,271 files; 5,749,431,243 bytes; zero mismatches; no unreadable directories |
| Upstream Garmin connector | 1,427 files; 25,469,498 bytes; zero mismatches; no unreadable directories |

Canonical counts include 15 historical test junctions, recreated with targets inside the new
local folder. Their original targets and all file hashes remain in private migration evidence.
42 inaccessible directories contain old pytest/cache state; their contents could not be
enumerated or verified. Robocopy recorded canonical exit `11`, separate archive exit `1`,
connector exit `1`, and additive runtime merge exit `3`. Source removal was never attempted.
Ownership/access repair for `.pytest_cache` was also denied; no successful source ACL change
occurred. Both original checkouts remain intact.

The full separate checkout, including its independent `.git`, lives under ignored
`runtime/migration-20261007/separate-checkout/`. Its 81,582 unique files and 2,126 differing files
are indexed in private `preservation-index.json`; newer canonical files were retained. Unique
runtime data was merged additively, and missing `.env`/`.env.local` configuration was copied
without displaying values. Older tracked source files were preserved in the archive rather than
reintroduced into current source. The old automatic deletion script remains an inactive archive
artifact and was not executed or installed as a launcher.

The connector retains nested Git history at `218e72c`, its demo, and private `your_data/` exports.
Nested Git remains clean and passes `git fsck --full`. Canonical Git refs/HEAD matched the copied
repository exactly before new migration changes; outer Git integrity and history secret scan
passed. Existing dangling Git objects were preserved rather than pruned.

## Environment and session repairs

- Core `.venv` and `.bootstrap-venv` rebuilt from unchanged `uv.lock` with official PSF Python
  3.11.9. Their complete moved originals are retained in ignored migration storage.
- `garmin_sync/.venv` rebuilt from its unchanged lockfile with Python 3.12.14. Original preserved.
- Connector `.venv` rebuilt with Python 3.14.7 and all 11 exact existing external package
  versions, plus editable upstream `garminconnect` 0.3.17. Frozen requirements and original
  environment preserved. Imports resolve into the new connector folder.
- Existing home-local voice environment remains in `%LOCALAPPDATA%\JARVIS\voice-venv`.
  Editable Core source now points to the new repository. Full pre-repair environment and original
  editable metadata preserved. Locked voice sync repaired missing `cryptography`, `pillow`,
  `pypdf`, `mypy`, and `tomli` files/packages and aligned `urllib3`; voice/Core imports and audit pass.
- Garmin report discovery now uses the executing repository's connector; `--connector` still
  accepts an explicit location. It no longer silently selects another checkout.

Windows Credential Locker entries and home-directory Garmin token locations were not moved,
deleted, or imported. The saved-session reporter required no new login. Normal upstream session
refresh remains owned by that client. No credentials or private health values were printed or
placed in source control. Private reports, nested repositories, manifests, backups, and generated
artifacts remain ignored.

## Verification and publication boundary

| Gate | Result |
| --- | --- |
| Core lock check / locked sync | Pass; both lockfiles unchanged |
| Ruff format / lint | Pass |
| Mypy | Pass; 164 source files |
| Full pytest | 1,317 passed, 3 skipped, 1 warning; 85.45% coverage |
| Core / bridge / connector / voice dependency audits | Pass; no known vulnerabilities |
| History Gitleaks | Pass; 83 commits scanned before migration commit |
| Git refs / integrity / whitespace | Pass |
| Local Core doctor | Pass with session-only `JARVIS_CLOUD_POLICY=local_only`; existing storage used |
| Desktop command launcher | Pass |
| Saved-session Garmin report | Pass; 10/14 categories available; JSON/Markdown stored privately |
| Native mobile format / lint / types / tests / Doctor / licenses | Pass; 38 tests, Doctor 21/21, 1,109 package licenses |
| Native mobile production audit | Blocked; 15 moderate, 45 high, zero critical after compatible remediation |

Native mobile initially needed four SDK 57 patch alignments. Compatible `npm audit fix` also
removed the critical `shell-quote` finding. The remaining high findings propagate from
`braces` and `node-forge`; current upstream advisories list no patched versions. No forced SDK
downgrade, major upgrade, audit exception, or weakened gate was applied. Mobile dependency
candidate changes remain **local and uncommitted** in `mobile/package.json` and
`mobile/package-lock.json`, with duplicate candidate files and patch under ignored migration
storage. Their publication is withheld pending a passing audit. Full `npm run verify` stops at
that production audit, before its export steps. Core/PWA Garmin acceptance was not advanced.

Only reviewed Core migration source, local launcher, and documentation are eligible for the
standing-authorized commit/push after their required Core gates. The published report explicitly
retains the unresolved source-access and native mobile audit blockers.

## Codex reopening and remaining work

Available Codex tools cannot change the current project's root. In Codex, choose the local-folder
project picker from the Projects sidebar, paste `C:\Users\poyan\Desktop\JARVIS Desktop`, confirm
that exact folder, then start a local chat in that project. This existing chat remains associated
with the original project until the owner reopens
the new folder. The Desktop shortcut opens the correct terminal independently of Codex.

Full closure requires authorized access to the 42 original pytest/cache directories, copying and
hash-verifying their contents, resolving the native mobile audit gate, and rechecking source
changes/processes before deleting the exact canonical source folder. Do not use the archived
automatic cleanup script or delete unrelated OneDrive files. No source removal is authorized by
this report without the original verified-copy and operation prerequisites being satisfied.

Estimated active PWA app completion: **80%**, unchanged. Basis: accepted phone chat/connection,
implemented Garmin panel and standalone reads; protected Core-session, physical-phone Garmin,
recovery, and final acceptance still pending. Migration does not complete those product gates.

References: [Python venv relocation](https://docs.python.org/3/library/venv.html),
[uv locked environments](https://docs.astral.sh/uv/reference/cli/),
[Expo compatibility checks](https://docs.expo.dev/more/expo-cli/),
[braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm),
[node-forge advisory](https://github.com/advisories/GHSA-86w9-cpqp-85rv),
[Codex local folders](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex).
