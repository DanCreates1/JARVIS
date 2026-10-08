# Local Garmin connector and batch reports

Updated: 2026-10-07. Status: local Desktop migration; Core/PWA acceptance pending.

## Organized local files

On 2026-10-05 the owner-added connector was organized inside the separate Desktop checkout.
On 2026-10-07 it was copied into `C:\Users\poyan\Desktop\JARVIS Desktop` under ignored
`runtime/integrations/garmin/python-garminconnect/`. The upstream Git history, original
environment, interactive menu, and private `your_data/` exports were preserved. Its active
environment was rebuilt with the exact existing package versions to repair moved paths; originals
remain under ignored `runtime/migration-20261007/`. See [local migration](LOCAL_DESKTOP_MIGRATION.md).
No account identifier, credential, token, export, or upstream nested repository was added to
JARVIS Git.

The imported upstream source identifies itself as `garminconnect` 0.3.17. Its existing environment
uses Python 3.14.7; the environment still imports the moved source successfully. This remains
separate from JARVIS Core and the existing pinned Python 3.12 `garmin_sync` bridge. No Core
dependency or bridge version was changed.

The interactive menu still runs from the moved upstream folder:

```powershell
Set-Location -LiteralPath 'C:\Users\poyan\Desktop\JARVIS Desktop\runtime\integrations\garmin\python-garminconnect'
.\.venv\Scripts\python.exe .\demo.py
```

This menu includes mutations. The JARVIS batch reporter executes its own fixed read allowlist;
it does not automate the menu. Upstream reference:
[python-garminconnect](https://github.com/cyberjunky/python-garminconnect).

## One-command report

Run from the active local Desktop checkout. The owner authorized native tools for this migration
because Windows Application Control blocks RTK; no Windows security policy was changed.

```powershell
Set-Location -LiteralPath 'C:\Users\poyan\Desktop\JARVIS Desktop'
uv run python scripts/garmin_report.py
```

Optional historical date or explicit connector location:

```powershell
uv run python scripts/garmin_report.py --date 2026-10-04 --connector "C:\Users\poyan\Desktop\JARVIS Desktop\runtime\integrations\garmin\python-garminconnect"
```

The launcher looks only under the current checkout's `runtime/integrations/garmin/`.
`--connector` overrides discovery. It launches the connector's existing Python in a bounded
child process, with a 180-second timeout and no stdin.
Credentials are never prompted for or passed; unrelated environment secrets are excluded from
the child process. The saved session uses `GARMINTOKENS` when set,
otherwise `~/.garminconnect`; `--token-store` can specify an existing local token directory.
If the session needs fresh authentication, the report fails with a sanitized error; reconnect
only through the trusted local demo. Normal session refresh remains managed by the upstream client.

One invocation attempts these 14 categories: daily totals, heart rate, sleep, stress, Body Battery,
HRV, training readiness, respiration, SpO2, intensity minutes, hydration, body composition,
VO2 max, and three recent activities. Missing device features, empty responses, unavailable
endpoints, or unmapped values remain explicit. Rate limiting stops further category reads.
Recent activities are the latest three, not a historical-date activity query.

Only bounded, explicitly mapped metrics leave the child process. Account/profile data, IDs,
GPS coordinates, raw responses, activity names, and detailed time series are omitted. These are
supported aggregate health categories, not a complete account archive or all demo options.

Both a readable Markdown report and machine-readable JSON report are saved with unique names
under ignored `runtime/garmin/reports/` in the current checkout. Reports contain private health
values: keep them local, never commit them or paste them into a cloud chat. No health report is
automatically sent to JARVIS chat, a model provider, or the phone API. Report files use the existing
local runtime boundary; disconnecting Garmin does not remove previously generated local reports.

## Historical 2026-10-05 evidence and next gate

- Connector move and environment import passed; demo remains unchanged.
- Owner-requested saved-session reads produced reports with mapped values in 11/14 categories.
  Training readiness returned no data; intensity and body composition had no supported mapped
  values. No private values were placed in this document or test fixtures.
- Focused tests exercise filtering, malformed/oversized values, partial data, total failure,
  rate-limit stopping, and unique report files.
- Verification: 18 focused tests passed; full suite 1,317 passed / 3 skipped, with 85.44%
  coverage. Lock check, locked sync, Ruff format/lint, Mypy (164 source files), Core and connector
  dependency audits, staged/history secret scans, and whitespace checks passed.
  Windows Application Control blocked the `mypy`, `pytest`, and `pip-audit` entry-point
  executables. Allowed `uv run python -m ...` invocations completed the locked-environment
  checks after restoring missing `cryptography`, `mypy`, and `tomli` files with
  `uv sync --locked --reinstall-package cryptography --reinstall-package mypy --reinstall-package tomli`;
  no dependency version changed. Pytest cache used
  ignored `runtime/` to avoid the existing cache-directory permission issue.

Estimated active PWA app completion: **80%**. Basis: phone chat/connection already accepted,
Garmin panel and local read/report implemented; protected Core session and physical-phone Garmin,
recovery, and final polish acceptance remain. This is an engineering estimate, not a passed gate.

Next work: **MVP 3 — PWA Garmin integration and acceptance**. Review compatibility of the owner's
saved 0.3.17 session with the existing Core bridge, choose a protected token import/re-login path,
then prove the Core summary and phone refresh. The report is a standalone local diagnostic,
not completed Core integration. New enrollment tickets, credential changes, and any new login/MFA
require fresh owner authority. Follow [PWA Garmin acceptance](PWA_GARMIN.md); native M2C remains
deferred under the existing $0/no-Mac constraint.

M3A review on 2026-10-07 found the 0.3.17 saved JSON session format compatible with the pinned
0.3.16 Core bridge. A strict offline `import-session` path and synthetic security/lifecycle checks
are now prepared; see [MVP 3 progress](phase-reports/PWA_MVP3_PROGRESS.md) and
[protected import instructions](PWA_GARMIN.md). No real token was read or imported, no live Garmin
request was made, and no new phone ticket was issued. Do not run the standalone reporter and Core
against independent session copies after import: refresh rotation can make copies diverge.
