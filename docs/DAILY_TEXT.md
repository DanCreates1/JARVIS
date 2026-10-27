# Daily text capability contract

Phase 7 selects explicit `daily-text` on the existing Windows Core and authenticated PWA.
One runtime/store/router/permission system; installed `qwen3:1.7b`, temperature 0. Launch:

```powershell
rtk proxy .\scripts\open-daily.cmd
```

Identify the existing process/port owner first. Stop an existing writer normally before starting
another against the same database. The launcher uses the existing configured store, loopback port
and approved private HTTPS route; it changes no route, identity, enrollment or scope.
Open the existing `/app/`, then Settings → Connect existing device. Wait for Live connection ready
and history readiness. Settings identifies the selected model; this does not establish model health.

| Available | Boundary |
| --- | --- |
| Explanations, rewrites, summaries, lists and supplied-text questions | Model-generated text can be wrong; requested constraints are quality targets, never action authority. |
| Follow-ups, saved history, search, rename/pin/archive | Existing exact device ownership, Core persistence and immutable receipts. |
| Current host clock | Existing deterministic validated tool path; model receives no tool schemas. |
| Existing approved-memory retrieval | Existing privacy/provenance controls; no new memory approval or product lifecycle. |

Live external evidence, file uploads, health, email/calendar access, voice/camera/screen capture,
computer actions, task execution and proactivity are unavailable in this profile, even if old
dotenv flags enable them. Private/uncertain context stays local; cloud is disabled and cost remains
hard-capped at $0. Later capability activation requires its current numbered phase and authority.
Laptop must remain on/reachable. Offline shell queues no messages and caches no private content.

Use Cancel reply while pending. After a lost acknowledgement, Retry request checks the original
immutable receipt; do not retype uncertain work. Restart/reconnect retrieves saved history and
interrupts unfinished generation without replay. Model unavailable/invalid reply/timeout states
offer fixed recovery guidance without exposing provider bodies. Check installed Ollama/model on
the laptop, then review request status/history before a new turn. No automatic download, provider
change, generation retry or credential recovery occurs. Logout erases browser state; Core history
uses its existing retention/deletion controls. Offline erase does not prove server revocation.

`prototype-text` and [its original launcher/runbook](PROTOTYPE_TEXT_RUNBOOK.md) retain their
accepted prompt/model and historical **8/10** result. Daily guidance is isolated from that baseline.
The standard profile retains its existing configuration; neither profile enables it implicitly.

Repeat isolated real acceptance (synthetic disposable state, no owner data):

```powershell
rtk proxy uv run --locked python scripts/prototype-acceptance.py --live --profile daily-text
```

All original cases plus [40 frozen additional cases](PHASE_7_CORPUS.json) execute through actual
PWA/auth/Core/SQLite/Ollama. Integration pass is separate from semantic scoring. Targets, failures,
repeated measurements and release status live in [Phase 7 report](phase-reports/current/PHASE_7_COMPLETION.md).
Three final runs score **10/10 original** and **37/40, 37/40, 36/40 additional**, all designated
safety cases passing. Sorting, conversions and physical explanations still have recorded failures;
verify important facts and calculations. This is bounded qualification, not general correctness.
Official [chat API](https://docs.ollama.com/api/chat) and
[thinking controls](https://docs.ollama.com/capabilities/thinking) checked 2026-10-26; actual installed
model/version evidence governs this configuration. No provider/dependency contract was changed.

Phone checks: **skipped by owner; unverified**. Native publication stays held. No physical/mobile
MVP/production acceptance or deployment follows from daily text qualification.
