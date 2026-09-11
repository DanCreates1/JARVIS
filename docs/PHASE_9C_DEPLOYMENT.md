# Phase 9C Deployment, Resilience, and Recovery

Phase 9C makes remote-core placement executable but never automatic. Local-only remains default.
A server process fails before opening SQLite or a listener unless exact release, Python version,
topology, deployment manifest, activation state, ownership receipt, database path, and one-owner
assignment agree. Only one core replica is supported.

Repository implementation and deterministic chaos gates pass locally. A real dedicated-server
cutover is not authorized by repository work. It requires separate authority for the named host,
Tailscale policy, systemd installation, data transfer, service start, firewall checks, and rollback.

## Deployment contract

Four immutable control documents and one artifact form the startup chain:

1. Phase 9A topology manifest: exact profile, epoch, nodes, capabilities, and one owner per domain.
2. Phase 9B cutover or rollback receipt: exact accepted database state and active owner.
3. Phase 9C deployment manifest: role, node, artifact SHA-256, Python patch version, database path,
   topology digest, ownership receipt digest, loopback listener, resource limits, and hardening.
4. Phase 9C deployment-state receipt: monotonic activation/update/rollback transition binding the
   prior documents and verified database.
5. Pinned wheel or source archive whose bytes match the deployment manifest.

The expected deployment and state digests live in root-owned service configuration. Editing a
document changes its canonical digest and blocks startup. A valid first activation receipt permits
normal database growth after activation; it does not require the live database to remain frozen at
the original snapshot. Owner, path, schema/integrity, release, topology, and receipt bindings still
revalidate on every process start.

## Hardening baseline

Use [jarvis-core.service](../deploy/phase9c/jarvis-core.service) unchanged unless a reviewed manifest
and security review update the matching controls. It enforces:

- fixed non-root `jarvis` identity, root-owned configuration, and private state/runtime directories;
- one process/replica, loopback `127.0.0.1:8765`, and no direct public listener;
- read-only system tree, protected home/kernel/device namespaces, private temporary storage,
  no-new-privileges, and empty ambient/capability bounding sets;
- native syscall architecture and only Unix/IPv4/IPv6 address families; and
- 256 tasks, 2 GiB memory, no swap, 200% CPU, and 1,024 open-file ceilings.

Do not enable a second core. SQLite replay/session/rate/task state is process-owned and no shared
coordination layer exists. Multi-replica deployment is fail-closed deferred scope.

Tailscale Serve is the sole HTTPS gateway. It proxies only to loopback. Funnel, public DNS proxying,
port forwarding, router exposure, and direct Ollama/admin/broker listeners are prohibited. Tailscale
documents that Serve is tailnet-only and supports a localhost HTTP proxy; keep the upstream on
localhost so untrusted peers cannot spoof identity headers:

- <https://tailscale.com/docs/features/tailscale-serve>
- <https://tailscale.com/docs/reference/tailscale-cli/serve>

## Server preflight

Before copying state or starting a service, record and review:

- supported Linux distribution with systemd and Python matching the manifest patch version;
- `uv sync --locked` succeeds from reviewed source with no lock change;
- Tailscale is authenticated to the intended tailnet and ACL/grants allow only approved devices;
- inbound firewall has no JARVIS, Ollama, database, debug, SSH-from-public, or admin port exception;
- `/opt/jarvis/releases`, `/etc/jarvis`, and `/var/lib/jarvis` have adequate space; and
- current local core is stopped before final Phase 9B comparison and ownership receipt creation.

Container runtime is not installed on the current validation host. Native systemd is the supported
9C deployment path. Container image build/runtime proof remains an explicit target-host or CI gate;
do not claim it from this workstation.

## Prepare and activate

Commands below are operator examples. Use private paths, exact digests, and the Phase 9B runbook.
They never deploy or contact a server themselves.

Create a remote deployment manifest after the restored database and cutover receipt exist:

```bash
uv run jarvis remote deployment manifest /srv/jarvis-private/deployment.json \
  --topology /srv/jarvis-private/topology.json \
  --release /srv/jarvis-private/jarvis-0.1.0-py3-none-any.whl \
  --role server-core --node-id node:server \
  --database /var/lib/jarvis/jarvis.db \
  --ownership-receipt /srv/jarvis-private/cutover.json
```

Review the JSON and record only the printed `deployment_manifest_sha256`. Then create activation
state. This rechecks the exact accepted snapshot and writes a new file only:

```bash
uv run jarvis remote deployment activate /srv/jarvis-private/deployment-state.json \
  --manifest /srv/jarvis-private/deployment.json \
  --topology /srv/jarvis-private/topology.json \
  --release /srv/jarvis-private/jarvis-0.1.0-py3-none-any.whl \
  --database /var/lib/jarvis/jarvis.db \
  --ownership-receipt /srv/jarvis-private/cutover.json
```

Create the fixed `jarvis` system user with no login shell. Copy
[jarvis.env.example](../deploy/phase9c/jarvis.env.example) to `/etc/jarvis/jarvis.env`, replace both
zero digests and every placeholder, then set configuration files to `root:jarvis` and mode `0640`
inside a root-owned mode `0750` directory. Keep provider credentials outside tracked files; inject
them through reviewed host secret storage. Verify before
installing/enabling units:

```bash
uv run jarvis remote deployment verify \
  --manifest /etc/jarvis/deployment.json --manifest-sha256 "$DEPLOYMENT_SHA" \
  --state /etc/jarvis/deployment-state.json --state-sha256 "$STATE_SHA" \
  --topology /etc/jarvis/topology.json \
  --release /opt/jarvis/releases/$RELEASE_SHA/jarvis-0.1.0-py3-none-any.whl \
  --database /var/lib/jarvis/jarvis.db \
  --ownership-receipt /etc/jarvis/cutover-receipt.json
```

Under separately granted deployment authority, install the two reviewed units to
`/etc/systemd/system`, run `systemd-analyze verify`, `systemctl daemon-reload`, enable/start
`jarvis-core.service`, then enable/start `jarvis-tailscale-serve.service`. Do not use Tailscale
Funnel. Confirm Tailscale Serve maps HTTPS 443 to `http://127.0.0.1:8765`.

## Health, telemetry, and listener checks

Unauthenticated probes reveal status only:

- `GET /api/health/live` returns `{"status":"live"}` or HTTP 503;
- `GET /api/health/ready` returns `{"status":"ready"}` or HTTP 503; and
- `GET /api/health` is the compatibility readiness endpoint with the same minimal shape.

Internal telemetry has a fixed enum, bounded 16-1,024 event ring, counts, sample count, and p50/p95
latency only. It accepts no arbitrary label, path, identifier, request body, prompt, user content,
model/tool output, credential, or exception text.

After activation, verify:

```bash
curl --fail http://127.0.0.1:8765/api/health/live
curl --fail http://127.0.0.1:8765/api/health/ready
ss -lntup
tailscale serve status
systemctl show jarvis-core.service -p MainPID -p TasksCurrent -p MemoryCurrent
```

Expected: one JARVIS core PID, listener only on loopback 8765, private Tailscale HTTPS 443, no
database/Ollama/admin/broker listener, and no public reachability. Test approved-device access and
immediate revoked-device denial before enabling any normal use.

## Update and rollback

Stage an exact artifact. Existing digest directories are never overwritten:

```bash
uv run jarvis remote deployment stage jarvis-0.1.1-py3-none-any.whl \
  --release-root /opt/jarvis/releases --sha256 "$CANDIDATE_SHA"
```

Create a new deployment manifest and chained deployment-state receipt with `--previous-state` and
`--transition update`. Verify in a non-owning staging database/process. Promote only after the exact
artifact probe succeeds:

```bash
uv run jarvis remote deployment promote "$CANDIDATE_SHA" \
  --state /var/lib/jarvis/release-state.json \
  --release-root /opt/jarvis/releases \
  --expected-current-sha256 "$CURRENT_SHA"
```

Stop core, atomically switch `/opt/jarvis/current` to the verified release, update root-owned
manifest/state paths and digests, then restart. If readiness, protocol, migration, latency,
revocation, listener, or smoke checks fail, stop immediately and roll back:

```bash
uv run jarvis remote deployment rollback "$CANDIDATE_SHA" \
  --state /var/lib/jarvis/release-state.json \
  --release-root /opt/jarvis/releases
```

Restore the prior root-owned manifest/state/release link, restart one core, and verify readiness.
Promotion and rollback use compare-and-swap expected digests; stale operators cannot overwrite a
newer release decision. A failed probe leaves current state unchanged.

## Partition and offline behavior

Network loss never elects the laptop as shared owner. A laptop can execute only capabilities listed
in its topology node's `offline_capabilities`. Shared-state mutation and device effects are denied
while disconnected, even if a similarly named capability exists. Server core reports unavailable
when disconnected. Reconnect requires normal authenticated protocol negotiation; queued shared
writes or effects are not replayed implicitly.

## Disaster recovery

RPO is the exact accepted Phase 9B snapshot plus later backups produced under the documented backup
policy. Target RTO is 15 minutes with host, key, release, manifests, receipts, and snapshot ready.

For remote failure: stop the server writer, restore/verify the accepted database to a new local path,
build a higher-epoch local-only topology, compare exact logical state, and create the chained Phase
9B rollback receipt. Build a `local-core` deployment manifest consuming that rollback receipt,
create a chained Phase 9C rollback state, pin its digests in local configuration, then start exactly
one local core. Never start local core while remote writer may still run.

If server fencing cannot be proven, remain stopped and treat recovery as blocked. DNS/Tailscale
reachability does not prove writer shutdown. Preserve the failed release, service journal,
content-free receipts, and database snapshot until incident review; never upload private database
or credentials as telemetry.

## Fixed local acceptance

```powershell
uv run pytest --no-cov -q tests/unit/test_phase9_resilience.py `
  tests/security/test_phase9_resilience_security.py tests/integration/test_web.py
uv run python scripts/phase9c-resilience-benchmark.py `
  --output runtime/phase9c-resilience-benchmark.json
```

The benchmark requires 100 local-only and 100 split validations, at least 100 attempts per chaos
class, zero false activation/offline acceptance/bad-release acceptance/rollback mismatch/private
telemetry marker, placement p95 at most 10 ms, and RSS growth at most 50 MiB. Production gates also
require private request p95 at most 250 ms, revoked/kill denial within 5 seconds, RTO at most 15
minutes, and rollback within 5 minutes on the authorized server and laptop.
