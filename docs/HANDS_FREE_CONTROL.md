# Hands-Free Control Plan

Updated: 2026-08-22  
Status: Phase 2 double-clap detector, Phase 3 closed typed proposal mappings, Phase 7A bounded
capture/privacy contracts, and Phase 7B provider-neutral temporal gesture core implemented;
continuous audio/camera listeners, a real hand-landmark detector, and gesture-to-action integration
remain disabled/unimplemented

## Goal

Control common laptop actions through local acoustic and hand gestures without touching the
keyboard. Recognition produces a typed intent; it never executes arbitrary commands directly.
Phase 3 permission policy remains the only path from intent to action.

## Initial controls

| Input contract | Phase 3 typed result | Current state | Default |
| --- | --- | --- | --- |
| Double clap | `launch_app_group` for only `hands_free_app_group` | Phase 2 detector and synthetic gate tests exist; continuous listening remains off | Existing configured app-group compatibility |
| Clockwise/counter-clockwise gesture | `set_master_volume` at current rounded percentage plus/minus exactly 5, clamped to 0-100 | Mapping verified with injected read-only volume state; no gesture detector | Off |
| Open-palm gesture | `control_media` with exact `play_pause` operation | Mapping verified synthetically; no gesture detector | Off |
| Swipe-left/right gesture | `control_media` with exact `previous_track`/`next_track` operation | Mapping verified synthetically; browser-tab navigation is deferred | Off |
| Cancel gesture | Session-scoped no-authority cancel directive | Mapping and cross-session denial verified synthetically; no gesture detector | Off |

Mute, browser-tab navigation, desktop/app switching, and gesture approval are not Phase 3
mappings. Detector input has no action-ID, path, operation, or numeric-delta field. Every emitted
action proposal remains Level 1 and represents neither approval nor execution authority.

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
3. Detector adapters may emit only the closed typed values `launch_app_group`, `volume_up`,
   `volume_down`, `media_play_pause`, `media_previous_track`, `media_next_track`, or `cancel`.
4. Phase 3 resolves that intent through an allowlisted action mapping and permission broker.
5. Execution emits an audit record and verifies the postcondition when possible.

No gesture becomes shell text, executable arguments, a file path, or model-generated code.

Phase 2 now provides a local adaptive double-clap detector and emits only typed
`launch_app_group` intent data. The fixed corpus achieved 20/20 positive detections and zero false
accepts in one simulated hour split across music, TV-like audio, typing, and room noise. This does
not grant action authority: continuous acoustic listening remains hard-disabled. Phase 3 applies
the same actor/source-session, freshness, confidence, replay, rate, and Level 1 checks to its closed
proposal mappings. The dormant gesture mappings are covered with synthetic intent tests only and
are absent unless individually enabled in host policy. A production consumer calls only
`ActionCoordinator.propose` with `ApprovalSource.HANDS_FREE`; trusted review and one-use broker
execution remain separate.

Phase 7A now provides dual-gated, foreground-only, visible, exact-region camera/screen capture with
ephemeral cleared buffers and no action authority. It provides no hand detector, gesture intent,
mapping, calibration, or continuous listener. Its authorized live-device closeout passed;
Phase 7B now provides local-only 21-landmark contracts, aggregate calibration thresholds, and
debounced/cooldown/re-arm temporal recognition for fist, palm, pinch, and both finger-roll
directions. Synthetic accuracy/false-trigger/latency gates pass. It emits content-free gesture
observations only and has no Phase 3 proposal or execution path. A real detector and live evaluation
remain blocked pending the current MediaPipe telemetry/terms decision and separate capture authority.

## Safety requirements

- Local processing by default; no camera or microphone stream leaves the laptop.
- Visible hands-free, microphone, and camera indicators plus one-click/physical kill path.
- Per-gesture confidence threshold, debounce window, cooldown, and rate limit.
- Calibration for the user, camera position, lighting, clap volume, and background noise.
- Configurable allowlist for launchable apps and app groups.
- Every side effect requires the Phase 3 policy. Acoustic/gesture input cannot approve any action;
  destructive, financial, communication, credential, privacy, admin, and system-power mappings are
  absent.
- Unknown, ambiguous, or conflicting signals do nothing.
- Camera-off and microphone-off states are enforced technically, not just shown in UI.
- Thirty-minute false-trigger soak test before enabling always-on detection.

## Suggested implementation order

1. Double-clap detector proposing one allowlisted app group through the Phase 3 gate.
2. Universal closed-fist cancel gesture.
3. Open-palm media play/pause.
4. Finger-roll volume control with 5% bounded steps.
5. Calibration UI, profiles, indicators, audit viewer, and false-trigger report.
6. Optional confirmation and advanced navigation gestures.

Recommended execution: **`gpt-6-astra`, `ultra`** for permission/execution policy and
**`gpt-6-astra`, `xhigh`** for real-time audio/vision. Real gestures can trigger computer actions;
cheaper models are limited to isolated mechanical tests/docs.
