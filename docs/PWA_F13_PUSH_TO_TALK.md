# Proposed F13 — PWA push-to-talk

Status: **planning complete; implementation not started**, 2026-10-17.
Baseline: `7517e6a` on `main`; F12 complete within repository/automated scope, shell **v9**.
Scope of this session: inspect, design, document and publish safe planning changes only.

## Result to build

Chat gains an explicit microphone control. The user records a short foreground clip, Core
transcribes it locally, and the user reviews/edits the resulting draft before using existing
**Send**. Existing Core chat handles routing, approvals, streaming, history, retry and cancellation.
Transcribing never submits chat, invokes a tool or creates a conversation.

F13 adds optional input capability; it does not change the basic mobile MVP definition or establish
physical acceptance. Estimated active PWA completion stays **94%**, based on implemented/verified
milestones. A plan and skipped checks earn no implementation or acceptance credit.

## Observed prerequisites

- F12 preserves one session/stream/request/conversation across Chat / Garmin / Settings. Reuse
  those owners and generation guards. See [F12 evidence](phase-reports/PWA_F12_COMPLETION.md).
- `src/jarvis/voice/` already defines `AudioClip`, `STTProvider`, `VADProvider`, local CPU/int8
  `FasterWhisperSTTProvider`, `SileroVADProvider` and persistent `VoiceSettingsFile` software kill.
  STT uses `local_files_only=True`; its mono input must actually be 16,000 Hz for this adapter.
- `build_voice_runtime` constructs another Core plus desktop audio and TTS. Do not call it from
  the PWA server. Compose a transcription-only service into the existing web runtime lifecycle.
- `web.py` authenticates versioned requests, checks origin/CSRF/scopes, bounds bodies to **1 MiB**,
  and marks APIs `no-store`. The PWA currently sends `microphone=()` in Permissions Policy.
- Read-only root-environment inventory: Python **3.11.9**, Node **24.20.0**, uv **0.12.15**;
  NumPy importable, faster-whisper/Silero/sounddevice absent. Existing locked `voice` extra can
  supply adapters; inventory does not prove model-cache readiness. No install/download ran here.
- Native `mobile/package.json` and `mobile/package-lock.json` remain dirty, held and unpublished.
  SHA-256 matches F12 evidence: `f1f34cd63792e55bd4db5293d3e9189eac0470d7a8fc81c58dbd895cf89796c4`
  and `acd08d9aa861f1f047b868a49889f3b8f04041539028f7c5ad793b5c2a66bf57`, respectively.

## User interaction and ownership

1. Connected Chat offers **Record message**, **Stop recording** and **Discard recording** with
   clear idle/requesting-permission/recording/transcribing/error status. Start/stop are ordinary
   tap/click/Enter/Space controls; no timed hold gesture is required. Escape discards active capture.
2. Only deliberate Record requests microphone access. Page load, connection, navigation, history,
   reconnect and visibility restoration never request permission or start/resume recording.
3. Recording shows a persistent indicator and elapsed time. Stop closes microphone tracks before
   upload; Discard sends no audio. Reaching the hard duration limit stops capture and follows the
   same transcription path. Denial, unavailable audio, silence and errors leave text input usable.
4. Record starts only with an empty composer, no pending/uncertain chat request and no other voice
   operation. Keep the composer read-only until completion/cancel so a late transcript cannot
   overwrite typing. Bind capture to session generation, conversation, operation and composer
   revision; never merge into an unrelated draft or silently truncate an oversized transcript.
5. Leaving Chat, changing conversation, pagehide, document hiding, offline transition, session
   expiry, logout, track loss or audio-context interruption stops/discards capture and invalidates
   outstanding results. Abort uploads where possible; never upload/retry automatically on resume.
   Late permission resolution must stop every returned track immediately after cancellation.
6. A successful current result fills the memory-only composer and announces **Review transcript,
   then Send**. The existing explicit Send owns submission/idempotency. Capture/transcription
   cancellation is separate from existing **Cancel reply** and **Retry request** behavior.

## Capture and transport contract

Use dependency-free `getUserMedia({audio: ..., video: false})` and a same-origin AudioWorklet.
Produce canonical **16,000 Hz, mono, signed 16-bit little-endian PCM**. Request a 16,000 Hz audio
context, inspect the actual rate, and use bounded Web Audio resampling if necessary. Never merely
relabel 44,100/48,000 Hz samples. If a validated capture path is unavailable, offer text fallback.
The graph must never monitor captured sound through speakers. Bound worklet messages/buffers and
stop tracks, disconnect nodes, close context/ports and release buffers on every exit.

Proposed endpoint: `POST /api/v1/client/voice/transcriptions`, binary
`Content-Type: application/octet-stream`; the fixed endpoint contract defines PCM format. No
multipart parser, arbitrary media decoder, URLs, filenames, base64 or uploaded format selection.
Return bounded JSON containing final `text` and `duration_ms`, with `Cache-Control: no-store`.
Render text as text, never HTML. Cap final text at the existing chat input limit.

Freeze these initial ceilings before implementation tests:

| Resource | Proposed bound |
| --- | --- |
| Clip duration | 120–30,000 ms; lower configured capture limit also applies |
| PCM body | 3,840–960,000 bytes; even length and sample-derived duration checked server-side |
| Existing global body ceiling | **1,048,576 bytes**, unchanged; voice route has the tighter cap |
| Permission wait | 30 seconds; cancel logically and clean up any late stream |
| Voice upload/read deadline | 15 seconds, including middleware body collection |
| Local STT response deadline | Existing configured timeout, capped at 90 seconds for PWA |
| Processing capacity | One host PWA transcription at a time; reject busy work, no waiting queue |
| Abuse limit | At most six transcription starts/minute per authenticated device, plus existing limits |

Apply route-specific body/deadline limits before unbounded accumulation; current middleware reads
bodies before authentication. Retain its global cap and signed-body validation. Protect upload
admission as well as inference; no alternate unauthenticated upload route. Validate size/shape,
identity and scope before speech adapters run. Reject duplicate/invalid length headers, odd/empty
PCM, excess streamed bytes, slow upload, wrong content type and unsupported methods.

## Core controls, privacy and cancellation

- Add a default-off PWA voice configuration gate and read-only authenticated availability
  metadata. Require that gate, existing software voice enable/kill state, healthy local adapters
  and `client.chat`. An unreadable control file fails closed. No new scope, enrollment or remote
  voice-enable endpoint. The PWA cannot change host controls.
- Change only the enabled PWA document's Permissions Policy to `microphone=(self)`; keep camera
  and geolocation denied and legacy pages denied. Keep CSP same-origin, framing denied, no inline
  scripts/eval/blob worklet. Browser consent remains required. Default-off rollout must retain
  `microphone=()`; cached shell content must not defeat the current disabled policy.
- Reuse authenticated cookie/CSRF/origin handling and existing signed identity checks; require
  `client.chat` explicitly in route mapping. Test missing scope, revoked/expired identity,
  cross-origin, missing/duplicate CSRF and mixed credentials before processing any audio.
- Reuse STT/VAD ports with test injection and lazy optional imports. Missing dependencies/model,
  disabled controls or failed readiness produce a safe unavailable state; text service must boot
  and remain usable. Preserve default language/model configuration and local-only model loading.
  Runtime requests never install packages, download weights or fall back to cloud speech.
- Revalidate identity and software kill before processing, during long work and before returning
  text. Cancellation/disconnect/revocation/kill/timeout discards results and requests adapter
  cancellation. Existing STT uses `asyncio.to_thread`; cancelling its await does **not** stop native
  inference. Keep its capacity slot until actual worker termination. Hard termination would need
  an isolated worker; never claim immediate native cancellation or admit overlapping workers.
- Keep raw audio/transcript in process/browser memory only until cleanup. No audio/transcript in
  logs, audit payloads, traces, database, URLs, local/session storage, IndexedDB or service-worker
  cache. Audit only bounded outcome/timing/ownership metadata. Drop references promptly; do not
  claim guaranteed memory zeroization in JavaScript/Python. Only explicitly sent text enters
  existing Core conversation storage/privacy routing.
- Maintain the **$0** limit: existing local speech only; no paid service, cloud speech/provider
  audio, new account, signing, public/remote deployment or native dependency work. Existing chat
  privacy routing and consequential-action approvals remain authoritative after Send.

## Implementation milestones

Execute only after F13 implementation is requested; this plan starts no application work.

1. **F13A — Core transcription boundary.** Create `docs/phase-reports/PWA_F13_PROGRESS.md` with
   acceptance checklist and baseline. Add typed PCM/result contracts, injected transcription-only
   service, gates/availability, scoped route, upload limits, capacity/cancellation and metadata-only
   audit. Compose with existing Core lifecycle. Use fake adapters first. Resolve locked speech
   extra/model readiness explicitly; do not enable production settings or capture a real microphone.
2. **F13B — Foreground capture and draft.** Add worklet plus Chat controls/state machine. Integrate
   session/navigation/conversation/logout cleanup and editable transcript review. Add worklet as a
   static route and explicit public shell asset. Advance shell/script/worklet/worker/cache markers
   together to **v10** if v9 is still current; APIs/audio/transcripts remain cache-excluded.
3. **F13C — Automated failure/security/accessibility gates.** Extend existing real-script tests,
   Python web/voice/security tests and desktop browser harness; verify resampling with generated
   signals at 16,000/44,100/48,000 Hz and irregular block boundaries. Run local model acceptance
   on synthetic/public non-private fixture audio when assets are available. Report dependency or
   model unavailability separately; fake success cannot establish real STT readiness.
4. **F13D — Release evidence and documentation.** Run full applicable locked quality/security
   gates and existing synthetic transport benchmark. Record counts, versions, known limits and
   local STT timing separately from phone measurements. Update setup/architecture/status docs;
   publish safe source under standing authorization. Stop at F13; no follow-on feature implied.

Minimum automated acceptance covers: no microphone/API side effects before Record; tap/keyboard
start/stop/discard and Escape; permission denial/never-resolved/late grant; track/context failure;
capture byte/time ceilings; silence/malformed input; busy/rate limits; missing adapters/models;
upload timeout; STT timeout with worker slot retained; kill/revocation during inference; stale
session/conversation/composer results; navigation/back/forward; offline/reload/logout cleanup;
no automatic Send/retry; zero audio/transcript persistence or cloud egress; no regression to chat
request ownership, Garmin authority or transport isolation. Desktop geometry, keyboard/focus,
accessible names/status, hidden controls and 44px targets extend F12's existing matrix.

Implementation gate commands use RTK and the locked environment: root and Garmin sidecar lock/sync,
bootstrap, Ruff format/lint, mypy, full strict pytest with unchanged **85%** coverage, relevant
voice/web/security tests, `node --test tests/pwa/garmin-lifecycle.test.cjs`,
`node scripts/pwa-accessibility-check.cjs`, existing PWA transport benchmark, root/sidecar
dependency audits, Gitleaks, documentation links, doctor and `git diff --check`. Install/test/audit
the locked voice extra separately; a base sync may remove optional speech packages. Preserve
synthetic evidence under ignored `runtime/`; never commit generated audio or private artifacts.

All manual phone checks remain **skipped by owner; unverified**. Do not request, remind or make
them prerequisites. Desktop/fake/audio-fixture evidence cannot prove iPhone microphone permission,
Home Screen capture, physical interruption, spoken accessibility or phone performance. Aggregate
MVP 4 acceptance stays incomplete. M3C access authority and native dependency publication hold
remain separate. Spoken replies, wake words/background listening, realtime/full-duplex audio,
new tools, attachments and expanded health access are outside F13.

## Standards and planning verification

Primary sources reviewed 2026-10-17: [Media Capture and Streams](https://www.w3.org/TR/mediacapture-streams/)
(secure context, consent, track lifecycle), [Web Audio](https://www.w3.org/TR/webaudio/)
(AudioWorklet and context sample rates), [Permissions Policy](https://w3c.github.io/webappsec-permissions-policy/)
(document feature controls), and [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
(keyboard and pointer cancellation). These support the proposed design, not a physical-device pass.

Planning checks pass: **4 documents / 54 relative links / zero missing targets**, staged and
worktree whitespace, Gitleaks history (**119 commits**) and staged planning source,
and unchanged held-file hashes. F12 test counts are historical evidence; this planning session
does not claim a new runtime release gate, microphone capture, local model readiness or F13
implementation pass. Application tests were not rerun for this documentation-only change.
