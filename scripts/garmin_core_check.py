"""Explicit live Core check; print evidence flags, never private health values."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from contextlib import redirect_stderr, redirect_stdout, suppress
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from jarvis.garmin.service import GarminSummaryService  # noqa: E402

_METRICS = ("steps", "resting_heart_rate", "sleep_minutes", "stress", "body_battery")


async def _check() -> dict[str, object]:
    summary = await GarminSummaryService().summary(refresh=True)
    now = datetime.now(UTC)
    refreshed = summary.refreshed_at
    fresh = (
        refreshed.tzinfo is not None
        and 0 <= (now - refreshed).total_seconds() <= 300
        and summary.date == now.astimezone().date().isoformat()
    )
    available = {field: getattr(summary, field) is not None for field in _METRICS}
    available["activities"] = bool(summary.activities)
    return {
        "status": "pass" if fresh and any(available.values()) else "unavailable",
        "schema_valid": True,
        "fresh": fresh,
        "available": available,
        "activity_bound": len(summary.activities) <= 3,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--read",
        action="store_true",
        help="Run one live Core read; saved-session renewal may occur.",
    )
    args = parser.parse_args(argv)
    if not args.read:
        print("Use --read to run one live Core check. Saved-session renewal may occur.")
        return 2

    previous_logging_level = logging.root.manager.disable
    evidence: dict[str, object] = {
        "status": "unavailable",
        "schema_valid": False,
        "fresh": False,
        "available": {field: False for field in (*_METRICS, "activities")},
        "activity_bound": False,
    }
    try:
        # Utility process only: no private diagnostic text is retained or emitted.
        # Child output is separately captured/validated by the existing Core service.
        with (
            open(os.devnull, "w", encoding="utf-8") as sink,
            redirect_stdout(sink),
            redirect_stderr(sink),
        ):
            logging.disable(logging.CRITICAL)
            with suppress(Exception, KeyboardInterrupt):
                evidence = asyncio.run(_check())
    finally:
        logging.disable(previous_logging_level)
    print(json.dumps(evidence, separators=(",", ":"), allow_nan=False))
    return 0 if evidence["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
