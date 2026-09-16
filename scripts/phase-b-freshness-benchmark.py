"""Reproducible Phase B deterministic route matrix and latency benchmark."""

from __future__ import annotations

import json
import math
import platform
import statistics
import sys
from itertools import cycle, islice
from time import perf_counter_ns
from typing import Final

from jarvis.core import FreshnessRoute
from jarvis.freshness_router import DeterministicFreshnessRouter

SAMPLE_COUNT: Final = 10_000
P95_TARGET_MS: Final = 1.0
CASES: Final = (
    ("Explain photosynthesis.", FreshnessRoute.STATIC),
    ("Who won the 2012 election?", FreshnessRoute.STATIC),
    ("Compare TCP and UDP.", FreshnessRoute.STATIC),
    ("What time is it?", FreshnessRoute.LOCAL_CONTEXT),
    ("What is the current timezone?", FreshnessRoute.LOCAL_CONTEXT),
    ("Which model is active?", FreshnessRoute.LOCAL_CONTEXT),
    ("What day is tomorrow?", FreshnessRoute.LOCAL_CONTEXT),
    ("What is the weather forecast?", FreshnessRoute.WEB_REQUIRED),
    ("Show the latest Python version.", FreshnessRoute.WEB_REQUIRED),
    ("Who is the prime minister?", FreshnessRoute.WEB_REQUIRED),
    ("What is the population of Toronto?", FreshnessRoute.WEB_REQUIRED),
    ("Look this up on the web.", FreshnessRoute.WEB_REQUIRED),
    ("What is the stock price for NVDA?", FreshnessRoute.WEB_REQUIRED),
    ("Read my unread email.", FreshnessRoute.PERSONAL_DATA_REQUIRED),
    ("Do I have a meeting today?", FreshnessRoute.PERSONAL_DATA_REQUIRED),
    ("Summarize the calendar.", FreshnessRoute.PERSONAL_DATA_REQUIRED),
    ("What is my upcoming flight?", FreshnessRoute.PERSONAL_DATA_REQUIRED),
    ("Where do I live?", FreshnessRoute.PERSONAL_DATA_REQUIRED),
    ("Cross-check this claim using independent sources.", FreshnessRoute.MULTI_SOURCE),
    ("Recommend the best laptop for development.", FreshnessRoute.MULTI_SOURCE),
    ("Compare current insurance plans.", FreshnessRoute.MULTI_SOURCE),
    ("Show reviews for this hotel.", FreshnessRoute.MULTI_SOURCE),
    ("Research quantum computing.", FreshnessRoute.MULTI_SOURCE),
)


def main() -> int:
    router = DeterministicFreshnessRouter()
    samples = tuple(islice(cycle(CASES), SAMPLE_COUNT))
    for query, _expected in CASES:
        router.classify(query)

    durations_ms: list[float] = []
    failures: list[dict[str, str]] = []
    counts = {route.value: 0 for route in FreshnessRoute}
    for query, expected in samples:
        started = perf_counter_ns()
        actual = router.classify(query).route
        durations_ms.append((perf_counter_ns() - started) / 1_000_000)
        counts[actual.value] += 1
        if actual is not expected and len(failures) < 20:
            failures.append({"query": query, "expected": expected.value, "actual": actual.value})

    ordered = sorted(durations_ms)
    p95_ms = ordered[math.ceil(len(ordered) * 0.95) - 1]
    result = {
        "benchmark": "phase-b-freshness-router",
        "samples": len(samples),
        "corpus_cases": len(CASES),
        "route_counts": counts,
        "p50_ms": round(statistics.median(ordered), 6),
        "p95_ms": round(p95_ms, 6),
        "max_ms": round(max(ordered), 6),
        "failures": failures,
        "target_p95_ms": P95_TARGET_MS,
        "passed": not failures and p95_ms < P95_TARGET_MS,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
