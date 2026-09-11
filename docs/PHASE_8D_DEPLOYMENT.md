# Phase 8D private phone deployment

Phase 8D uses one Tailscale Serve HTTPS gateway in front of JARVIS. JARVIS remains bound to
`127.0.0.1:8765`. No Windows firewall rule, LAN listener, port forward, Funnel, public endpoint, or
second replica is allowed. Tailnet membership is only the network boundary; Phase 8A-8C device
enrollment, scopes, signatures, cookies, CSRF, origin checks, expiry, and revocation still apply.

## Privacy and authority checkpoint

Tailscale Serve HTTPS publishes the exact node FQDN in public Certificate Transparency logs. Review
the Windows Tailscale machine name before enabling HTTPS; do not use a personal, secret, client, or
location-bearing machine name. `-AcknowledgeCertificateTransparency` records operator awareness;
it does not remove this disclosure.

Review the tailnet policy before deployment. Remove any default allow-all rule. Grant only the
intended identity/device access to the JARVIS host on TCP 443. Do not enable Funnel. Keep the phone
and laptop in the same private tailnet and separately enroll the PWA with JARVIS. The launcher
requires `-AcknowledgePrivateGrant` because the local CLI cannot prove the admin-console policy.

## Install and authenticate

Install the official Windows client, then sign in from the Tailscale tray icon:

```powershell
winget install --id Tailscale.Tailscale --exact
tailscale status
```

Install Tailscale on the physical phone and sign into the same approved tailnet. Do not create or
transfer a reusable Tailscale auth key for this personal deployment.

## Preflight and foreground run

From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\phase8d-private.ps1 `
  -Action Preflight
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\phase8d-private.ps1 `
  -Action Run `
  -AcknowledgeCertificateTransparency `
  -AcknowledgePrivateGrant
```

`-ExecutionPolicy Bypass` applies only to this reviewed repository script process; it does not
change machine or user policy. Review the worktree and script before invoking it.

The launcher derives the exact `https://<node>.<tailnet>.ts.net` origin from live Tailscale status,
sets it only for the JARVIS child process, verifies diagnostics, configures HTTPS Serve only to
`http://127.0.0.1:8765`, and runs JARVIS in the foreground. It refuses missing/offline Tailscale,
non-`.ts.net` DNS, invalid status JSON, public Funnel, non-loopback backend listeners, existing
unowned Serve routes, occupied backend port, invalid port, or failed diagnostics.

Open the printed `/app/` URL on the phone. Create a five-minute minimum-scope ticket locally:

```powershell
uv run jarvis remote enroll "My PWA" `
  --type browser `
  --scope browser.session `
  --scope identity.read `
  --scope events.read `
  --scope session.revoke `
  --scope client.chat `
  --scope client.tasks.read `
  --scope client.status.read `
  --risk-ceiling 1
```

Paste the one-use ticket directly into the phone PWA. Never send it through email, chat, cloud
notes, source control, logs, screenshots, or model context.

## Live acceptance

On the phone, verify installation, device/status/task minimization, one public-fixture chat,
generic notifications, 100 reconnects without gaps/duplicates, and empty API/user-data Cache
Storage. Test Wi-Fi/cellular transitions, Tailscale disconnect/reconnect, laptop JARVIS restart,
offline local erase, and certificate/time failures. Private prompts are not acceptance fixtures.

From Windows, record sanitized evidence only:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\phase8d-private.ps1 `
  -Action Status
uv run jarvis remote devices
Get-NetTCPConnection -State Listen | Where-Object LocalPort -In 80,443,8765
Get-NetFirewallRule -PolicyStore ActiveStore | Where-Object DisplayName -Like "*JARVIS*"
```

External checks must run from an approved tailnet peer and separately from an ordinary LAN/public
peer. Expected: tailnet HTTPS 443 works, app authentication still required, LAN/public JARVIS ports
do not respond, and Ollama/privilege-broker ports are absent.

## Backup and restore rehearsal

Create a private destination outside the repository, then use the no-overwrite online SQLite
backup. It includes all JARVIS data, not only remote identity, and prints its SHA-256 digest plus
`integrity_check: ok` without printing database content:

```powershell
$backupDirectory = Join-Path $env:LOCALAPPDATA "JARVIS\backups"
New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
$backupPath = Join-Path $backupDirectory "jarvis-phase8d.db"
uv run jarvis remote backup $backupPath
```

Keep backup private. Do not attach it to chat, place it in source control, or copy it to
unencrypted cloud storage. Rehearse restore only into an isolated directory: copy backup there as
`jarvis.db`, set `JARVIS_DATA_DIR` for that one process, run `jarvis doctor`, compare the reported
active-device count, then remove isolated rehearsal copy. To restore live data, first stop JARVIS,
preserve current database separately, copy verified backup into place, and run `jarvis doctor`
before enabling Serve. Never overwrite running database.

## Lost-phone revocation

Copy only the exact device ID from local inventory, then revoke locally:

```powershell
uv run jarvis remote devices
uv run jarvis remote revoke DEVICE_ID --confirm-device-id DEVICE_ID
uv run jarvis remote audit DEVICE_ID --after 0 --limit 100
```

The active phone stream and next request must fail within 5 seconds. Remove the phone from the
tailnet through its admin console. Re-enrollment requires a new browser key and new one-use ticket.

## Stop and rollback

Normal `Ctrl+C` runs rollback automatically. If interrupted hard, use:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\phase8d-private.ps1 `
  -Action Stop
```

Stop refuses to alter Serve without a local ownership marker or when any TCP, HTTPS authority, or
handler differs from the exact single route created by the launcher.
Rollback removes only the owned HTTPS Serve route and runtime marker. JARVIS remains loopback-only;
no firewall rule was created. Existing device records remain for audit and can be revoked locally.

## Primary references

- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-funnel/how-to/host-websites)
- [Tailscale Funnel boundary](https://tailscale.com/docs/features/tailscale-funnel)
- [Tailscale grants](https://tailscale.com/docs/features/access-control/grants)
