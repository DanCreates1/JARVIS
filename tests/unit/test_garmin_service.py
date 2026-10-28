"""Core rejects raw or malformed output from the isolated Garmin bridge."""

import asyncio
import json
import traceback
from datetime import UTC, datetime
from pathlib import Path
from sys import executable
from unittest.mock import AsyncMock, Mock

import pytest

from jarvis.garmin import service as service_module
from jarvis.garmin.service import GarminSummaryService, GarminUnavailableError


def _summary_bytes() -> bytes:
    return json.dumps(
        {
            "date": datetime.now(UTC).astimezone().date().isoformat(),
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
    process.stdout = asyncio.StreamReader()
    process.stdout.feed_data(stdout if stdout is not None else _summary_bytes())
    process.stdout.feed_eof()
    process.wait = AsyncMock(return_value=returncode)
    process.kill = Mock()

    async def fresh_process(*_args: object, **_kwargs: object) -> Mock:
        if spawn.await_count > 1:
            process.stdout = asyncio.StreamReader()
            process.stdout.feed_data(stdout if stdout is not None else _summary_bytes())
            process.stdout.feed_eof()
        return process

    spawn = AsyncMock(side_effect=fresh_process)
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
        limit=8_193,
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
    process.stdout.read = AsyncMock(side_effect=[TimeoutError, b""])
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

    async def pending_communication(_size: int) -> bytes:
        started.set()
        await asyncio.Future()
        return b""

    read_count = 0

    async def read(size: int) -> bytes:
        nonlocal read_count
        read_count += 1
        return await pending_communication(size) if read_count == 1 else b""

    process.stdout.read = AsyncMock(side_effect=read)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["provider", "missing-bridge"])
async def test_failed_refresh_does_not_resurrect_previous_server_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    now = [1000.0]
    monkeypatch.setattr(service_module, "monotonic", lambda: now[0])
    reader, process, spawn = _mock_bridge(tmp_path, monkeypatch)
    await reader.summary()
    now[0] = 1060.0
    process.returncode = 1
    if failure == "missing-bridge":
        await asyncio.to_thread((tmp_path / "bridge.py").unlink)
    expected = "bridge_unavailable" if failure == "missing-bridge" else "refresh_failed"
    with pytest.raises(GarminUnavailableError, match=expected):
        await reader.summary(refresh=True)
    for refresh in (True, False):
        with pytest.raises(GarminUnavailableError, match="refresh_limited"):
            await reader.summary(refresh=refresh)
    assert spawn.await_count == (1 if failure == "missing-bridge" else 2)
    now[0] = 1120.0
    process.returncode = 0
    if failure == "missing-bridge":
        await asyncio.to_thread((tmp_path / "bridge.py").touch)
    assert await reader.summary()
    assert spawn.await_count == (2 if failure == "missing-bridge" else 3)


@pytest.mark.asyncio
async def test_duplicate_concurrent_refreshes_share_one_read_and_cache_is_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, _, spawn = _mock_bridge(tmp_path, monkeypatch)
    results = await asyncio.gather(*(reader.summary(refresh=True) for _ in range(10)))
    assert spawn.await_count == 1
    assert all(result is results[0] for result in results)
    with pytest.raises(ValueError, match="frozen"):
        results[0].steps = 99
    with pytest.raises(ValueError, match="frozen"):
        results[0].activities[0].name = "changed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "replacement",
    [
        {"steps": True},
        {"steps": "123"},
        {"stress": 50.5},
        {"activities_available": "true"},
        {"date": "2026-02-31"},
        {"refreshed_at": "2026-10-27T12:00:00"},
        {"activities": [{"name": "a", "type": "b", "started": ""}] * 4},
    ],
)
async def test_untrusted_bridge_schema_rejects_coercion_dates_and_oversized_lists(
    replacement: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = json.loads(_summary_bytes()) | replacement
    reader, _, _ = _mock_bridge(tmp_path, monkeypatch, stdout=json.dumps(data).encode())
    with pytest.raises(GarminUnavailableError, match="refresh_failed"):
        await reader.summary()


@pytest.mark.asyncio
async def test_duplicate_bridge_fields_are_not_silently_reinterpreted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _summary_bytes()[:-1] + b',"steps":999}'
    reader, _, _ = _mock_bridge(tmp_path, monkeypatch, stdout=data)
    with pytest.raises(GarminUnavailableError, match="refresh_failed"):
        await reader.summary()


@pytest.mark.asyncio
@pytest.mark.parametrize("output_size", [9_000, 2_000_000])
async def test_real_overflowing_child_is_killed_and_reaped_before_its_sleep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output_size: int
) -> None:
    bridge = tmp_path / "overflow.py"
    bridge.write_text(
        f"import os, time\nos.write(1, b'x' * {output_size})\ntime.sleep(120)\n", encoding="utf-8"
    )
    spawn = asyncio.create_subprocess_exec
    children: list[asyncio.subprocess.Process] = []

    async def capture(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        child = await spawn(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(service_module.asyncio, "create_subprocess_exec", capture)
    reader = GarminSummaryService(python_path=Path(executable), bridge_path=bridge)
    with pytest.raises(GarminUnavailableError, match="refresh_failed"):
        await asyncio.wait_for(reader.summary(), timeout=5)
    assert len(children) == 1 and children[0].returncode is not None


@pytest.mark.asyncio
async def test_restart_drops_cache_and_throttle_instead_of_persisting_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, _, spawn = _mock_bridge(tmp_path, monkeypatch)
    first = await reader.summary()
    restarted = GarminSummaryService(
        python_path=tmp_path / "python.exe", bridge_path=tmp_path / "bridge.py"
    )
    assert await restarted.summary() is not first
    assert spawn.await_count == 2
    assert await asyncio.to_thread(lambda: {path.name for path in tmp_path.iterdir()}) == {
        "python.exe",
        "bridge.py",
    }
