"""Atomic non-media storage for the Phase 7A software kill control."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import CaptureControl

_MAX_SETTINGS_BYTES = 16 * 1_024


class VisionSettingsError(RuntimeError):
    """Vision control state cannot be read or updated safely."""


class _Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1, le=1)
    control: CaptureControl = Field(default_factory=CaptureControl)


class VisionSettingsFile:
    """Persist only an enable bit and timestamp; never pixels or capture metadata."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def load_control(self) -> CaptureControl:
        with self._lock:
            return self._load().control

    def save_control(self, control: CaptureControl) -> None:
        with self._lock:
            self._save(_Document(control=control))

    def _load(self) -> _Document:
        if not self.path.exists():
            return _Document()
        if self.path.is_symlink():
            raise VisionSettingsError("vision settings path must not be a symbolic link")
        try:
            if self.path.stat().st_size > _MAX_SETTINGS_BYTES:
                raise VisionSettingsError("vision settings exceed size limit")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return _Document.model_validate(payload)
        except VisionSettingsError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise VisionSettingsError("vision settings are unreadable or invalid") from exc

    def _save(self, document: _Document) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.is_symlink():
                raise VisionSettingsError("vision settings path must not be a symbolic link")
            encoded = document.model_dump_json(indent=2).encode("utf-8")
            if len(encoded) > _MAX_SETTINGS_BYTES:
                raise VisionSettingsError("vision settings exceed size limit")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".vision-settings-",
                suffix=".tmp",
                dir=self.path.parent,
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
        except VisionSettingsError:
            raise
        except OSError as exc:
            raise VisionSettingsError("vision settings could not be saved") from exc
