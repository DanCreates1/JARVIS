"""Synthetic Garmin import checks never use private sessions or real credentials."""

from __future__ import annotations

import builtins
import json
import socket
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from jarvis.garmin import bridge


def session_json() -> str:
    return json.dumps(
        {
            "di_token": "synthetic-access-token",
            "di_refresh_token": "synthetic-refresh-token",
            "di_client_id": "GARMIN_CONNECT_MOBILE_ANDROID_DI",
        }
    )


class FakeVault:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.writes = 0
        self.deletes = 0

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))

    def set_password(self, service: str, account: str, token: str) -> None:
        self.writes += 1
        self.values[(service, account)] = token

    def delete_password(self, service: str, account: str) -> None:
        self.deletes += 1
        del self.values[(service, account)]


@pytest.fixture(autouse=True)
def block_real_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.split(".", 1)[0] in {"garminconnect", "keyring"}:
            raise AssertionError("Import must not use Garmin or Credential Locker libraries")
        return original_import(name, *args, **kwargs)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Import must not access credentials or prompt")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(bridge, "_vault", forbidden)
    monkeypatch.setattr(builtins, "input", forbidden)
    monkeypatch.setattr(bridge.getpass, "getpass", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.mark.parametrize("as_bytes", [False, True])
def test_validate_token_accepts_complete_synthetic_session(as_bytes: bool) -> None:
    raw = session_json()
    value = bridge._validate_token_json(raw.encode("utf-8") if as_bytes else raw)
    assert value.isascii()
    assert json.loads(value) == json.loads(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-json",
        "[]",
        "null",
        '"synthetic-token"',
        "{}",
        '{"di_token":"synthetic-access-token"}',
        '{"oauth1_token":"synthetic-old-token","oauth2_token":"synthetic-old-token"}',
        '{"di_token":"a","di_refresh_token":"b","di_client_id":"c","extra":"d"}',
        '{"di_token":"a","di_token":"b","di_refresh_token":"c","di_client_id":"d"}',
        '{"di_token":"a","di_refresh_token":"b","di_client_id":"c"} trailing',
        b"\xff",
    ],
)
def test_validate_token_rejects_malformed_and_legacy_schemas(raw: bytes | str) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        bridge._validate_token_json(raw)


@pytest.mark.parametrize("field", ["di_token", "di_refresh_token", "di_client_id"])
@pytest.mark.parametrize(
    "invalid",
    [None, True, 1, [], {}, "", " ", "bad token", "bad\nvalue", "bad\x00value", "caf\u00e9"],
)
def test_validate_token_rejects_unsafe_field_values(field: str, invalid: object) -> None:
    data = json.loads(session_json())
    data[field] = invalid
    with pytest.raises(ValueError):
        bridge._validate_token_json(json.dumps(data))


def test_validate_token_enforces_client_id_limit() -> None:
    data = json.loads(session_json())
    data["di_client_id"] = "A" * 256
    assert json.loads(bridge._validate_token_json(json.dumps(data)))["di_client_id"] == "A" * 256
    data["di_client_id"] = "A" * 257
    with pytest.raises(ValueError):
        bridge._validate_token_json(json.dumps(data))


@pytest.mark.parametrize("as_bytes", [False, True])
def test_validate_token_enforces_total_input_size(as_bytes: bool) -> None:
    raw = session_json()
    at_limit = raw + " " * (65_536 - len(raw.encode("utf-8")))
    assert json.loads(
        bridge._validate_token_json(at_limit.encode("utf-8") if as_bytes else at_limit)
    ) == json.loads(raw)
    oversized = at_limit + " "
    with pytest.raises(ValueError):
        bridge._validate_token_json(oversized.encode("utf-8") if as_bytes else oversized)


def test_read_saved_session_keeps_source_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "garmin_tokens.json"
    payload = session_json().encode("utf-8")
    source.write_bytes(payload)
    before = source.stat()
    assert json.loads(bridge._read_saved_session(source)) == json.loads(payload)
    after = source.stat()
    assert source.read_bytes() == payload
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)


@pytest.mark.parametrize(
    "path",
    [
        "garmin_tokens.json",
        "../garmin_tokens.json",
        r"C:garmin_tokens.json",
        r"\garmin_tokens.json",
        "~/.garminconnect/garmin_tokens.json",
        r"\\server\share\garmin_tokens.json",
        r"\\?\C:\synthetic\garmin_tokens.json",
        r"\\.\C:\synthetic\garmin_tokens.json",
        r"C:\synthetic\garmin_tokens.json:stream.json",
    ],
)
def test_read_saved_session_rejects_ambiguous_or_nonlocal_paths(path: str) -> None:
    with pytest.raises((ValueError, OSError)):
        bridge._read_saved_session(Path(path))


def test_read_saved_session_rejects_wrong_extension_and_directory(tmp_path: Path) -> None:
    wrong_extension = tmp_path / "garmin_tokens.txt"
    wrong_extension.write_text(session_json(), encoding="utf-8")
    directory = tmp_path / "directory.json"
    directory.mkdir()
    for source in (wrong_extension, directory):
        with pytest.raises(ValueError):
            bridge._read_saved_session(source)


@pytest.mark.parametrize("size", [0, 65_537])
def test_read_saved_session_rejects_invalid_file_size(tmp_path: Path, size: int) -> None:
    source = tmp_path / "garmin_tokens.json"
    source.write_bytes(b" " * size)
    with pytest.raises(ValueError):
        bridge._read_saved_session(source)


@pytest.mark.parametrize("at_parent", [False, True])
def test_read_saved_session_rejects_reparse_points(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at_parent: bool
) -> None:
    source = tmp_path / "garmin_tokens.json"
    source.write_text(session_json(), encoding="utf-8")
    affected = source.parent if at_parent else source
    original_lstat = Path.lstat

    def marked_lstat(path: Path) -> Any:
        value = original_lstat(path)
        if path != affected:
            return value
        return SimpleNamespace(
            st_mode=value.st_mode,
            st_size=value.st_size,
            st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            st_dev=value.st_dev,
            st_ino=value.st_ino,
            st_mtime_ns=value.st_mtime_ns,
        )

    monkeypatch.setattr(Path, "lstat", marked_lstat)
    with pytest.raises(ValueError):
        bridge._read_saved_session(source)


def test_read_saved_session_stops_before_following_reparse_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "garmin_tokens.json"
    source.write_text(session_json(), encoding="utf-8")
    original_lstat = Path.lstat

    def marked_lstat(path: Path) -> Any:
        if path == source:
            raise AssertionError("Must reject parent before inspecting its child")
        value = original_lstat(path)
        if path != source.parent:
            return value
        return SimpleNamespace(
            st_mode=value.st_mode,
            st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
        )

    monkeypatch.setattr(Path, "lstat", marked_lstat)
    with pytest.raises(ValueError):
        bridge._read_saved_session(source)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows fixed-drive import boundary")
def test_read_saved_session_rejects_nonfixed_drive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "garmin_tokens.json"
    source.write_text(session_json(), encoding="utf-8")
    monkeypatch.setattr(bridge.ctypes.windll.kernel32, "GetDriveTypeW", lambda _anchor: 4)
    with pytest.raises(ValueError):
        bridge._read_saved_session(source)


@pytest.mark.parametrize("change", ["identity", "during_read"])
def test_read_saved_session_rejects_changed_open_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    source = tmp_path / "garmin_tokens.json"
    source.write_text(session_json(), encoding="utf-8")
    original_fstat = bridge.os.fstat
    calls = 0

    def changed_fstat(descriptor: int) -> Any:
        nonlocal calls
        calls += 1
        value = original_fstat(descriptor)
        return SimpleNamespace(
            st_mode=value.st_mode,
            st_dev=value.st_dev,
            st_ino=value.st_ino + (change == "identity"),
            st_size=value.st_size,
            st_mtime_ns=value.st_mtime_ns + (change == "during_read" and calls == 2),
        )

    monkeypatch.setattr(bridge.os, "fstat", changed_fstat)
    with pytest.raises(ValueError):
        bridge._read_saved_session(source)


def test_import_session_uses_only_fake_vault_without_source_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "garmin_tokens.json"
    payload = session_json().encode("utf-8")
    source.write_bytes(payload)
    vault = FakeVault()
    monkeypatch.setattr(bridge, "_vault", lambda: vault)
    bridge._import_session(source)
    saved = bridge._read_token(vault)
    assert saved is not None and json.loads(saved) == json.loads(payload)
    assert source.read_bytes() == payload
    assert vault.writes > 0 and vault.deletes == 0
    assert all(len(value) <= 900 for value in vault.values.values())
    output = capsys.readouterr()
    assert output.out and not output.err
    assert "synthetic-" not in output.out and str(source) not in output.out


def test_import_session_refuses_existing_session_without_replacement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "garmin_tokens.json"
    source.write_text(session_json(), encoding="utf-8")
    vault = FakeVault()
    bridge._store_token(vault, session_json())
    before = vault.values.copy()
    writes = vault.writes
    monkeypatch.setattr(bridge, "_vault", lambda: vault)
    with pytest.raises((ValueError, RuntimeError)):
        bridge._import_session(source)
    assert vault.values == before and vault.writes == writes and vault.deletes == 0


def test_import_session_rejects_invalid_json_before_storing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "garmin_tokens.json"
    source.write_text('{"di_token":"synthetic-private-token"}', encoding="utf-8")
    vault = FakeVault()
    monkeypatch.setattr(bridge, "_vault", lambda: vault)
    with pytest.raises(ValueError):
        bridge._import_session(source)
    assert vault.values == {} and vault.writes == 0 and vault.deletes == 0


def test_import_session_cli_sanitizes_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "private-path.json"

    def fail(_path: Path) -> None:
        raise ValueError(f"private-token {source}")

    monkeypatch.setattr(bridge, "_import_session", fail)
    monkeypatch.setattr(sys, "argv", ["bridge.py", "import-session", str(source)])
    assert bridge.main() == 1
    output = capsys.readouterr()
    assert not output.out and output.err
    assert "private-token" not in output.err and str(source) not in output.err


@pytest.mark.parametrize(
    "arguments",
    [
        ["import-session"],
        ["import-session", "synthetic.json", "extra"],
        ["summary", "synthetic.json"],
        ["unknown", "synthetic.json"],
    ],
)
def test_import_session_cli_rejects_invalid_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], arguments: list[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["bridge.py", *arguments])
    assert bridge.main() == 2
    output = capsys.readouterr()
    assert "Usage:" in output.err and "synthetic.json" not in output.err
