# Phase 7 Vision and Gestures Progress Report

Status: `in-progress` — Phase 7A complete; Phase 7B initiated; 7C not started
Started: 2026-09-08  
Updated: 2026-09-08  
Active subphase: Phase 7B — temporal gestures/calibration
Completed subphase: Phase 7A — capture/privacy/contracts
Recommended Codex model: `gpt-5.6-sol` for 7B (`gpt-6-astra` for aggregate Phase 7)
Recommended reasoning: `high` for 7B (`max` for aggregate Phase 7)
Session start / five-hour stop: 2026-09-08 21:05 EDT / 2026-09-09 02:05 EDT

## Objective

Add provider-neutral local hand landmarks, temporal fist/palm/pinch/finger-roll recognition,
confidence/debounce/cooldown controls, and privacy-minimal calibration on the completed 7A capture
boundary. Phase 7B emits gesture observations only. It does not map gestures to intents, propose or
execute tools, approve work, retain pixels/landmark sequences, identify people, or use cloud vision.

## Baseline

- Git branch/HEAD: `main` at `1595c1ef5547f35ba89483173eb897893dda6b83`, twelve commits
  ahead of local `origin/main` at session start.
- Worktree state and preserved unrelated changes: untracked
  `.codex_finish_jarvis_cleanup.ps1` belongs to the earlier OneDrive consolidation and remains
  untouched/unpublished.
- Relevant installed software/hardware/provider state: Windows 11 Home build 26200; Python
  3.11.16; uv 0.12.5; Git 2.55.0; Gitleaks 8.30.1; ASUS TUF Gaming F15; Intel i5-11400H;
  16,888,967,168 bytes RAM; one healthy `USB2.0 HD UVC WebCam`. OpenCV, MediaPipe, and Pillow are
  absent from the base environment. No cloud credential variable names were present.
- Existing tests and failures: pre-change current baseline passed 714 tests with 1 skipped and
  85.13% coverage; Ruff and strict mypy passed.
- Prior phase evidence: Phase 3 exact one-use broker, closed hands-free mapping, and default-off
  authority are implemented; current live OS-effect closeout remains separately gated. Phase 7A
  grants no action authority and does not need a live Phase 3 effect.

## Phase 7B initiation baseline

- Git/working tree: `main` at `88e2c21`, equal to `origin/main`; unrelated untracked
  `.codex_finish_jarvis_cleanup.ps1` remains untouched and excluded.
- Current release baseline: 752 passed, 2 skipped, 85.10% coverage on Python 3.11.16; exact lock
  and base sync pass.
- Target host: Windows 11 build 26200; ASUS TUF Gaming F15 FX506HF; Intel i5-11400H; 16.89 GB RAM;
  healthy USB UVC webcam. Capture host gate and persistent software control are disabled and no
  capture session is active.
- Base environment: OpenCV, Pillow, NumPy, and MediaPipe are absent after the ordinary locked sync;
  no relevant capture/cloud credential variable names are present.
- Candidate review: the current official MediaPipe Hand Landmarker supports Python image/video/live
  modes, 21 normalized and world landmarks, handedness, confidence thresholds, and tracking. The
  project/package is Apache-2.0, but the current MediaPipe privacy notice says Tasks sends API
  performance/utilization metrics to Google and makes the application owner responsible for
  informed consent. JARVIS therefore does not install, initialize, or adopt current MediaPipe until
  the owner explicitly accepts that disclosure/consent boundary or selects a reviewed no-telemetry
  candidate. Sources: [Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python),
  [repository/privacy notice](https://github.com/google-ai-edge/mediapipe), and
  [license](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE).

## Phase 7B acceptance checklist

### Functional deliverables

- [x] Owned immutable contracts represent exactly 21 normalized local hand landmarks, handedness,
  observation confidence/freshness, detector failure classes, calibration profile, closed gesture
  vocabulary, and gesture observation events without action fields.
- [ ] Local detector adapter implements the owned contract behind an optional reviewed dependency;
  fake detector and deterministic landmark fixtures keep CI camera/network/model independent.
- [x] Temporal recognizer supports closed fist, open palm, pinch, clockwise finger-roll, and
  counter-clockwise finger-roll with confidence, consecutive-frame debounce, release/re-arm,
  cooldown, freshness, handedness, and one-hand conflict enforcement.
- [x] Calibration derives only bounded dimensionless thresholds and mirrored-camera orientation;
  raw pixels, landmarks, world coordinates, hand geometry, and identity attributes are not stored.
- [x] Phase 7B exposes no gesture-to-intent mapping, Phase 3 proposal, approval, tool execution,
  shell/path/action arguments, background listener, or startup capture.

### Failure, cancellation, restart, and recovery

- [ ] Invalid/missing/malformed landmarks, non-finite coordinates, stale/out-of-order timestamps,
  detector dependency/model failure, timeout, cancellation, dropped frames, no-hand, multiple-hand
  conflict, occlusion, low confidence, and calibration corruption fail closed with no gesture event.
- [ ] Reset/restart clears temporal history and cooldown state; detector/source cleanup is bounded
  and idempotent; disabling 7A capture prevents all new landmark work.

### Privacy and security

- [x] Pixels and per-frame landmark/world-coordinate features remain ephemeral, local, excluded
  from logs/audit/reports, and released with the owning 7A frame.
- [x] Unknown, ambiguous, conflicting, low-confidence, stale, replayed, or out-of-order observations
  emit nothing; no confidence value can grant authority or approve work.
- [ ] Candidate dependency/model license, network behavior, telemetry, provenance, checksum, and
  redistribution terms are reviewed before adoption; no external code or model is copied into Git.

### Fixed quantitative targets

- [x] Deterministic labeled landmark corpus: at least 1,000 sequences spanning all five gestures,
  both handedness values, scale/distance, mirrored orientation, occlusion/drop variants, similar
  movements, conflicts, no-hand, and low-confidence negatives; macro precision >= 0.95 and macro
  recall >= 0.95, with each gesture precision and recall >= 0.90.
- [x] Negative soak: at least 36,000 frames (one simulated hour at 10 FPS) across no-hand, held
  poses, ambiguous motion, drop, replay, and two-hand conflict; false activations <= 0.1/hour and
  zero action proposals/executions by construction.
- [x] Classifier-only benchmark: at least 10,000 frames, warm p50/p95 reported, p95 <= 5 ms/frame,
  zero invalid emissions, and <= 50 MiB RSS growth.
- [ ] Reviewed detector end-to-end benchmark on target CPU at 640x480/10 FPS: at least 1,800 live
  or approved recorded frames, p95 <= 100 ms/frame, >= 9 processed FPS, average total CPU <= 35%,
  GPU optional/not required, and <= 50 MiB RSS growth during a 30-minute soak.
- [ ] Authorized diverse real-target evaluation covers at least two lighting levels, two distances,
  left/right hands, mirrored/unmirrored handling, partial occlusion, backgrounds, similar movement,
  and no-hand periods; no retained camera media or raw landmark dataset.

### Documentation and release

- [x] Safe-core/calibration operator guide, dataset card, privacy/security/architecture/hardware,
  setup/configuration, roadmap, status, rollback, and limitation documentation match evidence.
- [ ] Optional dependency clean install/import and ordinary camera-independent CI pass; complete
  lock/sync/format/lint/type/test/vulnerability/secret/diff/doctor plus 7B benchmark gates pass.

## Phase 7B milestones

### Milestone 1 — Baseline, candidate/privacy decision, threat model, and fixed gates

- Status: complete
- Changes: full playbook and target references read; current Git/test/environment/hardware/capture
  baseline recorded; fixed acceptance targets declared before classifier tuning; current MediaPipe
  telemetry and consent boundary identified from official sources.
- Evidence: baseline exact lock/sync and 752-test suite pass; capture status is disabled/inactive.
- Remaining: candidate adapter adoption needs owner direction because current MediaPipe Tasks sends
  metrics to Google; this moves to Milestone 3.

### Milestone 2 — Owned landmark, calibration, and temporal recognition core

- Status: complete for the provider-neutral safe core
- Changes: immutable 21-landmark/hand/frame/calibration/gesture/failure models; detector and sink
  ports; dimensionless feature extraction; bounded scalar-only calibrator; temporal recognizer;
  pixel-independent fake detector; frame-to-event processor; deterministic benchmark and tests.
- Evidence: 23 focused tests pass. Whole suite passes with 775 tests, 2 skips, and 85.39% coverage.
  Synthetic gate: 1,000 sequences at 1.00 macro/per-gesture precision and recall; 36,000 negative
  frames with zero false activations; 10,000 classifier frames at 0.0119/0.0138 ms p50/p95 and
  0.316 MiB RSS growth.
- Remaining: no safe-core work. Real detector and human/camera evaluation remain Milestone 3.

### Milestone 3 — Reviewed local detector and target evaluation

- Status: blocked on candidate privacy decision and later live-capture authorization
- Changes: none.
- Evidence: official candidate review above.
- Remaining: locked candidate/model, adapter contract tests, authorized target dataset, performance,
  accuracy, resource, and 30-minute soak evidence.

### Milestone 4 — Documentation, complete gates, and 7B handoff

- Status: complete for the provider-neutral safe-core release
- Changes: gesture operator/developer guide, synthetic dataset card, architecture, security,
  hands-free, hardware, setup, technology-decision, roadmap, overview, README, and progress updates.
- Evidence: documentation distinguishes perfect synthetic state-machine results from unmeasured
  detector and real-human behavior. Exact lock/sync, format, lint, full type checking, 775-test suite,
  vulnerability audit, secret scan, diff check, doctor, and 7B synthetic benchmark pass.
- Remaining: candidate dependency install/import and detector/live documentation and gates remain
  open under Milestone 3.

## Phase 7A acceptance checklist

### Functional deliverables

- [x] Strict owned contracts bind source, stable source ID, purpose, exact region, pixel format,
  requested FPS, maximum frames, maximum duration, per-frame timeout, and ephemeral retention.
- [x] Fake, OpenCV camera, and Windows screen adapters satisfy one bounded capture contract.
- [x] Capture controller requires both host configuration and persistent user control, activates a
  visible indicator before opening any source, and closes source before clearing indicator.
- [x] Software kill, cancellation, and one-session concurrency stop capture without a background
  listener or action proposal.
- [x] CLI exposes status, enable, disable, doctor, and explicit bounded capture without printing or
  storing frame content.

### Failure, cancellation, restart, and recovery

- [x] Tests cover deny/default-off, source switch/busy, source loss, malformed or stale frame,
  frame/duration cap, open/capture/consumer timeout, cancellation, indicator failure, settings
  corruption, restart, and kill while active.
- [x] Any uncertain source/indicator/settings state fails closed; source cleanup remains bounded and
  idempotent.

### Privacy and security

- [x] No source opens before explicit active state and visible indicator; indicator failure causes
  zero capture.
- [x] Frames stay local, are never persisted or logged, and controller-owned buffers are cleared
  immediately after the bounded consumer returns or fails.
- [x] Retention values other than `ephemeral`, cloud disclosure, biometrics, hidden capture, and
  unbounded/full-desktop defaults are structurally rejected or absent.
- [x] Gesture recognition, mapping, approvals, and tool execution remain outside Phase 7A.

### Fixed quantitative targets

- [x] At least 200 fake one-frame controller runs: capture-boundary overhead p95 <= 25 ms,
  excluding adapter capture time; zero leaked live buffers.
- [x] At least 100 denial/abuse scenarios: zero source opens or frame deliveries outside explicit
  active state, indicator, requested source/region, freshness, and configured limits.
- [x] Kill/cancel observed no later than one bounded in-flight frame timeout (fixed maximum 1,000
  ms); frame rate never exceeds requested FPS over multi-frame fake-clock tests.

### Target environment, documentation, and release

- [x] Optional vision dependencies install from the locked environment and import on current
  Windows host; ordinary CI remains camera/screen/network independent.
- [x] Current official license/privacy behavior is reviewed before adoption; no external source code
  is copied.
- [x] Capture/privacy operator guide, setup/configuration, architecture, security, hands-free plan,
  hardware report, roadmap, and phase status match verified behavior.
- [x] Lock/sync/format/lint/type/test/vulnerability/secret/diff/doctor gates pass.

## Phase 7A milestones

### Milestone 1 — Baseline, threat model, acceptance, and contracts

- Status: complete
- Changes: mandatory playbook and Phase 7 references read; Git, tools, hardware, installed vision
  libraries, credentials by variable name, and Phase 3 evidence inventoried; fixed acceptance
  targets recorded before implementation.
- Evidence: typed model/port tests cover every field and hard ceiling; pre-change gate recorded
  714 passed, 1 skipped, 85.13% coverage.
- Remaining: none.

### Milestone 2 — Privacy controller, settings, indicator, and fakes

- Status: complete
- Changes: dual-gate controller, atomic persistent kill store, terminal indicator, zeroing frame
  owner, cancellation, concurrency guard, and deterministic fakes.
- Evidence: focused controller/settings/model tests cover default denial, ordering, kill, cancel,
  restart, busy/switch, corruption, stale/mismatch, caps, pacing, and cleanup.
- Remaining: none.

### Milestone 3 — Windows adapters, CLI, and diagnostics

- Status: complete
- Changes: isolated Windows worker, OpenCV camera and Pillow screen paths, sanitized worker
  environment, status/control/doctor/capture CLI, and non-capturing main diagnostics.
- Evidence: adapter protocol/error/source tests and CLI/diagnostic suites; optional locked imports
  passed on the target host without opening a source.
- Remaining: none for 7A.

### Milestone 4 — Benchmark, documentation, release gates, and handoff

- Status: complete
- Changes: fixed benchmark and operator/privacy, setup, architecture, security, hands-free,
  hardware, technology, roadmap, status, and report documentation.
- Evidence: 200-session p95 0.229 ms; 100 abuse scenarios; no violations or leaked buffers.
- Remaining: none for 7A.

## Decisions

- Decision: ship only ephemeral in-memory frames in 7A.
- Reason: recognition, artifact retention, OCR, biometrics, and cloud disclosure are excluded; a
  broader retention model would create unneeded privacy state.
- Alternatives: image files, database blobs, screenshots, hashes, and model-bound artifacts are
  excluded.
- Reversible later: a separately reviewed artifact store can add explicit retention in a future
  phase without weakening this capture boundary.

- Decision: require a host configuration gate plus persistent user kill control.
- Reason: neither configuration nor stale persisted state alone may activate a privacy-sensitive
  device.
- Alternatives: implicit camera probing, startup capture, and background listeners are excluded.
- Reversible later: Phase 7C may add an explicit foreground gesture session after 7B evaluation.

## Verification evidence

```text
Baseline inventory on 2026-09-08
Windows 11 Home 10.0.26200; Python 3.11.16; uv 0.12.5; one healthy USB UVC webcam
OpenCV/MediaPipe/Pillow absent; no cloud credential variable names found

Focused implementation verification
76 passed, 1 skipped across vision plus adjacent configuration/CLI/diagnostics tests
strict mypy: success across 99 source files
optional imports: OpenCV 5.0.0, Pillow 12.3.0, NumPy 2.4.6

Final repository release gate
uv lock/sync, Ruff format/lint, strict mypy, pip-audit, Gitleaks, and git diff --check passed
752 passed, 2 skipped; 85.04% total coverage
main doctor and vision doctor passed with both capture gates disabled; neither opened a source

Authorized bounded live closeout
camera:0, diagnostic, RGB24, region 0,0,640x480: 1 frame, 921600 bytes, 2781 ms
screen:desktop, diagnostic, RGB24, region 0,0,640x480: 1 frame, 921600 bytes, 515 ms
Both runs: active indicator before capture, off after source close, stop=frame_limit, pixels discarded
Postcondition: host gate disabled, persistent software control disabled, capture inactive

Phase 7B safe-core verification
23 focused tests passed
whole suite: 775 passed, 2 skipped, 85.39% coverage
synthetic corpus: 1,000 sequences; macro/per-gesture precision and recall 1.00
negative soak: 36,000 frames / one simulated hour; zero false activations/actions
classifier: 10,000 frames; p50 0.0119 ms; p95 0.0138 ms; RSS growth 0.316 MiB
MediaPipe package/model not installed or initialized; no camera capture performed
```

## Benchmarks

### Phase 7B safe core

- Samples: 1,000 labeled sequences; 36,000 negative frames; 1,000 warm-up plus 10,000 measured
  classifier frames.
- Cold/warm: deterministic Python landmark/state-machine path; classifier timings are warm and
  exclude camera/detector/model time.
- p50: 0.0119 ms/frame.
- p95: 0.0138 ms/frame against fixed <= 5 ms target.
- Quality: macro precision/recall 1.00; every gesture precision/recall 1.00; zero false
  activations in one simulated hour.
- Errors/failures: zero invalid emissions, action proposals, or executions; RSS growth 0.316 MiB.
- Hardware/runtime/model/device versions: Windows build 26200, Python 3.11.16, target laptop above;
  no detector model/provider/device used.
- Relevant settings: default profile except unmirrored test profile, 250 ms cooldown, 1,000 ms
  fixture-age bound, and 1.2-radian roll gate. Evidence:
  `runtime/phase7b-gesture-core-03/benchmark.json` (ignored local aggregate output).
- Limit: synthetic state-machine evidence only; no claim about real detector, lighting, skin tone,
  background, camera, thermals, or human usability.

### Phase 7A capture boundary

- Samples: 200 fake one-frame foreground sessions; 100 denial/abuse scenarios.
- Cold/warm: in-process fake boundary only; native device time intentionally excluded.
- p50: 0.180 ms.
- p95: 0.229 ms against fixed <= 25 ms target.
- Errors/failures: zero leaks, zero privacy violations.
- Hardware/runtime/model/device versions: baseline above; no model/provider used by Phase 7A
- Relevant settings: one frame, ephemeral RGB24; hard limits fixed in acceptance above.
- Live closeout: one camera and one screen-region frame; no retained media or content output.

## Security and privacy

- Threats tested: disabled gates, indicator failure, busy/source switch, source loss,
  malformed/stale/mismatched data, settings corruption/change, timeout, cancellation, kill,
  restart, limit violation, secret environment inheritance, and worker protocol failure.
- Data boundaries: local-only, ephemeral frame ownership; no cloud, persistence, or action authority.
- Phase 7B adds ephemeral normalized landmark frames and aggregate calibration thresholds only;
  emitted gesture events have no mapping, action, argument, approval, permission, or tool fields.
- Permissions/approvals: explicit local capture controls only; Phase 3 grants remain separate.
- Audit/retention/deletion: content-free session metrics only; no retained media exists to export or
  delete.
- Secret scan: Gitleaks 8.30.1 scanned 18 commits / about 3.17 MB; no leaks found.

## Blockers

- None for completed Phase 7A.
- Phase 7B candidate adoption is blocked at an owner authority boundary: current MediaPipe Tasks
  sends performance/utilization metrics to Google and requires informed-consent handling. No
  telemetry disclosure or new material term is accepted by this initiation request.
- Phase 7B live/recorded camera evaluation and the 30-minute target soak require separate explicit
  bounded capture authorization after the detector candidate and exact test protocol are fixed.

## Known limits and deferred scope

- Gesture mapping, Phase 3 proposals/actions, OCR/object/scene understanding, multimodal model
  disclosure, and retained media remain deferred to 7C or later. MediaPipe adoption remains
  undecided because of current telemetry/consent behavior.

## Recovery and rollback

- Keep `JARVIS_VISION_CAPTURE_ENABLED=false`, persist the software control as disabled, cancel any
  foreground capture, close the adapter, and remove the optional vision extra if rollback is
  needed. Text, voice, permissions, memory, research, and task features remain independent.

## Final handoff

- Final status: Phase 7A complete; Phase 7B safe core implemented; detector/live acceptance blocked;
  aggregate Phase 7 remains in progress.
- Files changed this session: gesture contracts/features/calibration/recognizer/fake/pipeline,
  deterministic benchmark/tests, dataset/operator guides, and affected architecture/security/setup/
  hardware/technology/roadmap/status documentation.
- Next recommended work: owner selects MediaPipe-with-metrics or a reviewed no-telemetry candidate;
  then implement the adapter and request exact live evaluation authority. Phase 7C remains out of
  scope.
- Commit/push status: Phase 7A closeout `88e2c21` is on `origin/main`; current Phase 7B changes use
  standing safe-source commit/push authorization after required gates. Unrelated
  `.codex_finish_jarvis_cleanup.ps1` remains excluded.
