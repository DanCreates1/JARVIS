# Bounded foreground proactivity

Status: Phases 11A–11C implemented; Phase 11D long-duration evaluation remains
Last verified: 2026-09-14

Phase 11A stores and evaluates bounded trigger policy. Phase 11B adds an explicit foreground tick,
a generic local inbox, snooze/dismiss/cancel, bounded crash recovery, and an optional exact Phase 6
task handoff. Phase 11C adds durable candidate ownership and one approved adapter: the existing
authenticated Phase 8 PWA/API. A tick runs only when the operator invokes it. Handoffs change
metadata but never start a task. No background daemon or external notification sender is installed.

## Safety boundary

- Global proactivity is disabled by default. Each feature also needs an exact host allowlist entry.
- Model, research, API, and event input remains untrusted proposal data.
- A draft becomes active only through an exact, short-lived trusted-local-terminal activation bound
  to rule ID, version, and SHA-256 proposal digest.
- Activation starts no runner. `jarvis proactive tick` is the only implemented runner entry point.
- Fixed host ceilings override lower rule budgets: 6 candidates/hour, 24/day, 300 seconds of
  attention/day, 30-day rule lifetime, 300-second clock skew, one candidate at a time, and zero
  cloud cost.
- Candidate, dispatch, inbox, and runner-event rows contain only control metadata. They exclude
  titles, prompts, task arguments/results, provider content, tool receipts, and approval grants.
- One candidate has one durable dispatch and one inbox item. A 1–60 second lease allows one owner.
  Expired leases recover up to ten attempts; exhaustion fails terminally.
- Each ready candidate has exactly one durable owner. Local ownership is unleased. Device ownership
  is a 30–300 second renewable lease guarded by optimistic compare-and-swap. Expiry returns ownership
  locally; stale devices cannot renew, release, or hand off it.
- PWA access requires all gates: global policy, process adapter, persistent trusted-local enable,
  exact `jarvis-api` audience, active enrolled identity, session scopes, and active feature binding.
  Manage operations require both `client.proactivity.read` and `client.proactivity.manage`.
- Accept requires the exact host-owned task ID named by the activated rule, current task
  version/digest, safe task state/deadline, and intersected Phase 6/11 budgets. It creates no fresh
  grant, binds no existing grant, executes no node, and authorizes no effect.
- Disabling is immediate and cancels unhanded dispatches/inbox items. Deletion removes the rule,
  activation, candidate, dispatch, inbox, and event rows, leaving one content-free tombstone.

## Configuration

All three capability gates default off:

```dotenv
JARVIS_PROACTIVITY_ENABLED=false
JARVIS_PROACTIVITY_ENABLED_FEATURES=[]
JARVIS_PROACTIVITY_RUNNER_ENABLED=false
JARVIS_PROACTIVITY_TASK_HANDOFF_ENABLED=false
JARVIS_PROACTIVITY_PWA_ADAPTER_ENABLED=false
JARVIS_PROACTIVITY_DEVICE_LEASE_SECONDS=60
JARVIS_PROACTIVITY_RUNNER_LEASE_SECONDS=30
JARVIS_PROACTIVITY_NOTIFICATION_TTL_SECONDS=3600
JARVIS_PROACTIVITY_MAX_SNOOZE_SECONDS=86400
JARVIS_PROACTIVITY_MAX_CANDIDATES_PER_HOUR=6
JARVIS_PROACTIVITY_MAX_CANDIDATES_PER_DAY=24
JARVIS_PROACTIVITY_MAX_ATTENTION_SECONDS_PER_DAY=300
JARVIS_PROACTIVITY_MAX_RULE_LIFETIME_DAYS=30
JARVIS_PROACTIVITY_CLOCK_SKEW_SECONDS=300
JARVIS_PROACTIVITY_MAX_TASK_STEPS=10
JARVIS_PROACTIVITY_MAX_PROVIDER_REQUESTS=2
JARVIS_PROACTIVITY_MAX_TOOL_CALLS=5
JARVIS_PROACTIVITY_MAX_TOKENS=10000
JARVIS_PROACTIVITY_MAX_COST_USD=0
JARVIS_PROACTIVITY_MAX_CONCURRENCY=1
```

`JARVIS_PROACTIVITY_ENABLED_FEATURES` is a JSON array such as
`["task.checkin","device.health"]`. An empty list denies every feature even if the global gate is enabled.
Cost must remain `0` and concurrency must remain `1`. Enabling policy alone does not enable ticks;
enabling the runner does not enable task handoff or the PWA adapter. The process adapter gate also
does not replace persistent trusted-local enablement or exact device binding.

## Scoped PWA ownership adapter

Enroll only the intended browser/phone with the Phase 8C scopes plus:

```powershell
uv run jarvis remote enroll "My PWA" --type browser `
  --scope browser.session --scope events.read --scope session.revoke `
  --scope client.status.read --scope client.tasks.read --scope client.chat `
  --scope client.proactivity.read --scope client.proactivity.manage --risk-ceiling 1
```

Set `JARVIS_PROACTIVITY_PWA_ADAPTER_ENABLED=true`, while keeping the global feature allowlist exact.
Then, from the trusted local terminal, enable and bind one device/feature:

```powershell
uv run jarvis proactive adapter-enable --confirm "ENABLE PWA PROACTIVITY"
uv run jarvis proactive device-bind <device-id> --feature task.checkin --allow-manage `
  --minutes 1440 --confirm-device-id <device-id>
uv run jarvis proactive ownership
```

Authenticated PWA routes expose only candidate ID, feature, dispatch/notification state, generic
owner relation, version, and expiry:

```text
GET  /api/v1/client/proactivity
POST /api/v1/client/proactivity/{candidate}/claim
POST /api/v1/client/proactivity/{candidate}/renew
POST /api/v1/client/proactivity/{candidate}/release
POST /api/v1/client/proactivity/{candidate}/handoff
```

Every mutation supplies the current `expected_version`; handoff also supplies one exact bound
`target_device_id`. HTTP 409 means ownership changed and the caller must refresh. The adapter does
not expose notification text, title, prompt, task data, memory/research data, approval, destination,
provider/tool data, credential, or effect authority. It does not implement push.

Trusted-local recovery and ownership operations:

```powershell
uv run jarvis proactive owner-handoff <candidate-id> --target-device-id <device-id> `
  --expected-version <version>
uv run jarvis proactive owner-reclaim <candidate-id> --expected-version <version>
uv run jarvis proactive device-unbind <device-id> --feature task.checkin `
  --expected-version <binding-version>
uv run jarvis proactive adapter-disable
```

Binding revocation, device revocation, and `adapter-disable` immediately reclaim matching ownership
to the local host. Device disconnect requires no discovery or callback: its short lease expires and
the next ownership read/mutation reclaims locally.

## Create and activate a rule

Create `proposal.json` with explicit IANA timezone and expiry. `weekdays` uses Monday `0` through
Sunday `6`.

```json
{
  "title": "Daily task check-in",
  "feature": "task.checkin",
  "schedule": {
    "kind": "daily",
    "timezone": "America/Toronto",
    "local_date": null,
    "local_time": "09:00:00",
    "fold": 0,
    "event_name": null
  },
  "quiet_hours": [
    {
      "start": "22:00:00",
      "end": "07:00:00",
      "weekdays": [0, 1, 2, 3, 4, 5, 6]
    }
  ],
  "budget": {
    "max_candidates_per_hour": 1,
    "max_candidates_per_day": 1,
    "max_attention_seconds_per_day": 30,
    "max_task_steps": 0,
    "max_provider_requests": 0,
    "max_tool_calls": 0,
    "max_tokens": 0,
    "max_cost_usd": 0,
    "max_concurrency": 1
  },
  "scope": {
    "data_classes": ["task_state"],
    "task_template_id": null,
    "cloud_disclosure_allowed": false,
    "effect_execution_allowed": false,
    "notification_send_allowed": false,
    "approval_creation_allowed": false,
    "retains_candidate_content": false
  },
  "estimated_attention_seconds": 15,
  "provenance": {
    "source_type": "host",
    "source_id": "source:local-operator",
    "untrusted": true
  },
  "created_at": "2026-09-14T14:00:00Z",
  "expires_at": "2026-10-14T14:00:00Z"
}
```

Preview and persist the draft:

```powershell
uv run jarvis proactive create .\proposal.json
uv run jarvis proactive show <rule-id>
```

Read the displayed version, digest, and confirmation phrase. Activate that exact preview:

```powershell
uv run jarvis proactive activate <rule-id> `
  --expected-version 1 `
  --expected-digest <64-character-sha256> `
  --confirm "ACTIVATE <displayed-suffix>"
```

Any stale version, changed digest, replayed approval, expired approval, wrong host, invalid timezone,
DST gap, excessive lifetime, or excessive budget is denied. Activation still starts nothing.

## Run one foreground tick

After explicitly enabling the global, feature, and runner gates, invoke one bounded pass:

```powershell
uv run jarvis proactive tick
uv run jarvis proactive inbox --active-only
```

For an event rule, all three event fields are mandatory:

```powershell
uv run jarvis proactive tick --event-name task.changed --event-id event-123 `
  --occurred-at 2026-09-14T14:00:00-04:00
```

The tick evaluates active rules, claims at most one candidate, rechecks current policy/quiet time,
and makes one generic local inbox item ready. It does not call providers, tools, the Phase 6 task
scheduler, browser push, PWA notifications, email, SMS, or cloud services.

## Inbox feedback and optional task handoff

Use the exact candidate ID and current dispatch version shown by `inbox`:

```powershell
uv run jarvis proactive runner-events <candidate-id>
uv run jarvis proactive snooze <candidate-id> --expected-version <version> --minutes 15
uv run jarvis proactive dismiss <candidate-id> --expected-version <version>
uv run jarvis proactive cancel <candidate-id> --expected-version <version>
uv run jarvis proactive accept <candidate-id> --task-id <exact-task-id> `
  --expected-version <version>
```

Snooze is bounded by the configured ceiling and notification expiry. Dismiss/cancel is terminal.
Accept also requires `JARVIS_PROACTIVITY_TASK_HANDOFF_ENABLED=true`; it records one handoff only.
Run or approve the task later through the existing Phase 6 trusted workflow.

## Inspect, disable, export, and delete

```powershell
uv run jarvis proactive status
uv run jarvis proactive list
uv run jarvis proactive show <rule-id>
uv run jarvis proactive events <rule-id>
uv run jarvis proactive disable <rule-id> --expected-version <version>
uv run jarvis proactive export .\proactivity-export.json
uv run jarvis proactive delete <rule-id> --confirm-rule-id <rule-id>
```

Export refuses overwrite. It is an inspection/portability artifact, not an automatic restore path.
Export before deletion if recovery may matter.

## Time behavior

All durable timestamps are normalized to UTC. Schedules use an IANA timezone and naive local wall
time. Nonexistent local times during a daylight-saving gap are invalid. Ambiguous repeated times
require `fold: 0` for the earlier instant or `fold: 1` for the later instant. Occurrence digests and
transactional uniqueness prevent duplicate candidates across retries and restart.

## Recovery

1. Run `uv run jarvis proactive adapter-disable`; then set
   `JARVIS_PROACTIVITY_PWA_ADAPTER_ENABLED=false`.
2. Set `JARVIS_PROACTIVITY_RUNNER_ENABLED=false` and
   `JARVIS_PROACTIVITY_TASK_HANDOFF_ENABLED=false`; stop the invoking foreground command.
3. Set `JARVIS_PROACTIVITY_ENABLED=false` to deny new candidate evaluation.
4. Inspect `proactive ownership`, `inbox`, `runner-events`, `list`, `show`, and `events`.
5. Revoke a lost device with `jarvis remote revoke`; its bindings and ownership are reclaimed.
6. Disable the exact active rule with its current version; unhanded runner state becomes cancelled.
7. Export before deletion if evidence or portability is needed.
8. Run `uv run jarvis doctor`; it must report runner, handoff, and process adapter gates disabled.

Database corruption fails closed. Restore the main JARVIS database only from a verified backup;
never edit authority rows manually. Expired pre-delivery leases are reclaimed by the next explicit
tick; expired device ownership leases are reclaimed by the next ownership operation. Already-
notified, handed-off, dismissed, cancelled, expired, or failed candidates are never redelivered.
