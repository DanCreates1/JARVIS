"""Core rejects raw or malformed output from the isolated Garmin bridge."""

import asyncio
import json
import traceback
from pathlib import Path
from sys import executable
from unittest.mock import AsyncMock, Mock

import pytest

from jarvis.garmin import service as service_module
from jarvis.garmin.service import GarminSummaryService, GarminUnavailableError


def _summary_bytes() -> bytes:
    return json.dumps(
        {
            "date": "2026-09-30",
            "refreshed_at": "2026-09-30T12:00:00Z",
            "steps": 1234,
            "activities": [{"name": "Synthetic walk", "type": "walking", "started": "2026-09-30"}],
        }
    ).encode()


def _mock_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdout: bytes | None = None,
    returncode: int = 0,
) -> tuple[GarminSummaryService, Mock, AsyncMock]:
    python = tmp_path / "python.exe"
    bridge = tmp_path / "bridge.py"
    python.touch()
    bridge.touch()
    process = Mock()
    process.returncode = returncode
    process.communicate = AsyncMock(
        return_value=(stdout if stdout is not None else _summary_bytes(), None)
    )
    process.wait = AsyncMock(return_value=returncode)
    process.kill = Mock()
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(service_module.asyncio, "create_subprocess_exec", spawn)
    reader = GarminSummaryService(python_path=python, bridge_path=bridge)
    return reader, process, spawn


@pytest.mark.asyncio
async def test_garmin_service_rejects_unexpected_private_fields(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.py"
    bridge.write_text(
        "import json\n"
        "print(json.dumps({'date': '2026-09-30', "
        "'refreshed_at': '2026-09-30T12:00:00Z', "
        "'activities': [], 'token': 'must-not-leak'}))\n",
        encoding="utf-8",
    )
    reader = GarminSummaryService(python_path=Path(executable), bridge_path=bridge)
    with pytest.raises(GarminUnavailableError, match="refresh_failed"):
        await reader.summary()


@pytest.mark.asyncio
async def test_bridge_uses_isolated_python_and_only_required_windows_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, _, spawn = _mock_bridge(tmp_path, monkeypatch)
    safe_environment = {
        "SystemRoot": "C:\\Windows",
        "WINDIR": "C:\\Windows",
        "SYSTEMDRIVE": "C:",
        "TEMP": str(tmp_path),
        "TMP": str(tmp_path),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "APPDATA": str(tmp_path / "roaming"),
        "PROGRAMDATA": str(tmp_path / "program"),
        "USERPROFILE": str(tmp_path / "profile"),
        "HOMEDRIVE": "C:",
        "HOMEPATH": "\\Users\\synthetic",
    }
    monkeypatch.setattr(
        service_module.os,
        "environ",
        {
            **safe_environment,
            "GARMINTOKENS": "synthetic-session-directory",
            "PYTHONPATH": "synthetic-import-directory",
            "PYTHONHOME": "synthetic-python-home",
            "PYTHONSTARTUP": "synthetic-startup.py",
            "HTTPS_PROXY": "https://synthetic-proxy.invalid",
            "ALL_PROXY": "https://synthetic-proxy.invalid",
            "OPENAI_API_KEY": "synthetic-unrelated-secret",
            "PATH": "synthetic-search-path",
        },
    )

    await reader.summary()

    spawn.assert_awaited_once_with(
        str(tmp_path / "python.exe"),
        "-I",
        str(tmp_path / "bridge.py"),
        "summary",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=safe_environment,
    )


@pytest.mark.asyncio
async def test_summary_cache_expires_at_300_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [1000.0]
    monkeypatch.setattr(service_module, "monotonic", lambda: now[0])
    reader, _, spawn = _mock_bridge(tmp_path, monkeypatch)

    original = await reader.summary()
    now[0] = 1299.999
    assert await reader.summary() is original
    assert spawn.await_count == 1

    now[0] = 1300.0
    assert await reader.summary() is not original
    assert spawn.await_count == 2


@pytest.mark.asyncio
async def test_explicit_refresh_is_throttled_for_60_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [1000.0]
    monkeypatch.setattr(service_module, "monotonic", lambda: now[0])
    reader, _, spawn = _mock_bridge(tmp_path, monkeypatch)

    original = await reader.summary()
    now[0] = 1059.999
    assert await reader.summary(refresh=True) is original
    assert spawn.await_count == 1

    now[0] = 1060.0
    assert await reader.summary(refresh=True) is not original
    assert spawn.await_count == 2


@pytest.mark.asyncio
async def test_failed_refresh_without_cache_is_also_throttled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [1000.0]
    monkeypatch.setattr(service_module, "monotonic", lambda: now[0])
    reader, _, spawn = _mock_bridge(tmp_path, monkeypatch, returncode=1)
    with pytest.raises(GarminUnavailableError, match=r"^refresh_failed$"):
        await reader.summary()

    now[0] = 1059.999
    with pytest.raises(GarminUnavailableError, match=r"^refresh_limited$"):
        await reader.summary(refresh=True)
    assert spawn.await_count == 1

    now[0] = 1060.0
    with pytest.raises(GarminUnavailableError, match=r"^refresh_failed$"):
        await reader.summary(refresh=True)
    assert spawn.await_count == 2


@pytest.mark.asyncio
async def test_refresh_timeout_kills_and_reaps_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, process, _ = _mock_bridge(tmp_path, monkeypatch)
    process.returncode = None
    process.communicate.side_effect = TimeoutError
    wait_for = AsyncMock(wraps=asyncio.wait_for)
    monkeypatch.setattr(service_module.asyncio, "wait_for", wait_for)

    with pytest.raises(GarminUnavailableError, match=r"^refresh_timeout$"):
        await reader.summary()

    assert wait_for.call_args.kwargs == {"timeout": 90}
    process.kill.assert_called_once_with()
    process.wait.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_cancelled_refresh_kills_and_reaps_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, process, _ = _mock_bridge(tmp_path, monkeypatch)
    process.returncode = None
    started = asyncio.Event()

    async def pending_communication() -> tuple[bytes, None]:
        started.set()
        await asyncio.Future()
        return _summary_bytes(), None

    process.communicate.side_effect = pending_communication
    task = asyncio.create_task(reader.summary())
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)

    process.kill.assert_called_once_with()
    process.wait.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stdout", "returncode"),
    [
        (b"SYNTHETIC_PRIVATE_VALUE invalid JSON", 0),
        (
            json.dumps(
                {
                    "date": "2026-09-30",
                    "refreshed_at": "2026-09-30T12:00:00Z",
                    "activities": [],
                    "token": "SYNTHETIC_PRIVATE_VALUE",
                }
            ).encode(),
            0,
        ),
        (b"SYNTHETIC_PRIVATE_VALUE" + b"x" * 8192, 0),
        (b"SYNTHETIC_PRIVATE_VALUE", 1),
    ],
    ids=("invalid-json", "unexpected-token", "oversized-output", "nonzero-exit"),
)
async def test_bridge_failures_hide_private_output_in_errors_and_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    stdout: bytes,
    returncode: int,
) -> None:
    reader, _, _ = _mock_bridge(tmp_path, monkeypatch, stdout=stdout, returncode=returncode)
    with pytest.raises(GarminUnavailableError, match=r"^refresh_failed$") as caught:
        await reader.summary()

    assert "SYNTHETIC_PRIVATE_VALUE" not in "".join(traceback.format_exception(caught.value))
    assert "SYNTHETIC_PRIVATE_VALUE" not in caplog.text
