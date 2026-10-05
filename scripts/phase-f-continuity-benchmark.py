"""Fixed local Phase F oracle; no provider, credential, network, or effect calls."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path

from jarvis.coding_context import CodingContextService
from jarvis.core import SensitivityClass


def git(root: Path, *args: str) -> None:
    environment = {
        key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")
    }
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        env=environment,
    )


def percentile(values: list[float], fraction: float) -> float:
    return round(sorted(values)[int((len(values) - 1) * fraction)], 3)


async def run(repository: Path | None) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="jarvis-phase-f-") as directory:
        base = Path(directory)
        root = base / "repo"
        root.mkdir()
        git(root, "init")
        git(root, "config", "user.name", "Synthetic Fixture")
        git(root, "config", "user.email", "fixture@example.invalid")
        git(root, "config", "core.autocrlf", "false")
        (root / "src").mkdir()
        for number in range(60):
            (root / "src" / f"module_{number:02}.py").write_text(
                f"def answer_{number}():\n    return {number}\n",
                encoding="utf-8",
            )
        git(root, "add", ".")
        git(root, "-c", "commit.gpgsign=false", "commit", "-m", "Synthetic baseline")
        context = CodingContextService(root, base / "checkpoints")
        cold: list[float] = []
        warm: list[float] = []
        failures = 0
        max_chars = 0
        for sample in range(100):
            if sample % 2 == 0:
                (root / "src" / "module_00.py").write_text(
                    f"def answer_0():\n    return {sample + 100}\n",
                    encoding="utf-8",
                )
            started = time.perf_counter()
            snapshot = await context.snapshot()
            elapsed = (time.perf_counter() - started) * 1_000
            (warm if sample % 2 else cold).append(elapsed)
            projection = snapshot.project()
            checkpoint = context.checkpoint()
            max_chars = max(max_chars, len(projection.content))
            expected_value = sample - sample % 2 + 100
            if not (
                len(snapshot.entries) == 60
                and snapshot.changed_paths == ("src/module_00.py",)
                and f"+    return {expected_value}" in snapshot.diff
                and snapshot.cache_hit == bool(sample % 2)
                and projection.sensitivity is SensitivityClass.PRIVATE
                and checkpoint is not None
                and "return" not in checkpoint.model_dump_json()
            ):
                failures += 1
        context.clear()
        live = None
        if repository is not None:
            local = CodingContextService(repository, base / "local-checkpoints")
            started = time.perf_counter()
            snapshot = await local.snapshot()
            live = {
                "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
                "mapped_files": len(snapshot.entries),
                "changed_files": len(snapshot.changed_paths),
                "partial": snapshot.truncated,
                "projection_chars": len(snapshot.project().content),
                "checkpoint_valid": local.checkpoint() is not None,
            }
            local.clear()
        return {
            "samples": 100,
            "cold_samples": 50,
            "warm_samples": 50,
            "cold_p50_ms": percentile(cold, 0.50),
            "cold_p95_ms": percentile(cold, 0.95),
            "warm_p50_ms": percentile(warm, 0.50),
            "warm_p95_ms": percentile(warm, 0.95),
            "failures": failures,
            "max_projection_chars": max_chars,
            "p95_limit_ms": 1_000,
            "projection_limit_chars": 8_000,
            "provider_calls": 0,
            "network_calls": 0,
            "cost_usd": 0,
            "python": platform.python_version(),
            "platform": platform.system(),
            "local_repository_smoke": live,
            "passed": failures == 0
            and max_chars <= 8_000
            and percentile(cold, 0.95) <= 1_000
            and percentile(warm, 0.95) <= 1_000,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, help="Optional configured local checkout smoke.")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(run(args.repository))
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.enforce and not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
