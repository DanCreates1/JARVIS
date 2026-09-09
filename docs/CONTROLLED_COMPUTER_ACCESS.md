# Controlled Computer Access

Phase 3 adds narrow Windows actions behind a host-owned policy, exact trusted approval, expiring
one-use grants, a fixed local broker, postcondition checks, recovery where safe, and sanitized
audit views. It does not add a shell, arbitrary executable paths, implicit elevation, remote
approval, or general UI automation.

## Default state and trust boundary

Computer access is disabled unless both independent gates are active:

1. `JARVIS_COMPUTER_ACCESS_ENABLED=true` in the startup environment.
2. `%LOCALAPPDATA%\JARVIS\computer-access.json` exists, validates, and has `"enabled": true`.

The model and chat UI can request a typed action only. They cannot approve a request, mint a grant,
call the Windows adapter, or treat conversational text such as “yes” as approval. Approval happens
only in the authenticated local terminal. Execution uses a separate short-lived grant and the
broker re-reads the complete policy fingerprint immediately before dispatch.

`jarvis computer disable` rotates the policy authority epoch. Previously approved grants therefore
stay invalid after later re-enablement. The environment switch is a startup gate; use the policy
command for the live kill path.

## Permission levels

| Level | Meaning | Phase 3 behavior |
| --- | --- | --- |
| 0 | Authenticated, bounded read | Allowed only for registered local read tools; private results are local-model-only. |
| 1 | Low-risk reversible/control action | Exact local approval in the shipped policy engine. Acoustic input can only create a proposal. |
| 2 | Meaningful reversible or external effect | Exact local approval for every operation. |
| 3 | Sensitive/destructive | Contract requires recent authentication plus exact approval; no Phase 3 policy or handler enables it. |
| 4 | Administrative/critical | Always denied. No elevation service exists. |

Model confidence never changes a level. A grant binds the action ID/version, canonical arguments,
precondition, actor, Windows session/device, interface, capabilities, policy version, approval ID,
nonce, idempotency key, and expiry.

## Shipped actions

| Action | Level | Fixed boundary | Verification and recovery |
| --- | ---: | --- | --- |
| `search_controlled_files` | 0 | Filenames only beneath one controlled root | Bounded count/depth/time and 400-byte relative paths; computed result cap remains below 100 KiB; no file content. |
| `get_local_printer_status` | 0 | Enrolled printer aliases only | Queue discovery/status; no job. |
| `launch_application` | 1 | Enrolled `.exe`, SHA-256, file identity, and fixed argv | Running image identity checked; no automatic termination. |
| `launch_app_group` | 1 | Ordered group of at most eight enrolled apps | Every launched image checked; partial launch is explicit and not auto-terminated. |
| `control_media` | 1 | One fixed previous/next/stop/play-pause/volume-mute key pair | Verifies Windows accepted both inputs; playback or mute state is not observable. No retry. |
| `set_master_volume` | 1 | Absolute integer 0–100% | Core Audio readback; guarded restoration of prior scalar/mute state. |
| `set_clipboard_text` | 2 | Exact bounded Unicode text | Hash/length readback; a nonempty prior clipboard must expose materialized `CF_UNICODETEXT`, otherwise replacement is refused to prevent lossy rollback. |
| `move_controlled_file` | 2 | One file, same volume, no overwrite, controlled root only | File ID/hash/path revalidation; guarded rename rollback. |
| `open_browser_target` | 2 | Enrolled browser and exact configured public HTTPS target | Browser image identity checked; navigation success is not observable. |
| `print_controlled_text` | 2 | Whole single-link, online enrolled `.txt` file; printer alias; bounded copies | Hardlinked/offline/recall sources are refused; Windows spool acceptance only; fixed `TEXT` datatype, no RAW/PJL/PostScript; no automatic job recall. |

All tools declare a schema, risk, approval rule, timeout of at most 30 seconds, result cap of at most
100 KiB, retry/idempotency rule, concurrency rule, postcondition, and recovery limit.

## Hands-free proposal capability

| Typed detector intent | Fixed proposal | Current detector state |
| --- | --- | --- |
| Phase 2 double clap | `launch_app_group` with only the configured `hands_free_app_group` | Double-clap detector exists; continuous listening remains disabled. |
| `volume_up` / `volume_down` | `set_master_volume` from injected current state, exactly +/-5 percentage points, clamped to 0-100 | Synthetic mapping tests only; default off. |
| `media_play_pause` | `control_media` with `play_pause` | Synthetic mapping tests only; default off. |
| `mute_toggle` | `control_media` with the fixed Windows volume-mute key | Phase 7C maps pinch synthetically; default off; mute state is not observable through `SendInput`. |
| `media_previous_track` / `media_next_track` | `control_media` with track navigation only | Synthetic mapping tests only; default off; browser-tab navigation deferred. |
| `cancel` | Bound-session cancel directive with no action, approval, or grant | Synthetic mapping tests only; default off. |

The Phase 3 mapping contract has no detector-supplied action ID, path, media operation, or numeric
delta. Phase 7C fixes fist/palm/pinch/roll observations to cancel/play-pause/mute-toggle/volume-step
intents before this boundary. It applies actor, source, source-session, freshness, confidence,
replay, rate, and permission checks before producing a proposal. The production consumer can call only
`ActionCoordinator.propose` with `ApprovalSource.HANDS_FREE`; it has no review or execute method.
No audio or camera listener starts when this mapping layer is constructed.

## Setup

Initialize a disabled policy and dedicated root:

```powershell
uv run jarvis computer init
uv run jarvis computer status
```

Review `%LOCALAPPDATA%\JARVIS\computer-access.json` while it remains disabled. Enroll only exact
targets you own:

- `applications`: stable IDs mapped to absolute `.exe` paths, lowercase SHA-256 digests, and fixed
  argument arrays. Obtain a digest with `Get-FileHash -Algorithm SHA256 <path>`.
- `app_groups`: ordered stable application IDs, maximum eight.
- `browser_targets`: stable IDs mapped to credential-free public `https://` URLs. Set one enrolled
  `browser_application` ID.
- `printers`: stable aliases mapped to exact Windows queue names. Sensitive printing remains false.
- `hands_free_app_group`: optional existing double-clap mapping to one configured app group.
- `hands_free_mappings`: five closed, default-false action-family opt-ins for 5% volume steps, media
  play/pause, mute toggle, media track navigation, and bound-session cancel. These flags do not
  install or start a gesture detector.
- `controlled_root`: the dedicated child directory created beneath the JARVIS data directory. The
  loader rejects another root, a symlink, or a reparse redirect.
- `maximum_permission_level`: `1` or `2`. Values `3` and `4` are rejected in Phase 3.

Then enable the reviewed file and the separate startup gate:

```powershell
uv run jarvis computer enable
# Set JARVIS_COMPUTER_ACCESS_ENABLED=true in .env, then restart JARVIS.
uv run jarvis computer status
uv run jarvis doctor
```

`computer enable` refuses an absent policy. Each enable/disable rotates the authority epoch, so an
old pending request or grant cannot revive.

## Proposal, approval, and execution

Chat can create a pending exact proposal when the local model selects a registered action. The
terminal can also create one directly:

```powershell
uv run jarvis computer propose set_master_volume --arguments '{"percent": 30}'
uv run jarvis computer pending
uv run jarvis computer approve <approval-id>
uv run jarvis computer execute <grant-id>
uv run jarvis computer audit --kind all --limit 50
```

The approval command displays exact arguments, effect, risk, recovery limit, actor/session/device,
expiry, and fingerprint. It accepts only `APPROVE <fingerprint-suffix>`. Any other input records a
denial. Approval and execution are separate commands; grants expire and are consumed once.

Other exact argument shapes:

```json
{"application_id":"editor"}
{"group_id":"work"}
{"operation":"stop"}
{"text":"exact clipboard text"}
{"source":"inbox/report.txt","destination":"archive/report.txt"}
{"target_id":"documentation"}
{"query":"report","limit":20}
{"printer_id":"office"}
{"file":"approved-note.txt","printer_id":"office","copies":1}
```

IDs and paths are policy-relative selections, never arbitrary executable or printer command text.

## Audit, privacy, and retention

`computer audit` has bounded `all`, `lifecycle`, `receipts`, and `events` views. Lifecycle entries
cover proposal, approval/denial/expiry, grant issue/claim/revoke/expiry, broker rejection,
execution, cancellation, verification outcome, and rollback. Operator views omit canonical
arguments, model output, clipboard/file/print content, actor identifiers, fingerprints, and raw
adapter results.

Exact pending authority must remain in the private SQLite database until execution or expiry so a
short-lived approved grant can survive a normal process restart. Clipboard recovery plaintext is
never captured during proposal/approval and is volatile after dispatch. Conversation/action data
stays under the configured JARVIS data directory, outside Git; protect that Windows profile and
backups as private data. Removing the JARVIS database deletes its durable action history together
with conversation history; make an authorized backup first if audit retention is required.

Private/unknown tool schemas, including host-owned allowlist identifiers, are removed before a
cloud-provider request. Private computer tools cannot run on a cloud-routed model turn. Audit failures before dispatch stop
the effect. Errors are reduced to fixed codes and bounded summaries; adapter exception text is not
returned.

## Kill, cancellation, and recovery

```powershell
uv run jarvis computer disable
```

This invalidates pending/active authority immediately for running brokers. Also set
`JARVIS_COMPUTER_ACCESS_ENABLED=false` before the next startup. Wrong approval text records a denial;
otherwise pending requests expire without execution.

Rollback is conditional, never forced over newer user/application changes:

- file move restores only the same unchanged file ID/content and only if the original path is free;
- volume restores only while the current scalar/mute still matches this action;
- clipboard restores only while its current hash matches and volatile prior text remains;
- app/browser/media/print effects have no safe generic inverse.

A cancellation before dispatch causes zero effect. Cancellation or timeout after a blocking native
call begins can be uncertain because Windows does not provide a universal way to stop an in-flight
Core Audio, input, process, clipboard, rename, or spool call. The broker records `unknown` evidence
and manual-recovery status rather than claiming no effect. Inspect the receipt and live target.
Printing may already be accepted by the spooler; queue cancellation is manual and may be too late.

## Windows implementation limits

- Runs as the current non-elevated user. Elevated execution is rejected; no UAC prompt or service
  is provided.
- Global media input uses `SendInput` and is subject to Windows UIPI. Input acceptance does not
  identify a recipient or prove playback state.
- Master volume controls the default console render endpoint. Exclusive-mode applications can
  behave differently.
- Windows clipboard is shared across applications. Another application can change it at any time;
  guarded rollback then refuses.
- `TEXT` printing depends on the installed print processor, driver, default font, queue, paper, and
  device. Spool acceptance is not proof of physical output.
- Browser launch proves enrolled process identity, not page load, DNS result, or rendered content.
- General UI automation, screen scraping, arbitrary keystrokes, shell execution, recursive file
  mutation, overwrite/delete, admin/security changes, purchases, and communications are absent.

Primary Windows references:

- [Endpoint Volume Controls](https://learn.microsoft.com/en-us/windows/win32/coreaudio/endpoint-volume-controls)
- [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)
- [About the Clipboard](https://learn.microsoft.com/en-us/windows/win32/dataxchg/about-the-clipboard)
- [TEXT print data type](https://learn.microsoft.com/en-us/windows-hardware/drivers/print/text-data-type)
- [GetFinalPathNameByHandleW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew)
