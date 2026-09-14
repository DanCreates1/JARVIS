# Suggestion-only proactivity

Status: Phase 11A implemented; Phase 11B runner not implemented
Last verified: 2026-09-14

Phase 11A stores and evaluates bounded trigger policy. It can create an inert suggestion candidate.
It cannot execute a task, call a provider or tool, create an approval, send a notification, retain
candidate content, or authorize an effect. No background runner is installed.

## Safety boundary

- Global proactivity is disabled by default. Each feature also needs an exact host allowlist entry.
- Model, research, API, and event input remains untrusted proposal data.
- A draft becomes active only through an exact, short-lived trusted-local-terminal activation bound
  to rule ID, version, and SHA-256 proposal digest.
- Activation starts no runner. Policy evaluation is an internal library boundary for Phase 11B.
- Fixed host ceilings override lower rule budgets: 6 candidates/hour, 24/day, 300 seconds of
  attention/day, 30-day rule lifetime, 300-second clock skew, one candidate at a time, and zero
  cloud cost.
- Candidate rows contain only IDs, feature, timestamps, occurrence digest, and attention estimate.
- Disabling is immediate. Deletion removes the rule, activation records, candidates, and lifecycle
  events, leaving only a content-free tombstone.

## Configuration

Keep the global gate off until a future phase supplies and validates a runner:

```dotenv
JARVIS_PROACTIVITY_ENABLED=false
JARVIS_PROACTIVITY_ENABLED_FEATURES=[]
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
Cost must remain `0` and concurrency must remain `1`.

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

1. Set `JARVIS_PROACTIVITY_ENABLED=false` and restart the invoking process.
2. Inspect `jarvis proactive list`, `show`, and `events`.
3. Disable the exact active rule with its current version.
4. Export before deletion if evidence or portability is needed.
5. Run `uv run jarvis doctor`; its proactivity row must report suggestion-only mode and no runner.

Database corruption fails closed. Restore the main JARVIS database only from a verified backup;
never edit authority rows manually.
