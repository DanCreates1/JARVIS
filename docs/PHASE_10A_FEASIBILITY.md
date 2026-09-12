# Phase 10A Wearable Feasibility, Access, and License Matrix

Reviewed: 2026-09-11
Scope: official public documentation only; no account creation, term acceptance, SDK download,
vendor code copy, device enrollment, health import, or media capture.

## Decision summary

The owned generic contract and simulator are feasible now. A Meta Device Access Toolkit phone
bridge is the preferred Phase 10B prototype candidate because it matches the glasses objective,
supports iOS and Android, exposes a mock device, and keeps the vendor SDK in a mobile adapter.
Vendor integration is not yet authorized: the toolkit remains Developer Preview, publishing is not
available, and the binding Developer Terms and Acceptable Use Policy require authenticated access.

Wear OS is the strongest public alternative for a distributable generic watch client, but its Data
Layer requires Wear OS plus a paired Android device and may route through Google-owned servers.
Apple Watch fits the existing iPhone topology but requires Apple hardware/Xcode and accepted Apple
developer terms. Garmin Connect/Health is not selected: direct health access is enterprise-only,
commercial terms may create cost, and health data needs a separate privacy/retention decision.

## Dated matrix

| Candidate | Official access and current version | Confirmed capabilities and transport | Simulation/testing | Distribution/license boundary | Phase 10 disposition |
| --- | --- | --- | --- | --- | --- |
| Meta Wearables Device Access Toolkit | Public [iOS](https://github.com/facebook/meta-wearables-dat-ios) and [Android](https://github.com/facebook/meta-wearables-dat-android) repositories; latest documented/tagged version `0.9.0` dated 2026-08-03 | Mobile-app extension. Toolkit camera/photo/video; microphone and speakers through iOS/Android Bluetooth profiles; display only on supported display glasses. Meta AI app performs pairing. | Official Mock Device Kit simulates registration, permission, state, and media. It does not support display glasses. | [Meta FAQ](https://developers.meta.com/wearables/faq/) says Developer Preview permits build/test but not end-user publishing; sharing uses release channels. Repository license delegates to authenticated [Developer Terms](https://wearables.developer.meta.com/terms) and [Acceptable Use Policy](https://wearables.developer.meta.com/acceptable-use-policy). Analytics and crash reporting default on unless explicitly opted out. | Preferred provisional 10B prototype. Blocked until owner reviews/accepts exact current terms, confirms supported market/account access, and authorizes a mobile adapter project. No SDK code or binary enters core. |
| Wear OS Data Layer | Public Android SDK documentation; official dependency example `com.google.android.gms:play-services-wearable:20.0.1` reviewed 2026-09-11 | Capability discovery, messages, state/data/file transfer between matching package/signature on Android handheld and Wear OS. Bluetooth or network/cloud relay; cloud path is end-to-end encrypted but Google-operated. Notifications can bridge automatically. | Wear OS emulator supported; connection and Doze cases still need device tests. | Android documentation/code is governed by its [content license](https://developer.android.com/license); Google Play services and distribution terms remain separately applicable. Data Layer does not work for a Wear OS watch paired to iOS. | Viable alternate adapter, not current first choice. Requires Android bridge and explicit cloud-route privacy classification. |
| Apple Watch / WatchConnectivity | Public [WatchConnectivity](https://developer.apple.com/documentation/watchconnectivity) APIs; platform versions follow installed Apple SDK | Two-way app context, immediate messages, queued user info, file transfers, and complication updates between companion iOS/watchOS apps. | Apple requires physical iPhone/Watch for authoritative transfer tests; some file transfers are unsupported in Simulator. | Apple SDK use/distribution requires acceptance of current [Apple Developer agreements](https://developer.apple.com/support/terms). Xcode/Apple SDKs may not be run on this Windows host. | Feasible architecture, externally blocked on Mac/Xcode, developer-team terms, and Apple Watch hardware. |
| Garmin Connect Developer Program | Application/approval required; enterprise/business use only | OAuth 2.0 cloud-to-cloud Health, Activity, Women’s Health, Training, and Courses APIs. Not a generic real-time device client. | Production environment with throttled developer access after approval. | [Program FAQ](https://developer.garmin.com/gc-developer-program/program-faq/) says no general licensing/maintenance fee, but some commercial metrics can require a fee or minimum device order. | Defer. No application, credential, business representation, or paid term authorized. Manual FIT/TCX/GPX/CSV import remains safer future fallback. |
| Garmin Health SDKs / Connect IQ | Health SDK access by enterprise request; Connect IQ SDK `9.2.0` dated 2026-08-25 | Health SDK Standard/Companion provides direct or live health/sensor streams. Connect IQ device apps expose display/input/sensors and BLE/mobile or network communication. | Health SDK evaluation is free after approval; Connect IQ has SDK/device simulators. | [Garmin Health](https://developer.garmin.com/health-sdk/overview/) states commercial use needs a license fee or minimum device order. Connect IQ store/review and developer terms apply. | Generic UI client may be revisited; health ingestion remains disabled and separately gated. |

## Meta 0.9.0 capability notes

The official iOS and Android changelogs show material preview churn: `0.9.0` consolidated camera
ownership under a session camera, removed prior stream APIs, added display button groups, and added
crash-reporting opt-out. iOS minimum deployment increased to iOS 17.2. `0.7.0` introduced display,
thermal/device state, battery/thermal/peak-power failures, and display-aware device selection.
Therefore Phase 10B must pin an exact SDK version, wrap every vendor type, and test removal and
upgrade incompatibility. No vendor type may cross `jarvis.wearables`.

## Owned contract boundary

- Capabilities: audio input/output, display, camera, input, notification, and health.
- Negotiation returns only supported descriptors, permission state, limits, data class, and
  indicator requirement. `authorization_granted` is structurally always false.
- Operations require an exact host/device/session/capability authorization already present in a
  trusted store. Caller-constructed or model-provided grant-shaped data is denied.
- Camera and microphone are `media`; health is `health`; all other wearable data is `private`.
  These classifications cannot be downgraded by an adapter.
- Camera/microphone require a visible indicator. All operations are foreground, bounded,
  ephemeral, local-only, and cloud-disabled in Phase 10A.
- Receipts contain identifiers, counts, timing, and indicator state only. They contain no media,
  notification text, input value, or health metric.

## Phase 10B entry requirements

1. Owner reviews and explicitly accepts the exact vendor terms for the selected adapter.
2. Owner confirms intended platform, supported country/account access, device model, and whether a
   mobile app project may be created.
3. Selected SDK/version and transitive licenses are pinned and recorded. Analytics/crash reporting
   is disabled by default where vendor configuration permits.
4. Phase 8 enrollment/revocation binds the phone bridge; vendor discovery grants no JARVIS scope.
5. Media remains local and ephemeral with a tested hardware indicator and bystander policy.
6. Health stays disabled unless a separate consent, retention, deletion, export, and cloud-routing
   policy is approved.
7. Current-fact responses use the Phase 5 live-research path with citations, source timestamps,
   expiry, conflict disclosure, and explicit offline fallback status.
8. Logs or feedback may create maintenance suggestions only. Any preapproved low-risk isolated
   implementation remains production-unauthorized until trusted user approval.

## Revalidation

Recheck all linked official pages, SDK tags/changelogs, supported markets/devices, terms, default
telemetry, and publishing status at Phase 10B start. Preview facts are volatile; this document is
evidence dated 2026-09-11, not a permanent vendor promise.
