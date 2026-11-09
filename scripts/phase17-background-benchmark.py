"""Synthetic current background-worker simulation, incidents, resource soak and removal.

Uses fresh temporary canonical state under ignored runtime; never production settings.
Short runs cannot satisfy --enforce. No provider, broker or notification transport exists here.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sqlite3
import tempfile
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from jarvis.proactivity import (
    ForegroundProactivityRunner,
    HostProactivityPolicy,
    ProactivityProposal,
    ProactivityProvenance,
    SQLiteProactivityRunnerStore,
    SQLiteProactivityStore,
    TriggerSchedule,
    TrustedActivation,
)
from jarvis.proactivity.worker import BoundedProactivityWorker
from jarvis.proactivity.worker_models import WorkerDeniedError, WorkerPlan, policy_digest
from jarvis.proactivity.worker_store import SQLiteProactivityWorkerStore

ROOT = Path(__file__).resolve().parents[1]
HOST = "host:phase17-benchmark"
FEATURE = "task.checkin"
POLICY = HostProactivityPolicy(enabled=True, enabled_features=frozenset({FEATURE}))


def _legacy():
    spec = importlib.util.spec_from_file_location(
        "phase17_retained_policy_oracle", ROOT / "scripts/phase11d-long-duration-benchmark.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plan(now, generation=0, *, ticks=3_600):
    return WorkerPlan(
        host_id=HOST,
        expected_generation=generation,
        policy_sha256=policy_digest(POLICY),
        features=(FEATURE,),
        created_at=now,
        expires_at=now + timedelta(seconds=3_600),
        poll_seconds=1,
        max_ticks=ticks,
    )


async def _incidents(database: Path, samples: int) -> dict:
    denied = 0
    async with (
        SQLiteProactivityWorkerStore(database) as first,
        SQLiteProactivityWorkerStore(database) as second,
    ):
        for _ in range(samples):
            state = await first.status(host_id=HOST)
            p = _plan(datetime.now(UTC), int(state["generation"]))
            await first.enable(p)
            _, old = await first.claim(host_id=HOST)
            try:
                await second.claim(host_id=HOST)
            except WorkerDeniedError:
                denied += 1
            else:
                raise AssertionError("split worker ownership")
            await second.stop(host_id=HOST)
            for action in (first.check(old), first.reserve_tick(old, p), first.enable(p)):
                try:
                    await action
                except WorkerDeniedError:
                    denied += 1
                else:
                    raise AssertionError("stale worker authority accepted")
            await first.release(old)
    return {"incidents": samples, "expected_denials": samples * 4, "actual_denials": denied}


async def _seed(database: Path, cycles: int) -> list[str]:
    now = datetime.now(UTC)
    ids = []
    offsets = (2, 610, 1_220) if cycles >= 1_800 else (0.1,)
    async with SQLiteProactivityStore(database) as store:
        for offset in offsets:
            due = now + timedelta(seconds=offset)
            proposal = ProactivityProposal(
                title="PRIVATE-PHASE17-CANARY not for notification preview",
                feature=FEATURE,
                schedule=TriggerSchedule(
                    kind="once",
                    timezone="UTC",
                    local_date=due.date(),
                    local_time=due.time().replace(tzinfo=None),
                ),
                provenance=ProactivityProvenance(source_type="test", source_id="benchmark:17"),
                budget={"max_candidates_per_hour": 6, "max_candidates_per_day": 24},
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
            draft = await store.create_rule(host_id=HOST, preview=POLICY.preview(proposal, now=now))
            await store.activate(
                TrustedActivation(
                    approval_id=f"activation:{draft.id}",
                    host_id=HOST,
                    rule_id=draft.id,
                    expected_version=1,
                    expected_proposal_sha256=draft.proposal_sha256,
                    approved_at=now,
                    expires_at=now + timedelta(minutes=1),
                ),
                policy=POLICY,
                now=now,
            )
            ids.append(draft.id)
    return ids


async def measure(*, cycles=1_800, enforce=False) -> dict:
    evidence = ROOT / "runtime/phase17"
    evidence.mkdir(parents=True, exist_ok=True)
    legacy = _legacy()
    simulation = legacy._simulate(virtual_days=30, decision_samples=1_000)
    timings = []
    original_tick = ForegroundProactivityRunner.tick
    peak = start_rss = legacy._rss_bytes()

    async def measured_tick(self, **kwargs):
        nonlocal peak
        started = time.perf_counter()
        result = await original_tick(self, **kwargs)
        timings.append((time.perf_counter() - started) * 1_000)
        peak = max(peak, legacy._rss_bytes())
        return result

    with tempfile.TemporaryDirectory(prefix="background-", dir=evidence) as temp:
        database = Path(temp) / "core.db"
        incidents = await _incidents(database, 100)
        ids = await _seed(database, cycles)
        async with SQLiteProactivityWorkerStore(database) as store:
            state = await store.status(host_id=HOST)
            await store.enable(_plan(datetime.now(UTC), int(state["generation"]), ticks=cycles))
        started = time.perf_counter()
        cpu = time.process_time()
        with patch.object(ForegroundProactivityRunner, "tick", measured_tick):
            result = await BoundedProactivityWorker(
                database,
                host_id=HOST,
                policy_supplier=lambda: (POLICY, True),
            ).run()
        elapsed = time.perf_counter() - started
        cpu_percent = (time.process_time() - cpu) / elapsed * 100
        with closing(sqlite3.connect(database)) as connection:
            candidates = connection.execute(
                "SELECT COUNT(*) FROM proactivity_candidates"
            ).fetchone()[0]
            notices = connection.execute(
                "SELECT COUNT(*) FROM proactivity_notifications"
            ).fetchone()[0]
            assert candidates == notices == result.inbox_items
            for table in (
                "proactivity_candidates",
                "proactivity_dispatches",
                "proactivity_notifications",
                "proactivity_runner_events",
                "proactivity_worker_controls",
            ):
                assert "PRIVATE-PHASE17-CANARY" not in repr(
                    connection.execute(f"SELECT * FROM {table}").fetchall()
                )
            assert connection.execute("SELECT COUNT(*) FROM planning_tasks").fetchone()[0] == 0
        async with (
            SQLiteProactivityWorkerStore(database) as store,
            SQLiteProactivityStore(database) as rules,
            SQLiteProactivityRunnerStore(database) as inbox,
        ):
            await store.stop(host_id=HOST)
            for rule_id in ids:
                await rules.delete_rule(host_id=HOST, rule_id=rule_id)
            assert not (await store.status(host_id=HOST))["enabled"]
            assert not await rules.list_candidates(host_id=HOST)
            assert not await inbox.list_notifications(host_id=HOST)
        core_ok = await legacy._on_demand_core(database)
        with closing(sqlite3.connect(database)) as connection:
            assert (
                connection.execute("SELECT plan_json FROM proactivity_worker_controls").fetchone()[
                    0
                ]
                is None
            )
    minimums = cycles >= 1_800 and result.ticks >= 1_800 and elapsed >= 1_800
    p95 = legacy._percentile(timings, 0.95)
    growth = max(0, peak - start_rss) / (1024 * 1024)
    passed = (
        simulation["oracle_agreement"] == 1.0
        and incidents["actual_denials"] == incidents["expected_denials"]
        and result.ticks == cycles
        and core_ok
        and (cycles < 1_800 or result.inbox_items == 3)
        and p95 <= 50
        and growth <= 50
        and cpu_percent <= 5
        and (minimums or not enforce)
    )
    return {
        "passed": passed,
        "minimums_met": minimums,
        "simulation": simulation,
        "worker_incidents": incidents,
        "soak": {
            "seconds": elapsed,
            "ticks": result.ticks,
            "reason": result.reason,
            "inbox_items": result.inbox_items,
            "tick_p95_ms": p95,
            "average_cpu_one_core_percent": cpu_percent,
            "rss_growth_mib": growth,
        },
        "on_demand_core_passed": core_ok,
        "rule_and_worker_plan_removed": True,
        "temporary_state_deleted": not await asyncio.to_thread(Path(temp).exists),
        "zero_activity": {
            "providers": 0,
            "tools": 0,
            "tasks": 0,
            "effects": 0,
            "external_sends": 0,
            "cloud_cost_usd": 0,
            "private_previews": 0,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=1_800)
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to((ROOT / "runtime").resolve())
    if not 1 <= args.cycles <= 3_600:
        parser.error("cycles must be 1 through 3600")
    result = asyncio.run(measure(cycles=args.cycles, enforce=args.enforce))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
