# Hands-Free Control Plan

Updated: 2026-08-22  
Status: planned; not implemented

## Goal

Control common laptop actions through local acoustic and hand gestures without touching the
keyboard. Recognition produces a typed intent; it never executes arbitrary commands directly.
Phase 3 permission policy remains the only path from intent to action.

## Initial controls

| Input | Default action | Risk class | Notes |
| --- | --- | --- | --- |
| Double clap | Open configured main-app group: ChatGPT, Opera, and user-selected apps | Reversible | Local clap detector, cooldown, configurable time window |
| Clockwise finger roll | Raise volume in 5% steps | Reversible | Continuous gesture with rate limit and on-screen level |
| Counter-clockwise finger roll | Lower volume in 5% steps | Reversible | Stops immediately when hand confidence drops |
| Pinch and hold | Mute/unmute | Reversible | Require minimum hold duration to prevent accidental toggles |
| Open palm | Play/pause media | Reversible | Optional per-app profile |
| Closed fist | Cancel current JARVIS output or pending low-risk action | Read-only/reversible | Universal emergency gesture |
| Swipe left/right | Previous/next track or browser tab | Reversible | User chooses mapping; never both simultaneously |
| Two-finger point left/right | Switch virtual desktop or app | Reversible | Disabled by default until calibrated |
| Thumbs up/down | Confirm/reject a displayed low-risk proposal | Approval signal | Never authorizes sensitive or destructive work |

## More ideas

- Triple clap: mute microphone or toggle hands-free mode.
- Hand raised for one second: start push-to-talk listening.
- Air dial: brightness control instead of volume.
- Palm toward camera: privacy pause; stop camera/microphone processing.
- Draw a small circle: open media controls.
- Per-room or per-app profiles with different mappings.
- Audible and visual confirmation tones, plus optional spoken feedback.
- Training screen showing recognition confidence and false-trigger history.

## Architecture

1. Phase 2 adds local clap/event detection through the audio pipeline.
2. Phase 7 adds local hand landmarks, temporal gesture recognition, calibration, confidence,
   debounce, and camera-state enforcement.
3. Both emit a provider-neutral `HandsFreeIntent` such as `launch_app_group`, `volume_delta`,
   `media_toggle`, or `cancel`.
4. Phase 3 resolves that intent through an allowlisted action mapping and permission broker.
5. Execution emits an audit record and verifies the postcondition when possible.

No gesture becomes shell text, executable arguments, a file path, or model-generated code.

## Safety requirements

- Local processing by default; no camera or microphone stream leaves the laptop.
- Visible hands-free, microphone, and camera indicators plus one-click/physical kill path.
- Per-gesture confidence threshold, debounce window, cooldown, and rate limit.
- Calibration for the user, camera position, lighting, clap volume, and background noise.
- Configurable allowlist for launchable apps and app groups.
- Destructive, financial, communication, credential, privacy, and system-power actions require
  trusted UI/voice confirmation; gestures alone cannot approve them.
- Unknown, ambiguous, or conflicting signals do nothing.
- Camera-off and microphone-off states are enforced technically, not just shown in UI.
- Thirty-minute false-trigger soak test before enabling always-on detection.

## Suggested implementation order

1. Double-clap detector controlling one allowlisted app group.
2. Universal closed-fist cancel gesture.
3. Open-palm media play/pause.
4. Finger-roll volume control with 5% bounded steps.
5. Calibration UI, profiles, indicators, audit viewer, and false-trigger report.
6. Optional confirmation and advanced navigation gestures.

Overall recommended Sol thinking: **Ultra** because real-world gestures can trigger computer
actions. Audio and vision recognition work uses **Extra high**; permission and execution policy
uses **Ultra**.
