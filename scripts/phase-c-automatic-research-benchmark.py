"""Fixed Phase C routing and volatile projection benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from jarvis.core import FreshnessDecision, FreshnessRoute  # noqa: E402
from jarvis.freshness_router import DeterministicFreshnessRouter  # noqa: E402
from jarvis.research import (  # noqa: E402
    AutomaticResearchProjector,
    Citation,
    ClaimStatus,
    ResearchClaim,
    ResearchErrorCode,
    ResearchReport,
    ResearchSearchError,
    SourceRecord,
)

NOW = datetime(2026, 9, 16, 15, tzinfo=UTC)
TARGET_P95_MS = 5.0


class FixtureWorkflow:
    def __init__(self) -> None:
        self.calls = 0
        self.report = _report("host-benchmark")
        self.persistence_writes = 0
        self.authority_events = 0

    async def run_volatile(self, *, host_id: str, plan: object) -> object:
        self.calls += 1
        return type("Run", (), {"report": self.report})()


def _report(host_id: str) -> ResearchReport:
    sources = tuple(
        SourceRecord(
            id=f"source-{index}",
            host_id=host_id,
            url=f"https://independent-{index}.example/current",
            publisher=f"independent-{index}.example",
            title=f"Current source {index}",
            topic="Current fixture",
            media_type="text/plain",
            content_sha256=f"{index}" * 64,
            extracted_text=f"Current fixture evidence {index}.",
            retrieved_at=NOW,
            published_at=NOW,
            last_checked_at=NOW,
        )
        for index in (1, 2)
    )
    claims = tuple(
        ResearchClaim(
            id=f"claim-{index}",
            statement=f"Current fixture claim {index}.",
            status=ClaimStatus.VERIFIED,
            citations=(
                Citation(
                    source_id=source.id,
                    locator="text:0-7",
                    quote="Current",
                ),
            ),
        )
        for index, source in enumerate(sources, start=1)
    )
    return ResearchReport(
        objective="Current fixture",
        answer=(
            "Current fixture claim 1. [source:source-1]\n\n"
            "Current fixture claim 2. [source:source-2]"
        ),
        sources=sources,
        claims=claims,
        generated_at=NOW,
    )


def _cases() -> tuple[tuple[str, FreshnessRoute], ...]:
    templates = (
        ("Explain photosynthesis fixture {index}.", FreshnessRoute.STATIC),
        ("What time is it for fixture {index}?", FreshnessRoute.LOCAL_CONTEXT),
        ("What is the latest Python version for fixture {index}?", FreshnessRoute.WEB_REQUIRED),
        ("Read my unread email fixture {index}.", FreshnessRoute.PERSONAL_DATA_REQUIRED),
        (
            "Compare current laptop prices using independent sources fixture {index}.",
            FreshnessRoute.MULTI_SOURCE,
        ),
    )
    return tuple(
        (template.format(index=index), expected)
        for index in range(20)
        for template, expected in templates
    )


async def _run() -> dict[str, object]:
    router = DeterministicFreshnessRouter()
    workflow = FixtureWorkflow()
    projector = AutomaticResearchProjector(workflow, host_id="host-benchmark")  # type: ignore[arg-type]
    failures: list[str] = []
    projection_latencies_ms: list[float] = []
    live_cases = 0
    privacy_violations = 0

    for query, expected in _cases():
        decision = router.classify(query)
        if decision.route is not expected:
            failures.append(f"route:{expected.value}->{decision.route.value}")
            continue
        if decision.requires_live_evidence:
            live_cases += 1
            projection = await projector.project(query, decision)
            started = time.perf_counter()
            projected_again = projector.render(workflow.report, decision)
            projection_latencies_ms.append((time.perf_counter() - started) * 1_000)
            if projected_again.content != projection.content:
                failures.append("projection:unstable")
            if "evidence_status=sufficient" not in projection.content:
                failures.append("evidence:insufficient")
            if len(projection.content) > 20_000:
                failures.append("projection:oversize")
        elif decision.route is FreshnessRoute.PERSONAL_DATA_REQUIRED:
            calls_before = workflow.calls
            try:
                await projector.project(
                    query,
                    FreshnessDecision(
                        route=FreshnessRoute.WEB_REQUIRED,
                        reason="Benchmark privacy probe.",
                    ),
                )
            except ResearchSearchError as exc:
                if exc.code is not ResearchErrorCode.PRIVACY_DENIED:
                    failures.append("privacy:wrong-denial")
            else:
                failures.append("privacy:missing-denial")
            if workflow.calls != calls_before:
                privacy_violations += 1

    ordered = sorted(projection_latencies_ms)
    p95_index = max(0, int(len(ordered) * 0.95 + 0.999999) - 1)
    p95 = ordered[p95_index]
    checks = {
        "all_routes_correct": not any(item.startswith("route:") for item in failures),
        "only_live_routes_researched": workflow.calls == live_cases == 40,
        "privacy_violations": privacy_violations,
        "persistence_writes": workflow.persistence_writes,
        "authority_events": workflow.authority_events,
        "projection_failures": len(failures),
        "projection_p95_under_target": p95 < TARGET_P95_MS,
    }
    passed = all(value if isinstance(value, bool) else value == 0 for value in checks.values())
    return {
        "format": "jarvis-phase-c-automatic-research-benchmark-v1",
        "cases": len(_cases()),
        "live_research_cases": live_cases,
        "research_calls": workflow.calls,
        "projection_p50_ms": statistics.median(ordered),
        "projection_p95_ms": p95,
        "projection_max_ms": max(ordered),
        "target_projection_p95_ms": TARGET_P95_MS,
        "failures": failures,
        "checks": checks,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(_run())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.enforce and not result["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
