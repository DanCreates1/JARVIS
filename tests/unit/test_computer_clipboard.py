from __future__ import annotations

from dataclasses import dataclass

import pytest

from jarvis.computer import clipboard
from jarvis.computer.clipboard import (
    ClipboardChangedError,
    ClipboardError,
    ClipboardSnapshot,
)


@dataclass
class FakeClipboard:
    text: str | None = "before"
    sequence: int = 10
    formats: tuple[int, ...] = (13,)
    mismatch: bool = False
    fail_write: bool = False

    def snapshot(self, *, max_bytes: int) -> ClipboardSnapshot:
        encoded = b"" if self.text is None else self.text.encode("utf-16-le")
        if len(encoded) > max_bytes:
            raise ClipboardError("too large")
        digest = None if self.text is None else clipboard._text_digest(self.text)
        mismatched = self.mismatch and self.text == "after"
        return ClipboardSnapshot(
            sequence=self.sequence,
            text=("wrong" if mismatched else self.text),
            text_sha256=(clipboard._text_digest("wrong") if mismatched else digest),
            utf16_bytes=len(encoded),
            formats=self.formats,
        )

    def replace_text(self, text: str | None) -> None:
        if self.fail_write:
            self.fail_write = False
            raise ClipboardError("busy")
        self.text = text
        self.formats = () if text is None else (clipboard._CF_UNICODETEXT,)
        self.sequence += 1


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> FakeClipboard:
    fake = FakeClipboard()
    monkeypatch.setattr(clipboard, "_BACKEND", fake)
    monkeypatch.setattr(clipboard, "require_non_elevated_process", lambda: None)
    return fake


def test_snapshot_is_bounded_and_digested(fake_backend: FakeClipboard) -> None:
    result = clipboard.get_clipboard_snapshot(max_bytes=100)
    assert result.text == "before"
    assert result.text_sha256 == clipboard._text_digest("before")
    with pytest.raises(ValueError, match="max_bytes"):
        clipboard.get_clipboard_snapshot(max_bytes=0)


def test_utf16_terminator_is_detected_only_on_code_unit_boundary() -> None:
    assert clipboard._decode_clipboard_payload("A".encode("utf-16-le") + b"\x00\x00") == "A"
    assert clipboard._decode_clipboard_payload("AB".encode("utf-16-le") + b"\x00\x00") == "AB"


def test_set_text_verifies_and_is_idempotent(fake_backend: FakeClipboard) -> None:
    receipt = clipboard.set_clipboard_text("after", max_bytes=100)
    assert receipt.changed is True
    assert receipt.verified is True
    assert fake_backend.text == "after"

    repeated = clipboard.set_clipboard_text("after", max_bytes=100)
    assert repeated.changed is False
    assert repeated.before_sequence == repeated.after_sequence


def test_set_rejects_bounds_nul_and_nontext_formats(fake_backend: FakeClipboard) -> None:
    with pytest.raises(ValueError, match="NUL"):
        clipboard.set_clipboard_text("bad\x00text")
    with pytest.raises(ValueError, match="byte limit"):
        clipboard.set_clipboard_text("too long", max_bytes=2)
    fake_backend.formats = (13, 99)
    with pytest.raises(ClipboardError, match="non-text"):
        clipboard.set_clipboard_text("after")


@pytest.mark.parametrize(
    "formats",
    [
        (clipboard._CF_TEXT,),
        (clipboard._CF_OEMTEXT,),
        (clipboard._CF_LOCALE,),
        (clipboard._CF_TEXT, clipboard._CF_OEMTEXT, clipboard._CF_LOCALE),
    ],
)
def test_set_refuses_nonempty_legacy_text_without_materialized_unicode(
    fake_backend: FakeClipboard,
    formats: tuple[int, ...],
) -> None:
    fake_backend.text = None
    fake_backend.formats = formats
    before_sequence = fake_backend.sequence

    with pytest.raises(ClipboardError, match="lacks materialized Unicode"):
        clipboard.set_clipboard_text("after")

    assert fake_backend.text is None
    assert fake_backend.formats == formats
    assert fake_backend.sequence == before_sequence


def test_set_allows_truly_empty_clipboard(fake_backend: FakeClipboard) -> None:
    fake_backend.text = None
    fake_backend.formats = ()

    receipt = clipboard.set_clipboard_text("after")

    assert receipt.before_sha256 is None
    assert receipt.changed is True
    assert fake_backend.text == "after"


def test_unicode_plus_legacy_formats_preserve_semantic_rollback(
    fake_backend: FakeClipboard,
) -> None:
    fake_backend.text = "prior café"
    fake_backend.formats = (
        clipboard._CF_UNICODETEXT,
        clipboard._CF_TEXT,
        clipboard._CF_OEMTEXT,
        clipboard._CF_LOCALE,
    )

    mutation = clipboard.set_clipboard_text("after")
    restored = clipboard.rollback_clipboard_text(
        "prior café",
        expected_current_sha256=mutation.after_sha256,
    )

    assert restored.verified is True
    assert fake_backend.text == "prior café"
    assert fake_backend.formats == (clipboard._CF_UNICODETEXT,)


def test_set_failure_attempts_prior_text_restore(fake_backend: FakeClipboard) -> None:
    fake_backend.fail_write = True
    with pytest.raises(ClipboardError, match="busy"):
        clipboard.set_clipboard_text("after")
    assert fake_backend.text == "before"


def test_postcondition_mismatch_attempts_restore(fake_backend: FakeClipboard) -> None:
    fake_backend.mismatch = True
    with pytest.raises(ClipboardError, match="postcondition"):
        clipboard.set_clipboard_text("after")
    assert fake_backend.text == "before"


def test_rollback_is_bound_to_expected_current_digest(fake_backend: FakeClipboard) -> None:
    clipboard.set_clipboard_text("after")
    receipt = clipboard.rollback_clipboard_text(
        "before",
        expected_current_sha256=clipboard._text_digest("after") or "",
    )
    assert receipt.verified is True
    assert fake_backend.text == "before"

    with pytest.raises(ClipboardChangedError, match="changed"):
        clipboard.rollback_clipboard_text(
            "original",
            expected_current_sha256=clipboard._text_digest("after") or "",
        )


def test_rollback_validates_digest_and_refuses_elevation(
    fake_backend: FakeClipboard, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        clipboard.rollback_clipboard_text("before", expected_current_sha256="bad")
    monkeypatch.setattr(
        clipboard,
        "require_non_elevated_process",
        lambda: (_ for _ in ()).throw(ClipboardError("elevated")),
    )
    with pytest.raises(ClipboardError, match="elevated"):
        clipboard.set_clipboard_text("after")


@pytest.mark.skipif(clipboard.os.name != "nt", reason="Windows-only read probe")
def test_real_windows_clipboard_read_probe_is_non_mutating() -> None:
    snapshot = clipboard.get_clipboard_snapshot(max_bytes=64 * 1024)
    assert snapshot.sequence >= 0
    assert len(snapshot.formats) <= 32
