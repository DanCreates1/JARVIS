"""Frozen synthetic local email acceptance; no credentials/network/models/effects."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from jarvis.email import EmailService, LocalEmailExports  # noqa: E402


async def benchmark(root: Path) -> dict[str, object]:
    timings = []
    max_chars = 0
    for index in range(100):
        thread_id = f"t{index:03}"
        thread = root / thread_id
        thread.mkdir()
        body = f"Please review ORACLE-{index:03} by 2026-10-09."
        raw = (
            f"From: fixture@example.invalid\nSubject: Synthetic {index}\n"
            f"Content-Type: text/plain; charset=utf-8\n\n{body}"
        ).encode()
        (thread / "m1.eml").write_bytes(raw)
        # Fresh adapter per case; no map/message/model cache.
        service = EmailService(LocalEmailExports(root))
        started = time.perf_counter()
        summary = await service.summarize(thread_id)
        extracted = await service.extract(thread_id)
        projection = await service.project(thread_id)
        draft = await service.draft(
            thread_id,
            recipients=("owner@example.invalid",),
            subject="Explicit subject",
            body="Explicit draft",
        )
        timings.append((time.perf_counter() - started) * 1000)
        assert summary.evidence[0].quote == body and summary.evidence[0].message_id == "m1"
        assert [e.kind for e in extracted.evidence] == ["action_candidate", "date_candidate"]
        assert f"ORACLE-{index:03}" in projection.content
        assert hashlib.sha256(raw).hexdigest() in projection.content
        assert projection.source_ids == (thread_id,) and projection.sensitivity.value == "private"
        assert len(projection.content) <= 8000
        assert not draft.sent and not draft.stored and draft.body == "Explicit draft"
        assert (thread / "m1.eml").read_bytes() == raw
        max_chars = max(max_chars, len(projection.content))
    ordered = sorted(timings)
    return {
        "cases": 100,
        "oracle_failures": 0,
        "messages_per_case": 1,
        "operations_per_case": 4,
        "parser_processes": 400,
        "cache": "none",
        "p50_ms": round(statistics.median(timings), 3),
        "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 3),
        "max_projection_chars": max_chars,
        "p95_gate_ms": 1000,
        "credentials_used": 0,
        "cloud_calls": 0,
        "research_calls": 0,
        "effects": 0,
        "cost_usd": 0,
        "python": platform.python_version(),
        "os": platform.platform(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enforce", action="store_true")
    arguments = parser.parse_args()
    runtime = REPOSITORY / "runtime"
    runtime.mkdir(exist_ok=True)
    if not runtime.resolve().is_relative_to(REPOSITORY):
        raise ValueError("runtime outside workspace")
    with tempfile.TemporaryDirectory(prefix="phase-i-benchmark-", dir=runtime) as directory:
        root = Path(directory).resolve()
        if not root.is_relative_to(runtime.resolve()):
            raise ValueError("cleanup outside runtime")
        result = asyncio.run(benchmark(root))
    print(json.dumps(result, indent=2))
    if arguments.enforce and float(str(result["p95_ms"])) > 1000:
        raise SystemExit("email p95 gate failed")


if __name__ == "__main__":
    main()
