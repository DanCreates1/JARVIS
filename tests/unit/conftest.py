from __future__ import annotations

import os

import pytest

import jarvis.computer.windows as windows


@pytest.fixture(autouse=True)
def _stable_standard_user_windows_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests independent of runner elevation and host identity."""

    if os.name != "nt":
        return

    elevated, _sid = windows._read_token_state()
    if not elevated:
        return

    def read_standard_user_token() -> tuple[bool, bytes]:
        windows._require_windows()
        return False, b"jarvis-unit-test-user"

    monkeypatch.setattr(windows, "_read_token_state", read_standard_user_token)
