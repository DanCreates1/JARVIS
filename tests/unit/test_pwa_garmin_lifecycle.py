"""Execute real PWA JavaScript against delayed responses without live services."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_pwa_garmin_lifecycle_ignores_results_after_logout_or_session_change() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node required for PWA JavaScript lifecycle acceptance")
    repository = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [node, "--test", str(repository / "tests/pwa/garmin-lifecycle.test.cjs")],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
