# Vision Capture Privacy Boundary

Updated: 2026-09-08  
Status: Phase 7A complete

Phase 7A provides explicit, bounded camera and screen-region capture. It does not recognize
gestures, retain images, call a cloud vision service, inspect pixels with a model, or authorize a
computer action.

## Privacy contract

Every request binds an exact source and stable source ID, purpose, non-empty region, RGB24 pixel
format, frame rate, frame count, duration, frame timeout, and `ephemeral` retention. Current hard
ceilings are 15 FPS, 300 frames, 30 seconds, a 1,000 ms per-frame timeout, and a 1920 x 1080 region.
Camera IDs are `camera:0` through `camera:31`; the only screen ID is `screen:desktop`.

Capture requires both controls:

1. `JARVIS_VISION_CAPTURE_ENABLED=true` at process startup.
2. The persistent local software control enabled with `jarvis vision enable`.

The foreground `jarvis vision capture` command is still required. No startup probe, resident
listener, scheduled capture, hidden mode, or full-desktop default exists. The controller displays
`JARVIS CAPTURE ACTIVE` before opening a source, closes the source before displaying
`JARVIS CAPTURE OFF`, and permits only one session. Indicator or settings uncertainty denies
capture.

Frames remain in a controller-owned memory buffer. The buffer is cleared immediately after the
bounded consumer returns or fails. Frame bytes, hashes, thumbnails, OCR, filenames, and pixel
values are not logged or persisted. Session output contains only source metadata, dimensions,
counts, timings, and stop/failure reason.

## Install and inspect without capture

```powershell
uv sync --locked --extra vision
uv run jarvis vision status
uv run jarvis vision doctor
```

`vision doctor` imports the OpenCV and Pillow adapters and checks gates/settings. It does not open
a camera or read the screen.

## Explicit bounded capture

Start with the software control disabled. Review the source and exact region, close private
windows, and use the webcam shutter or Windows camera privacy control as an independent kill path.

```powershell
uv run jarvis vision enable
# Set JARVIS_VISION_CAPTURE_ENABLED=true, then start a new foreground process.
uv run jarvis vision capture --source camera --source-id camera:0 --x 0 --y 0 --width 640 --height 480 --fps 10 --frames 1 --duration-ms 1000
uv run jarvis vision disable
```

For a screen-region test, use `--source screen --source-id screen:desktop` and exact coordinates.
The command reads the requested frame and immediately discards it; it does not print or save the
image. `jarvis vision disable` is the software kill command and remains effective across restart.

## Isolation and failure behavior

Native capture runs in a short-lived child process connected through private pipes. The child gets
only a fixed allowlist of ordinary Windows process variables; JARVIS/provider credentials are not
inherited. Camera and screen adapters are loaded lazily. Timeout, cancellation, protocol error,
source loss, stale/mismatched frame, persistent-control change, or consumer failure terminates the
session, clears the frame, and closes or kills the worker. The worker is process-isolated, not a
Windows AppContainer.

If an indicator remains visible after an abnormal terminal failure, run:

```powershell
uv run jarvis vision disable
```

Then close the foreground JARVIS process and use the physical shutter or Windows **Settings >
Privacy & security > Camera** control before retrying. Text, voice, memory, research, planning, and
Phase 3 controls remain independent.

## Windows and dependency notes

Windows controls desktop-app camera access separately and normally shows a hardware light or
camera-use notification ([Microsoft camera privacy guidance](https://support.microsoft.com/en-us/windows/windows-camera-microphone-and-privacy-a83257bc-e990-d54a-d212-b5e41beba857)).
Those OS indicators are independent of the JARVIS terminal indicator.
Screen-region capture has no equivalent hardware light, so exact coordinates and foreground use
are mandatory.

Phase 7A adopts optional [`opencv-python-headless`](https://pypi.org/project/opencv-python-headless/)
5.x and [Pillow](https://pypi.org/project/pillow/) 12.x packages. OpenCV 4.5 and later is
[Apache-2.0](https://opencv.org/license/); the Python wrapper is MIT and its wheels include
LGPL-2.1 FFmpeg components. Pillow is MIT-CMU. JARVIS installs only one OpenCV package and uses no
OpenCV GUI window. [MediaPipe](https://github.com/google-ai-edge/mediapipe) remains deferred to
Phase 7B because gesture/landmark processing is outside 7A. Phase 7B's owned temporal core is now
implemented without MediaPipe. Current MediaPipe API terms state that Solution/Tasks APIs contact
Google servers and send performance/utilization/application/input/system metadata, with informed
consent duties for the app owner. JARVIS does not install or initialize it without an explicit owner
decision. See [Local Gesture Recognition](GESTURE_RECOGNITION.md).

No third-party source code or model artifact is copied into this repository.

## Closeout evidence

On 2026-09-08, the audited Windows host completed exactly one `camera:0` frame and one
`screen:desktop` frame, each at `(0,0)` with a 640 x 480 RGB24 region. Both displayed the active
indicator before capture and the off indicator after source close, delivered 921,600 bytes, and
discarded the pixels. Camera duration was 2,781 ms; screen duration was 515 ms. The persistent
software control and host gate were then verified disabled, with no active session.
