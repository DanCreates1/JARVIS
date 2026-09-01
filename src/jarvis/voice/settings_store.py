"""Small atomic store for voice device selection and the software kill switch."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import DeviceSelection, VoiceControl

_MAX_SETTINGS_BYTES = 64 * 1024


class VoiceSettingsError(RuntimeError):
    """Voice settings cannot be read or updated safely."""


class _Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1, le=1)
    devices: DeviceSelection = Field(default_factory=DeviceSelection)
    control: VoiceControl = Field(default_factory=VoiceControl)


class VoiceSettingsFile:
    """Persist non-secret voice settings without persisting audio or transcripts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def load_devices(self) -> DeviceSelection:
        with self._lock:
            return self._load().devices

    def save_devices(self, selection: DeviceSelection) -> None:
        with self._lock:
            current = self._load()
            self._save(current.model_copy(update={"devices": selection}))

    def load_control(self) -> VoiceControl:
        with self._lock:
            return self._load().control

    def save_control(self, control: VoiceControl) -> None:
        with self._lock:
            current = self._load()
            self._save(current.model_copy(update={"control": control}))

    def _load(self) -> _Document:
        if not self.path.exists():
            return _Document()
        if self.path.is_symlink():
            raise VoiceSettingsError("voice settings path must not be a symbolic link")
        try:
            size = self.path.stat().st_size
            if size > _MAX_SETTINGS_BYTES:
                raise VoiceSettingsError("voice settings exceed size limit")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return _Document.model_validate(payload)
        except VoiceSettingsError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise VoiceSettingsError("voice settings are unreadable or invalid") from exc

    def _save(self, document: _Document) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.is_symlink():
                raise VoiceSettingsError("voice settings path must not be a symbolic link")
            encoded = document.model_dump_json(indent=2).encode("utf-8")
            if len(encoded) > _MAX_SETTINGS_BYTES:
                raise VoiceSettingsError("voice settings exceed size limit")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".voice-settings-",
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
        except VoiceSettingsError:
            raise
        except OSError as exc:
            raise VoiceSettingsError("voice settings could not be saved") from exc
