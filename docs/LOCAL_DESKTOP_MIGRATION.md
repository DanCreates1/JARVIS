# Local Desktop migration — 2026-10-07

Status: **data migration verified; empty old source folder removal pending**. All 42 blocked
pytest/cache trees were repaired, copied, and hash-verified. Complete original source and Git
history remain preserved privately in the destination. All old source contents were removed;
only its empty root remains locked by another process. Native mobile release verification has
an independent upstream dependency-audit blocker. No next Garmin integration phase was started.

## Active paths and commands

- Operational repository: `C:\Users\poyan\Desktop\JARVIS Desktop`
- Connector: `runtime/integrations/garmin/python-garminconnect/` beneath that repository
- Private reports: `runtime/garmin/reports/`
- Initial private migration evidence and preserved environments: `runtime/migration-20261007/`
- Final preservation archive and cleanup evidence: `runtime/migration-cleanup-20261007/`
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

| Initial copy | Verification |
| --- | --- |
| Canonical | 98,834 accessible files/links; 7,260,757,351 file bytes; zero SHA-256 mismatches |
| Separate checkout archive | 90,271 files; 5,749,431,243 bytes; zero mismatches; no unreadable directories |
| Upstream Garmin connector | 1,427 files; 25,469,498 bytes; zero mismatches; no unreadable directories |

Canonical counts include 15 historical test junctions, recreated with targets inside the new
local folder. Their original targets and all file hashes remain in private migration evidence.
The initial copy could not enumerate 42 pytest/cache directories. Initial Robocopy recorded
canonical exit `11`, separate archive exit `1`, connector exit `1`, and additive runtime merge
exit `3`. Initial ownership repair failed under the ordinary Windows token; source was retained.

Final cleanup used an owner-approved Windows UAC helper scoped to those exact 42 trees. It
visited 13,902 objects and changed 6,089 ACL objects, preserving other access entries. Zero
reparse points were encountered. All source directories then became readable. See Microsoft
[takeown](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/takeown)
and [icacls](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls).
Private ACL snapshots, repair receipt, logs, and scripts remain under
`runtime/migration-cleanup-20261007/`.

The recovered trees contain **6,527 files / 2,457,896,948 bytes**. Their contents were merged additively into
matching destination paths; existing destination files were retained. All 6,527 recovered files
match their destination SHA-256 hashes; zero destination conflicts and zero unpreserved files
remain. Every recovered file is also verified in the complete final source archive.

A fresh complete source archive lives at
`runtime/migration-cleanup-20261007/canonical-source-final/`, including hidden files, original
environments, runtime data, and original `.git`. Final Robocopy exit was `1`. All 15 historical
test junctions point inside this archive. Two expired internal Codex refs from the initial
snapshot were recovered from the earlier verified Git copy and independently hash-verified.

| Final preservation gate | Result |
| --- | --- |
| Source at final verification | 105,348 files / 15 junctions |
| Complete archive, including historical refs | 105,350 files / 9,718,659,476 bytes |
| SHA-256 mismatches / unreadable directories / missing directories | 0 / 0 / 0 |
| Changed original file bytes / unpreserved original entries | 0 / 0 |
| Source inventory changed during verification | No |

After preservation, Core quality/security gates, local operation, clean source Git, and source
writer checks passed, all contents of the exact obsolete canonical source were removed. All
15 old test junctions were unlinked without traversing targets. The root
`C:\Users\poyan\OneDrive\Desktop\JARVIS` remains present with **zero children**. Windows
refuses its nonrecursive removal because it is being used by another process. The lock owner
remains unidentified. A read-only diagnostic using signed Microsoft Handle was canceled at
Windows UAC; elevation was not retried, and no handle was forcibly closed. The removal receipt
records `SourceContentsRemoved: true`
and `SourceRemoved: false`; it does not claim full folder removal. The separate
`C:\Users\poyan\Desktop\JARVIS` checkout remains intact.

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
| History Gitleaks | Pass; 84 commits scanned before cleanup publication |
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

Initial reviewed migration source and launcher were published as `6e8045d`. Cleanup documentation
is eligible for publication under the same standing authorization after all nine required Core
gates passed. Fresh verification again passed 1,317 tests, 3 skips, and 85.45% coverage. Local doctor,
Core/connector Git integrity, connector imports, and Desktop shortcut checks passed. Fresh
evidence remains under `runtime/migration-cleanup-20261007/core-gates-0249/` and its parent.

Fresh native production audit still reports 15 moderate, 45 high, and zero critical findings.
Both upstream advisories still have no patched release. This blocks native release verification
and publication of the mobile dependency candidates. Those exact candidates and backups remain
in the migrated destination. This independent native product blocker does not prevent data
migration cleanup, whose preservation and Core-operation gates passed. The remaining migration
blocker is the empty source-root lock. Cleanup does not advance native or PWA Garmin acceptance.

## Codex reopening and remaining work

This chat remains associated with the former source project. Available Codex tools cannot
change its root. The Desktop shortcut opens the correct destination terminal independently of
Codex; reopen the new folder through the Projects sidebar before resuming repository work.

Data preservation and removal of old source contents are complete. Final folder cleanup requires
releasing the lock on the empty old root. Reopen the destination and restart Codex as follows:

1. In Codex's Projects sidebar, open the local-folder project picker, paste
   `C:\Users\poyan\Desktop\JARVIS Desktop`, and confirm that exact folder.
2. Save current work and close chats, terminals, and editors still associated with the old
   source directory. If the folder remains locked, exit Codex completely and restart it, then
   open a local chat in the destination project.
3. From a new PowerShell window outside the old source, run the command below. It verifies the
   exact path and emptiness, then removes only that empty folder without recursion. Cloud-sync
   metadata is allowed; junctions and symbolic links are refused.

```powershell
Set-Location -LiteralPath 'C:\Users\poyan\Desktop\JARVIS Desktop'
$migrationOldSource = 'C:\Users\poyan\OneDrive\Desktop\JARVIS'
if (Test-Path -LiteralPath $migrationOldSource) {
    $migrationResolved = (Resolve-Path -LiteralPath $migrationOldSource -ErrorAction Stop).ProviderPath
    if ($migrationResolved -ne $migrationOldSource) { throw 'Unexpected source path.' }
    $migrationItem = Get-Item -LiteralPath $migrationOldSource -Force -ErrorAction Stop
    if (-not $migrationItem.PSIsContainer -or $migrationItem.LinkType -or
        $migrationItem.LinkTarget -or $migrationItem.Target) {
        throw 'Source root redirects elsewhere or is not a directory.'
    }
    if (@(Get-ChildItem -LiteralPath $migrationOldSource -Force -ErrorAction Stop).Count -ne 0) {
        throw 'Source root is no longer empty; stop and preserve new contents.'
    }
    Remove-Item -LiteralPath $migrationOldSource -Force -ErrorAction Stop
}
```

If Windows still reports that another process uses the folder, retain the empty root and
identify its owner before retrying. Do not use recursive deletion or forcibly close handles.
Once the folder is absent, update the private removal receipt and this report; until then,
complete folder removal remains unverified. The archived automatic deletion script was never
used. Original configuration, independent checkout, Credential Locker entries, home Garmin
tokens, and private exports remain preserved. Native audit remediation is separate maintenance;
no next Garmin integration phase is authorized or started by this cleanup.

Estimated active PWA app completion: **80%**, unchanged. Basis: accepted phone chat/connection,
implemented Garmin panel and standalone reads; protected Core-session, physical-phone Garmin,
recovery, and final acceptance still pending. Migration does not complete those product gates.

References: [Python venv relocation](https://docs.python.org/3/library/venv.html),
[uv locked environments](https://docs.astral.sh/uv/reference/cli/),
[Expo compatibility checks](https://docs.expo.dev/more/expo-cli/),
[braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm),
[node-forge advisory](https://github.com/advisories/GHSA-86w9-cpqp-85rv),
[Codex local folders](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex).
