# Controlled Windows actions

Phase 13 selects the existing trusted-local terminal workflow. Models/chat may propose typed
actions; only exact local review can issue an expiring one-use grant. No remote execute endpoint
or new PWA scope exists. `prototype-text` and other text profiles still disable computer access.

## Selected action set

Choose `"action_set": "controlled-windows"` in the private host policy. This explicitly restricts
registrations even when stale optional printer/browser/app-group configuration remains present.
Hands-free mappings must all be disabled. The backward-compatible default `legacy` retains the
[legacy action contract](CONTROLLED_COMPUTER_ACCESS.md); it is a broader configuration.

| Action | Typed input | Boundary / receipt |
| --- | --- | --- |
| `launch_application` | `{"application_id":"editor"}` | Host-enrolled executable digest/identity and fixed argv; verifies running image, no automatic termination. |
| `set_master_volume` | `{"percent":30}` | Absolute integer 0–100 on default render endpoint; exact prior state, readback and guarded rollback. |
| `control_media` | `{"operation":"stop"}` | Closed previous/next/stop/play-pause/mute key pair; verifies Windows accepted inputs, no playback/mute claim. |
| `move_controlled_file` | `{"source":"inbox/report.txt","destination":"archive/report.txt"}` | One unchanged file within controlled root, same volume, no overwrite; exact identity/hash and guarded rollback. |
| `search_controlled_files` | `{"query":"report","limit":20}` | Bounded filename-only read; no file content or filesystem-wide search. |

All effects require exact approval, including Level 1. Level 3/4, deletion, overwrite, shutdown,
printing, clipboard, browser navigation, app groups, security changes, arbitrary shell and general
UI automation are outside this selected set. No automatic retry or hands-free activation.

## Setup and use

No production policy is changed by repository tests. Configure only a reviewed local data directory.
Use the standard CLI settings for operator commands; text-only profiles intentionally remove the
computer master switch. Cloud/model inference is not invoked by these computer CLI commands.

```powershell
rtk proxy uv run --locked python -m jarvis computer init
rtk proxy uv run --locked python -m jarvis computer status
```

While policy remains disabled, review `computer-access.json` in the configured JARVIS data
directory. Set `action_set` explicitly, enroll exact owned application IDs/digests/fixed argv as
needed, keep hands-free off, and keep the controlled root a dedicated child of that data directory.
Enabling host actions is a separate owner decision. Both the startup master switch
`JARVIS_COMPUTER_ACCESS_ENABLED=true` and enabled private policy remain necessary.

```powershell
rtk proxy uv run --locked python -m jarvis computer enable
rtk proxy uv run --locked python -m jarvis computer catalog
rtk proxy uv run --locked python -m jarvis computer propose move_controlled_file --arguments '{"source":"inbox/report.txt","destination":"archive/report.txt"}'
rtk proxy uv run --locked python -m jarvis computer pending
rtk proxy uv run --locked python -m jarvis computer approve <approval-id>
rtk proxy uv run --locked python -m jarvis computer execute <grant-id>
rtk proxy uv run --locked python -m jarvis computer audit --kind receipts --limit 50
```

Catalog displays fixed JSON input schemas, enrolled aliases, risk, approval, deadlines, result
bounds, postconditions and recovery limits. It creates no identity, database, proposal or grant.
Review shows exact effect/arguments/recovery/identity/expiry/fingerprint. Terminal controls and
directional formatting are escaped visibly; Rich markup stays literal. Type the exact displayed
`APPROVE <fingerprint-suffix>` phrase; any other input denies. Approval alone dispatches nothing.
Local app previews also show the bound executable, fixed argv and digest; file previews show
controlled root, file size and digest. Private fixed argv is read from the hash-bound host policy
for review and is not copied into durable proposal/grant records or audit projections.

Durable grants now bind the complete policy hash as well as its editable version label.
Manual policy edits invalidate old authority across restart even without changing that label.
Policy hashing and target previews preserve exact Unicode code points, including fixed argv;
visually equivalent Unicode forms cannot silently substitute different Windows inputs.
Pre-upgrade grants bound only to the old label fail closed; propose/review again after upgrade.
No migration or automatic grant conversion is needed. Same unchanged policy retains unexpired
authority across normal restart. Consumed grants reject `execute`; inspect audit instead.

## Cancel, kill and recover

```powershell
rtk proxy uv run --locked python -m jarvis computer cancel <grant-id>
rtk proxy uv run --locked python -m jarvis computer disable
```

`cancel` atomically revokes one still-unclaimed same-identity grant. It does not stop a dispatched
native call. Unknown, foreign, consumed or claimed grants never report a successful cancellation.
To deny a pending request, enter anything other than its approval phrase, or let it expire.
`disable` rotates the policy epoch and blocks new dispatch; use sanitized audit even while disabled.
Also turn off the startup master switch before next launch.

Cancellation/timeout after native dispatch can be uncertain: read receipt/postcondition and
reconcile target state before new work. Guarded rollback refuses newer user changes. Restore a
moved file through a fresh exact reverse-move proposal only after inspecting its current identity
and free destination. Never replay an old grant, overwrite a collision, or force a rollback.

Authority/receipts stay in private Core SQLite. Operator audit omits arguments, content, actor
identifiers and raw results. Protect data directory/backups; normal conversation/action retention
still applies. No private content, raw evidence or allowlist identifiers are published to Git.

## Current live acceptance boundary

Automated fixtures move disposable synthetic files under ignored runtime roots; existing
bounded Python subprocess primitive tests remain part of routine verification. Current brokered
app/audio/media acceptance requires a separate owner-approved bounded run. Prepared command:

```powershell
rtk proxy uv run --locked python scripts/phase3-live-smoke.py --action-set controlled-windows --work-dir runtime/phase13-live-owner-01 --acknowledgement 'I AUTHORIZE DISPOSABLE PHASE 13 LIVE HOST EFFECTS' --app-fixture --volume-current-rounded --media-operation stop
```

Run only after exact approval: one enrolled two-second Python fixture; one current rounded volume
write with at most 0.6 percentage-point scalar change and mute unchanged; one global media STOP
key-down/key-up pair, which can stop active playback. Fresh isolated store, fixed arguments,
production coordinator/trusted CLI/broker, sanitized receipts, no persistent owner policy change,
no printer/browser/clipboard/phone effect. Existing work directory refuses overwrite; choose a
new direct runtime child for any separately approved repeat. This command grants no authority itself.

Official Windows contracts rechecked 2026-10-31:
[SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput),
[Endpoint Volume Controls](https://learn.microsoft.com/en-us/windows/win32/coreaudio/endpoint-volume-controls).
Policy/preview exactness follows [Windows filename code-point semantics](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation).
Inserted inputs do not prove recipient/playback state. Endpoint hardware/software controls have
different exclusive-mode behavior. Native calls may outlive cancellation; no elevated service ships.

Current evidence/status: [Phase 13 progress](phase-reports/current/PHASE_13_PROGRESS.md).
Wikimedia authentication blocker, native dependency publication hold and historical evidence remain.
Phone checks **skipped by owner; unverified**; physical/native/mobile MVP/production acceptance
unestablished.
