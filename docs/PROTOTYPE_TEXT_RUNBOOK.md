# Text prototype: one Windows Core

PROTO-2.2 profile/recovery rehearsal, **2026-10-25**. Primary client: authenticated `/app/`; local CLI and
loopback `/` are operator fallbacks. Canonical scope: [Prototype Plan](PROTOTYPE_PLAN.md).
Requires the locked setup in [Windows setup](setup-windows.md), existing Ollama, and the
already-installed `qwen3:1.7b`. No new model download or account is required.

## Launch

Open a terminal in the active checkout:

```powershell
Set-Location -LiteralPath 'C:\Users\poyan\Desktop\JARVIS Desktop'
rtk proxy .\scripts\open-local.cmd
```

The script selects `JARVIS_RUNTIME_PROFILE=prototype-text`, pins the selected installed model
to `qwen3:1.7b`, and runs `rtk proxy uv run --locked python -m jarvis serve` in the foreground.
The module entry avoids dependence on the generated `jarvis.exe` console shim. It uses the
existing configured database and port (default `8765`); it never replaces a store, enrolls a
device, changes a private route, or starts a second server/framework. Before launching, identify
any existing Core process on that port. Its owner must stop it normally before another writer
starts. Ctrl+C stops the foreground process; never kill an unidentified owner process.

Equivalent module launch in PowerShell:

```powershell
$env:JARVIS_RUNTIME_PROFILE = 'prototype-text'
$env:JARVIS_OLLAMA_MODEL = 'qwen3:1.7b'
rtk proxy uv run --locked python -m jarvis serve
```

The opt-in profile forces `local_only`, loopback Core/Ollama and the configured Ollama model.
It disables research (including automatic search), attachments, email/coding/current-context
projections, voice/camera/screen capture, computer actions, task execution, and proactive effects,
including old enabled flags in dotenv. Existing approved-memory retrieval, privacy/policy,
authentication, cost ceiling, receipts, history and request recovery remain active. Unsupported
current-fact questions receive explicit missing-evidence guidance; generated facts are not live
verification. Disabled-research requests settle with a deterministic unavailable-evidence answer,
without model generation. Model generation advertises no tools; the separately validated direct
clock path remains. The profile fixes Ollama temperature to `0`; instruction-following still has
known limits: the unchanged corpus scores **8/10**, failing polite tone and one checklist format.
See [repeat acceptance evidence](PROTO_2_1_EVIDENCE.md). The standard profile retains historical
implementations and its existing default model/sampling.

## Use Chat, then Settings when needed

Open the **existing approved private HTTPS origin** with `/app/`. This guide intentionally
contains no private hostname or ticket. The existing route must already proxy to loopback Core;
do not change Serve/Funnel, bind publicly or weaken TLS. Plain HTTP loopback is an operator
fallback and does not replace authenticated HTTPS PWA access.

1. PWA opens on Chat. Settings holds connection/recovery. Connect existing device with its
   retained authorized browser key. A missing key needs a separately approved chat-only
   enrollment ticket; do not create one as a launch step.
2. Wait for **Live connection ready** and history readiness before Send enables. Settings shows
   `ollama · qwen3:1.7b · local_only` after authenticated status succeeds. This identifies the
   selected configuration; it is not a model-health or quality claim.
3. Ask `What is the time?`, then a short explanation or synthetic checklist. Follow up in the same
   conversation. Library/search, rename/pin/archive, Cancel reply and immutable-request retry
   retain their existing contracts. No optional integration is required in this profile.
4. Use Cancel reply while pending. After a lost acknowledgement, reconnect and let Core check the
   receipt; use Retry request for that immutable turn. Do not retype a duplicate while its outcome
   is uncertain. Start a new request only after the prior request has settled.

## Fallback and recovery

CLI single turn (same profile; synthetic example):

```powershell
rtk proxy .\scripts\open-local.cmd chat --message "Explain a solar eclipse in two sentences, under 60 words."
rtk proxy .\scripts\open-local.cmd doctor
```

Use CLI with an explicit `--conversation-id` to resume a CLI conversation. Device-owned PWA
history keeps its existing ownership boundaries; CLI is not a way to bypass them. Stop the
foreground Core normally before using a separate CLI writer against the same canonical store.

| Visible state | Recovery |
| --- | --- |
| Core unreachable / connection failed | Verify laptop is available, identify the process/port owner, start the text profile, then Settings → Connect existing device. |
| Network offline / reconnecting | Restore the existing private network and laptop connection; reconnect. No offline sends are queued. Cached shell supplies no private transcript. |
| Local model unavailable | Check `rtk proxy ollama list` includes `qwen3:1.7b`; start the installed Ollama app if absent from running processes. If the model is not installed, report it; no automatic download/cloud fallback. |
| Session expired / access denied | Connect existing device to renew. If rejected, use approved trusted-host recovery; do not change origin, scopes or auth controls. |
| Restart / interrupted request | Restart the same profile/store after normal shutdown. Reconnect, recover receipt/history; interrupted work must not be blindly replayed. |
| Live evidence unavailable | This text slice cannot verify external current facts. Ask a stable/supplied-content question; do not treat uncited model output as research. |

Settings → Logout and erase this device uses existing revocation/erase handling. It clears private
UI; it does not delete Core history. Keep databases, keys, tickets and transcripts outside Git.

## Repeat isolated local smoke

```powershell
rtk proxy uv run --locked python scripts/prototype-text-smoke.py --live
```

This historical PROTO-1.2 smoke uses `qwen3:0.6b`. Explicit opt-in contacts only installed loopback
Ollama, builds a disposable real Core/SQLite
store under ignored `runtime/proto12/`, checks deterministic clock against host time, streams C1
and F1 from the [frozen corpus](PROTOTYPE_CORPUS.md), checks persisted context, and runs the CLI
launcher against another synthetic store. It never copies owner data or enrolls an identity.
Keep generated evidence ignored. A smoke pass proves this slice runs; full corpus, ten warm
timings and real authenticated browser/Core/model acceptance belong to **PROTO-2.1**.

Repeat the selected configuration's full real browser/Core/model acceptance:

```powershell
rtk proxy uv run --locked python scripts/prototype-acceptance.py --live
```

Default model is `qwen3:1.7b`. Results distinguish integration success from the separate frozen
semantic rubric. Temporary HTTPS certificates, fixture identities and synthetic data stay under
ignored `runtime/proto21/`; no owner database, production enrollment or route change is used.

Manual phone checks remain **skipped by owner; unverified**. This is neither physical acceptance,
full mobile MVP completion, nor production readiness.

## Acceptance receipt and known limits

[PROTO-2.2 receipt](PROTO_2_2_EVIDENCE.md) records exact launcher doctor/chat/foreground startup,
disposable restart with saved messages, and repeated authenticated browser/Core/SQLite/Ollama
recovery. Repeat `prototype-acceptance.py --live` only against its disposable fixtures; it must
never copy owner state or reset a real store. Synthetic fixture enrollment is not production
enrollment authority. Use existing backup/recovery contracts for real data; this rehearsal does
not validate restoration of the owner's database.

Selected installed `qwen3:1.7b`, Ollama 0.40.8 and temperature 0 repeat **8/10** on the unchanged
ten-case corpus. Polite rewrite tone and one three-item checklist format still fail. Current-fact
verification remains unavailable with research disabled. Readiness identifies configuration,
not general model competence. No cloud fallback, automatic model download, integration activation,
deployment or next phase follows from this receipt.
