# Mobile M2C live acceptance

Status: local preparation in progress; physical iPhone evidence pending.

## Authority checkpoint

Ask the owner before creating **each** fresh enrollment ticket. Ask separately before starting an
Expo development build. Do not enter live ticket JSON, private key, signature, session token, exact
tailnet hostname, device identifier, screenshot, or phone data in chat, reports, logs, or Git.

The iOS development build uses app signing and a registered device. On this Windows workstation,
Expo's documented physical-device route uses EAS Build and an Apple Developer account. The owner
must choose the iOS bundle identifier, account, signing path, and any associated cost before that
build starts. Expo Go can provide provisional JavaScript and native-module evidence; it does not
prove the final app scheme or independent native binary.

## Read-only preflight

1. Check Git and keep the Phase C work untouched. Run the mobile `npm.cmd run verify` gate.
2. Check Tailscale online state, tailnet-only Serve HTTPS, Funnel disabled, exact
   `http://127.0.0.1:8765` backend, and absence of a non-loopback Core listener. Review the
   admin-console grant to intended devices on TCP 443. See `PHASE_8D_DEPLOYMENT.md`.
3. Record whether Serve is already configured and whether the Phase 8D deployment marker exists.
   An existing route without that marker is not owned by the Phase 8D launcher. Do not run its
   `Run` or `Stop` action over an unowned route.
4. Keep Core bound to loopback. Verify the HTTPS status endpoint requires application auth.
5. Use the repository's working Python environment. The workstation's standard `.venv` currently
   has a `cryptography.exceptions` import failure; the `.bootstrap-venv` interpreter passed import
   and prior full-suite gates. Reverify before live use.

## Provisional Expo Go matrix

After ticket approval, create one five-minute v2 phone ticket locally with exact Tailscale HTTPS
origin, `client.status.read` only, and risk ceiling 0. Show its JSON only in a trusted local
terminal; scan or paste it directly into the physical iPhone. Never reuse or retransmit a ticket.

| Check | Expected evidence |
| --- | --- |
| Fresh pair | One phone device enrolled at v2 and bound to exact HTTPS origin; signed session uses only `client.status.read` |
| Signed status | **Check Core status** succeeds; local audit records allowed scoped access |
| Logout | **Log out session** revokes current session, retains device identity; next status creates a new signed session |
| Wi-Fi to cellular and back | Status works through Tailscale HTTPS on each network after connection settles |
| Tailscale off/on | Status fails closed while disconnected, then succeeds after reconnect |
| Core restart | Status fails while Core is down, then recreates a session or succeeds after restart |
| Revocation | Trusted-local `jarvis remote revoke` for the exact phone ID invalidates the next request; local erase still works |
| Lost-phone drill | Revoke locally, confirm audit, remove phone from tailnet, then verify access remains denied |

Do not claim pass from a rendered UI alone. Record sanitized pass/fail, elapsed times where relevant,
Core/Tailscale/Expo versions, network type, audit reason codes, and any recovery steps in
`phase-reports/MOBILE_M2_PROGRESS.md`. The owner operates the physical phone. If pairing fails,
do not create another ticket without fresh approval.

## Native build and rotation gate

Before production-style M2C closeout, obtain separate development-build authorization. Confirm
the `jarvis-mobile` scheme, camera permission behavior, SecureStore identity after app restart,
and absence of credentials in links or logs on that build. The current pairing client requests only
`client.status.read`; native key rotation needs a reviewed `key.rotate` flow and a separately
approved ticket carrying that scope. Core's existing rotation tests do not substitute for a live
native rotation result. Keep M2C open until required rotation and lost-phone evidence is recorded.

## Recovery

If the phone is lost or a key may be exposed, use the trusted-local Core inventory to identify the
exact device, revoke it with the CLI's matching `--confirm-device-id`, inspect sanitized audit, and
remove the phone from the tailnet. A fresh ticket and a new local key are required for re-enrollment.
Do not alter an unowned Serve route during cleanup.

## Primary Expo references

- [Expo linking scheme and new-build requirement](https://docs.expo.dev/linking/into-your-app/)
- [Expo Go and development-build differences](https://docs.expo.dev/develop/development-builds/faq/)
- [Physical iOS development build and signing prerequisites](https://docs.expo.dev/tutorial/eas/ios-development-build-for-devices/)
