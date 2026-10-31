# Foreground voice

Current Phase 12 selects **local speech input, reviewed draft, explicit Send, text replies**.
One Windows Core and existing authenticated PWA; no second conversation or voice runtime.
`prototype-text`, daily text and other capability profiles retain their original restrictions.

## Startup and controls

Use `scripts/open-voice.cmd` for installed `qwen3:1.7b`, temperature 0 and local-only routing.
It selects `foreground-voice` and locked voice dependencies, but does not enable host controls,
request microphone permission, download speech models or stop an existing Core writer.
Keep existing approved private HTTPS/origin/device connection; no enrollment or scope change.

Voice availability requires all of:

- `JARVIS_PWA_VOICE_ENABLED=true` in host configuration, independently default false.
- Existing trusted-host software voice enable (`rtk proxy uv run --locked --extra voice python -m jarvis voice enable`).
- Installed locked voice extra and existing configured local speech model cache.
- Current authenticated `client.chat`, host ownership/origin/CSRF and browser microphone consent.

These are operator instructions, not evidence that production controls were enabled. Model setup
is a separate explicit operation; normal startup/transcription uses local files only. Missing
packages/models, disabled/unreadable controls or unavailable microphone leave typed chat usable.

## Use and privacy

Connect, wait for live history, leave composer empty, then Record message. Stop closes tracks
before uploading canonical PCM to Core. Review/edit the transcript, then Send deliberately.
Discard or Escape cancels recording/transcription. Cancel reply separately stops generation;
Retry request consults its original receipt. No automatic capture, Send, upload retry or playback.
Replies remain visible text; browser speech vendors receive no transcript/reply. Legacy desktop
SAPI TTS remains separate and is not activated by this profile.

Navigation, conversation change, hiding/pagehide, offline, identity replacement/logout and
microphone/context loss discard capture and reject late results. Permission wait is 30 seconds.
Raw PCM and unsent transcript stay in process/page memory, outside logs, database, browser
persistence and caches. Only deliberately sent text follows normal conversation retention.
JavaScript/Python reference cleanup does not guarantee memory zeroization.

Existing F13 limits remain: mono 16000 Hz signed 16-bit little-endian, 120–30000 ms,
3840–960000 bytes, 15-second upload, local STT <=90 seconds, one worker/no queue and six
starts/device/minute. Lower host capture limits still apply. Cancellation is cooperative;
native worker capacity stays held until termination. No cloud speech, new scopes, action
authority, attachments, research, health, email/calendar, background/wake/clap listener.

## Recovery and evidence

Type when speech fails. Discard/Escape stops the foreground operation; host
`rtk proxy uv run --locked --extra voice python -m jarvis voice disable` enforces the software
kill while text remains usable. Setting `JARVIS_PWA_VOICE_ENABLED=false` then restarting the
owner-controlled Core disables new voice admission. Reconnect/reload never resumes capture.
Default-off/legacy/offline cached documents deny microphone permission. No store migration.

Opt-in disposable Windows acceptance:

```powershell
rtk proxy uv run --locked --extra voice python -X utf8 scripts/foreground-voice-acceptance.py --live
rtk proxy uv run --locked --extra voice python -X utf8 scripts/pwa-voice-acceptance.py
```

First harness uses real browser AudioWorklet/auth/PCM/local Silero/faster-whisper/Core/Ollama,
synthetic SAPI audio, isolated controls/history/identity/TLS and existing local model cache.
Second checks a synthetic reference directly through the local transcription service. Neither
opens a physical microphone, plays speakers, changes host controls or downloads models.
Generated audio, keys, stores and browser evidence stay ignored under `runtime/`.

F13 transport/lifecycle contracts: [original contract](PWA_F13_PUSH_TO_TALK.md).
Current measurements: [Phase 12 report](phase-reports/current/PHASE_12_COMPLETION.md).
Phone checks **skipped by owner; unverified**. Desktop/synthetic evidence grants no physical,
native, mobile MVP or production acceptance. Wikimedia authentication blocker/native hold remain.

Primary references reviewed 2026-10-31: [Media Capture and Streams](https://www.w3.org/TR/mediacapture-streams/),
[Web Audio](https://www.w3.org/TR/webaudio/),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper).
These support consent, track cleanup, actual-rate processing and local model-loading contracts;
installed-version behavior is verified separately by the harnesses.
