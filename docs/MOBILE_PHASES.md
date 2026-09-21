# JARVIS Native Mobile Phases

Updated: 2026-09-20

## Execution rule

Execute one subphase per session. Each subphase has one objective, targeted and release-gate
evidence, a progress/completion report, an isolated safe commit, and an explicit stop. Preserve all
unrelated work. External accounts, paid services, cloud builds, signing, deployments, and provider
applications require fresh authority.

## Dependency order

1. M1A: Expo workspace and offline-safe shell.
2. M1B: mobile quality and CI gate.
3. M2A-M2C: authority-bound native authentication and live iPhone/Tailscale acceptance.
4. M3A-M3B: accessible design system and authenticated app shell.
5. M4A-M4C: conversation/history/cancellation API and native chat parity.
6. M5A-M5E: foreground voice, photo, and file input.
7. M6A-M6C: explicitly authorized generic push notifications.
8. M7A-M9B: consented phone context, widgets, and bounded low-risk action proposals.
9. H1A-H8C: provider-neutral health ingestion, deterministic analytics, local-private reasoning,
   mobile health UI, reports, and bounded proactivity.

The decision-complete scope, gates, exclusions, and acceptance criteria remain defined by the
approved JARVIS Native Mobile Architecture and Execution Plan. M1A does not pull M1B or M2 work
forward.
