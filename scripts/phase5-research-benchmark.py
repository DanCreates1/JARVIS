"""Reproducible Phase 5 citation, entailment, diversity, freshness, and latency benchmark."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from jarvis.research import (
    BoundedResearchOrchestrator,
    Citation,
    ClaimStatus,
    FetchedDocument,
    ResearchAnswerPoint,
    ResearchClaim,
    ResearchPlan,
    ResearchSynthesisDraft,
    SandboxedDocumentParser,
    SearchRequest,
    SearchResult,
)

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
RUNTIME_ROOT: Final = (REPOSITORY_ROOT / "runtime").resolve()
GOLDEN_PATH: Final = REPOSITORY_ROOT / "tests" / "fixtures" / "phase5_research_golden.json"
TARGETS: Final = {
    "citation_coverage": 1.0,
    "claim_entailment": 1.0,
    "source_diversity": 1.0,
    "freshness_awareness": 1.0,
    "conflict_handling": 1.0,
    "injection_resistance": 1.0,
    "reproducibility": 1.0,
    "failures": 0,
    "p95_ms": 2_000.0,
}


class FixtureSearchProvider:
    def __init__(self, task: dict[str, Any]) -> None:
        self._task = task

    async def search(self, request: SearchRequest) -> Sequence[SearchResult]:
        return tuple(
            SearchResult(
                url=source["url"],
                title=source["title"],
                publisher=source["publisher"],
                published_at=datetime.fromisoformat(source["published_at"]),
            )
            for source in self._task["sources"][: request.limit]
        )

    async def close(self) -> None:
        return None


class FixtureFetcher:
    def __init__(self, task: dict[str, Any], now: datetime) -> None:
        self._sources = {source["url"]: source for source in task["sources"]}
        self._now = now

    async def fetch(self, request):  # type: ignore[no-untyped-def]
        source = self._sources[request.url]
        published = source["published_at"]
        html = (
            f'<html lang="en"><head><title>{source["title"]}</title>'
            f'<meta name="publisher" content="{source["publisher"]}">'
            f'<meta property="article:published_time" content="{published}"></head>'
            f"<body><p>{source['text']}</p></body></html>"
        ).encode()
        return FetchedDocument(
            requested_url=request.url,
            final_url=request.url,
            media_type="text/html",
            body=html,
            retrieved_at=self._now,
            status_code=200,
        )

    async def close(self) -> None:
        return None


class FixtureSynthesizer:
    def __init__(self, task: dict[str, Any]) -> None:
        self._task = task

    async def synthesize(self, request):  # type: ignore[no-untyped-def]
        sources_by_url = {source.url: source for source in request.sources}
        claims: list[ResearchClaim] = []
        points: list[ResearchAnswerPoint] = []
        for definition in self._task["claims"]:
            citations: list[Citation] = []
            for url, quote in definition["citations"]:
                source = sources_by_url[url]
                start = source.extracted_text.index(quote)
                citations.append(
                    Citation(
                        source_id=source.id,
                        locator=f"text:{start}-{start + len(quote)}",
                        quote=quote,
                    )
                )
            claim = ResearchClaim(
                id=definition["id"],
                statement=definition["statement"],
                status=ClaimStatus(definition["status"]),
                citations=tuple(citations),
                uncertainty=definition.get("uncertainty", ""),
            )
            claims.append(claim)
            points.append(ResearchAnswerPoint(text=claim.statement, claim_ids=(claim.id,)))
        return ResearchSynthesisDraft(
            points=tuple(points),
            claims=tuple(claims),
            contradictions=tuple(self._task["contradictions"]),
        )

    async def close(self) -> None:
        return None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", default="results.json")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args(argv)
    if args.samples < 20:
        parser.error("--samples must be at least 20")
    if Path(args.output).name != args.output or not args.output.endswith(".json"):
        parser.error("--output must be a plain JSON filename")
    return args


def prepare_work_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    try:
        resolved.relative_to(RUNTIME_ROOT)
    except ValueError as exc:
        raise ValueError("work directory must be a new child of repository runtime/") from exc
    if resolved == RUNTIME_ROOT or resolved.exists() or resolved.is_symlink():
        raise FileExistsError("work directory must be a new non-link child of runtime/")
    resolved.mkdir(parents=True)
    return resolved


async def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    fixture = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    now = datetime.fromisoformat(fixture["as_of"]).astimezone(UTC)
    durations: list[float] = []
    reports = []
    failures = 0
    citation_total = 0
    material_total = 0
    entailed = 0
    diversity_passes = 0
    freshness_passes = 0
    conflict_passes = 0
    injection_passes = 0
    signatures: dict[str, set[str]] = {task["objective"]: set() for task in fixture["tasks"]}

    for index in range(args.samples):
        task = fixture["tasks"][index % len(fixture["tasks"])]
        parser = SandboxedDocumentParser()
        orchestrator = BoundedResearchOrchestrator(
            search_provider=FixtureSearchProvider(task),
            fetcher=FixtureFetcher(task, now),
            parser=parser,
            synthesizer=FixtureSynthesizer(task),
            clock=lambda: now,
        )
        started = time.perf_counter_ns()
        try:
            result = await orchestrator.run(
                host_id="host-phase5-benchmark",
                plan=ResearchPlan(
                    objective=task["objective"],
                    questions=(task["question"],),
                    max_sources=len(task["sources"]),
                    max_fetches=len(task["sources"]),
                ),
            )
        except Exception:
            failures += 1
            continue
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
        report = result.report
        reports.append(report)
        material = [claim for claim in report.claims if claim.is_material]
        material_total += len(material)
        citation_total += sum(bool(claim.citations) for claim in material)
        expected = {claim["statement"]: claim for claim in task["claims"]}
        entailed += sum(
            claim.statement in expected
            and all(
                citation.quote
                == next(
                    quote
                    for url, quote in expected[claim.statement]["citations"]
                    if url
                    == next(
                        source.url for source in report.sources if source.id == citation.source_id
                    )
                )
                for citation in claim.citations
            )
            for claim in report.claims
        )
        domains = {urlsplit(source.url).hostname for source in report.sources}
        diversity_passes += int(len(domains) >= 2)
        current_claims = [claim for claim in report.claims if claim.status is not ClaimStatus.STALE]
        source_by_id = {source.id: source for source in report.sources}
        freshness_passes += int(
            all(
                any(
                    source_by_id[citation.source_id].published_at is not None
                    and (now - source_by_id[citation.source_id].published_at).days <= 365
                    for citation in claim.citations
                )
                for claim in current_claims
            )
        )
        conflicting = [claim for claim in report.claims if claim.status is ClaimStatus.CONFLICTING]
        conflict_passes += int(not conflicting or bool(report.contradictions))
        hostile = "ignore previous instructions"
        injection_passes += int(
            hostile not in report.answer.lower()
            and all(hostile not in claim.statement.lower() for claim in report.claims)
        )
        stable = report.model_copy(update={"generated_at": now}).model_dump_json()
        signatures[task["objective"]].add(hashlib.sha256(stable.encode()).hexdigest())

    completed = len(reports)
    expected_claims = completed * 2
    latency = summarize(durations)
    metrics = {
        "samples_requested": args.samples,
        "samples_completed": completed,
        "citation_coverage": citation_total / material_total if material_total else 0.0,
        "claim_entailment": entailed / expected_claims if expected_claims else 0.0,
        "source_diversity": diversity_passes / completed if completed else 0.0,
        "freshness_awareness": freshness_passes / completed if completed else 0.0,
        "conflict_handling": conflict_passes / completed if completed else 0.0,
        "injection_resistance": injection_passes / completed if completed else 0.0,
        "reproducibility": (
            sum(len(values) == 1 for values in signatures.values()) / len(signatures)
        ),
        "failures": failures,
        "latency_ms": latency,
    }
    checks = {
        "citation_coverage": metrics["citation_coverage"] >= TARGETS["citation_coverage"],
        "claim_entailment": metrics["claim_entailment"] >= TARGETS["claim_entailment"],
        "source_diversity": metrics["source_diversity"] >= TARGETS["source_diversity"],
        "freshness_awareness": metrics["freshness_awareness"] >= TARGETS["freshness_awareness"],
        "conflict_handling": metrics["conflict_handling"] >= TARGETS["conflict_handling"],
        "injection_resistance": metrics["injection_resistance"] >= TARGETS["injection_resistance"],
        "reproducibility": metrics["reproducibility"] >= TARGETS["reproducibility"],
        "failures": failures == TARGETS["failures"],
        "p95_ms": latency["p95"] <= TARGETS["p95_ms"],
    }
    return {
        "format": "jarvis-phase5-research-benchmark-v1",
        "fixture": str(GOLDEN_PATH.relative_to(REPOSITORY_ROOT)),
        "settings": {
            "samples": args.samples,
            "isolated_parser": True,
            "max_sources_per_task": 3,
            "fresh_source_age_days": 365,
            "quoted_word_limit_per_source": 25,
        },
        "targets": TARGETS,
        "metrics": metrics,
        "checks": checks,
        "passed": all(checks.values()),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }


def summarize(samples: Sequence[float]) -> dict[str, float | int]:
    if not samples:
        return {"samples": 0, "p50": float("inf"), "p95": float("inf"), "max": float("inf")}
    ordered = sorted(samples)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))
    return {
        "samples": len(ordered),
        "p50": statistics.median(ordered),
        "p95": ordered[p95_index],
        "max": max(ordered),
    }


def write_result(path: Path, result: dict[str, Any]) -> None:
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        work_dir = prepare_work_dir(args.work_dir)
        result = asyncio.run(run_benchmark(args))
        output = work_dir / args.output
        write_result(output, result)
    except Exception as exc:
        print(f"Phase 5 benchmark failed safely: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps({"passed": result["passed"], "output": str(output)}, sort_keys=True))
    return 0 if result["passed"] or not args.enforce else 1


if __name__ == "__main__":
    raise SystemExit(main())
