"""One-command local report; isolate upstream connector in its own environment."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from jarvis.garmin.report import read_saved_session, write_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date", type=date.fromisoformat, default=datetime.now(UTC).astimezone().date()
    )
    parser.add_argument("--connector", type=Path)
    parser.add_argument(
        "--token-store", type=Path, default=Path(os.environ.get("GARMINTOKENS", "~/.garminconnect"))
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            print(json.dumps(read_saved_session(args.token_store, args.date), allow_nan=False))
        except Exception:
            print(
                "Saved Garmin session unavailable; use trusted local demo to reconnect.",
                file=sys.stderr,
            )
            return 1
        return 0
    candidates = [
        REPO / "runtime/integrations/garmin/python-garminconnect",
        Path.home() / "Desktop/JARVIS/runtime/integrations/garmin/python-garminconnect",
    ]
    connector = args.connector or next(
        (path for path in candidates if path.is_dir()), candidates[0]
    )
    connector = connector.expanduser().resolve()
    python = connector / ".venv/Scripts/python.exe"
    if not python.is_file() or not (connector / "garminconnect/__init__.py").is_file():
        print(
            "Connector environment missing; supply --connector with python-garminconnect folder.",
            file=sys.stderr,
        )
        return 2
    # Script lives elsewhere, so explicitly expose the owner's upstream source in
    # this child only. No environment changes or SDK dependency in JARVIS Core.
    allowed_environment = {
        "SYSTEMROOT",
        "WINDIR",
        "SYSTEMDRIVE",
        "PATH",
        "TEMP",
        "TMP",
        "LOCALAPPDATA",
        "APPDATA",
        "PROGRAMDATA",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    }
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in allowed_environment
    }
    environment["PYTHONPATH"] = str(connector)
    try:
        result = subprocess.run(
            [
                str(python),
                str(Path(__file__).resolve()),
                "--worker",
                "--date",
                args.date.isoformat(),
                "--token-store",
                str(args.token_store.expanduser()),
            ],
            cwd=connector,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=180,
            check=False,
        )
        if result.returncode or len(result.stdout) > 65_536:
            print("Saved Garmin session or reads unavailable; no report written.", file=sys.stderr)
            return 1
        report = json.loads(result.stdout)
        paths = write_report(report, REPO / "runtime/garmin/reports")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print(
            "Garmin report unavailable or timed out; retry from trusted local terminal.",
            file=sys.stderr,
        )
        return 1
    available = sum(row["status"] == "available" for row in report["sections"].values())
    print(f"Report saved: {available}/{len(report['sections'])} categories with supported values.")
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
