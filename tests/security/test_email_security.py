from __future__ import annotations

import os
from pathlib import Path

import pytest

from jarvis.email import EmailError, LocalEmailExports
from jarvis.email.processing import IsolatedEmailParser


@pytest.mark.parametrize(
    "identifier",
    [
        "../escape",
        "a/b",
        "a\\b",
        "a:stream",
        "CON",
        "con",
        "nul",
        "aux",
        "com1",
        "lpt9",
        "a.",
        "a ",
        "x" * 65,
    ],
)
async def test_export_identifier_attacks(tmp_path, identifier):
    adapter = LocalEmailExports(tmp_path)
    with pytest.raises(EmailError, match="invalid_email_id"):
        await adapter.read_thread(identifier)


def test_unc_relative_and_missing_roots(tmp_path):
    for root in (Path("relative"), Path("//server/share/export"), tmp_path / "absent"):
        with pytest.raises(EmailError):
            LocalEmailExports(root)


async def test_hardlink_and_capacity_denied(tmp_path):
    thread = tmp_path / "t1"
    thread.mkdir()
    source = tmp_path / "outside.eml"
    source.write_bytes(b"Subject: x\n\nprivate")
    os.link(source, thread / "m1.eml")
    adapter = LocalEmailExports(tmp_path)
    with pytest.raises(EmailError, match="export_type_denied"):
        await adapter.read_thread("t1")
    (thread / "m1.eml").unlink()
    for i in range(17):
        (thread / f"m{i}.eml").write_bytes(b"\nbody")
    with pytest.raises(EmailError, match="export_capacity"):
        await adapter.read_thread("t1")


async def test_symlink_or_windows_reparse_denied(tmp_path, monkeypatch):
    thread = tmp_path / "t1"
    thread.mkdir()
    source = thread / "m1.eml"
    source.write_bytes(b"\nbody")
    adapter = LocalEmailExports(tmp_path)
    original = Path.lstat

    class Reparse:
        st_mode = 0o100644
        st_file_attributes = 0x400

    monkeypatch.setattr(Path, "lstat", lambda self: Reparse() if self == source else original(self))
    with pytest.raises(EmailError, match="export_link_denied"):
        await adapter.read_thread("t1")


async def test_hostile_nested_mime_and_many_parts_rejected():
    raw = b"Content-Type: multipart/mixed; boundary=x\n\n"
    for _ in range(40):
        raw += b"--x\nContent-Type: text/plain\n\npart\n"
    raw += b"--x--\n"
    with pytest.raises(EmailError, match="message_rejected"):
        await IsolatedEmailParser().parse(raw, thread_id="t1", message_id="m1")
    body = b"Content-Type: text/plain\n\nbody"
    for i in range(12):
        boundary = f"b{i}".encode()
        body = (
            b"Content-Type: multipart/mixed; boundary="
            + boundary
            + b"\n\n--"
            + boundary
            + b"\n"
            + body
            + b"\n--"
            + boundary
            + b"--\n"
        )
    with pytest.raises(EmailError, match="message_rejected"):
        await IsolatedEmailParser().parse(body, thread_id="t1", message_id="m1")


def test_mapped_network_drive_denied_before_filesystem_access(tmp_path, monkeypatch):
    import jarvis.email.exports as exports

    class Query:
        def __call__(self, anchor):
            assert anchor == tmp_path.anchor
            return 4

    class Kernel:
        GetDriveTypeW = Query()

    monkeypatch.setattr(exports.ctypes, "WinDLL", lambda *a, **k: Kernel())
    with pytest.raises(EmailError, match="local_volume_required"):
        LocalEmailExports(tmp_path)
