"""Validated, portable runtime configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def default_data_dir(environment: Mapping[str, str] | None = None) -> Path:
    """Return a per-user data directory outside the source checkout."""
    env = os.environ if environment is None else environment
    if os.name == "nt":
        base = Path(env.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(env.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base.expanduser() / "JARVIS"


class Settings(BaseSettings):
    """JARVIS settings loaded from ``JARVIS_*`` environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="JARVIS_",
        case_sensitive=False,
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=default_data_dir)
    database_filename: str = "jarvis.db"
    ollama_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:11434")
    ollama_model: str = "qwen2.5:3b"
    allow_remote_ollama: bool = False
    request_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    context_message_limit: int = Field(default=40, ge=2, le=500)
    max_tool_iterations: int = Field(default=4, ge=1, le=10)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("data_dir", mode="before")
    @classmethod
    def expand_data_dir(cls, value: object) -> object:
        if isinstance(value, (str, Path)):
            return Path(value).expanduser()
        return value

    @field_validator("database_filename")
    @classmethod
    def validate_database_filename(cls, value: str) -> str:
        if not value or value in {".", ".."} or Path(value).name != value:
            raise ValueError("database filename must be a plain filename")
        return value

    @field_validator("ollama_model")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 200:
            raise ValueError("Ollama model must be a non-empty model tag")
        return normalized

    @model_validator(mode="after")
    def require_explicit_remote_opt_in(self) -> Settings:
        host = self.ollama_base_url.host
        if host not in _LOOPBACK_HOSTS:
            if not self.allow_remote_ollama:
                raise ValueError("remote Ollama endpoints require JARVIS_ALLOW_REMOTE_OLLAMA=true")
            if self.ollama_base_url.scheme != "https":
                raise ValueError("remote Ollama endpoints must use HTTPS")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_filename

    @property
    def ollama_chat_url(self) -> str:
        return f"{str(self.ollama_base_url).rstrip('/')}/api/chat"

    @property
    def ollama_tags_url(self) -> str:
        return f"{str(self.ollama_base_url).rstrip('/')}/api/tags"

    def safe_summary(self) -> dict[str, str | int | float | bool]:
        """Return diagnostic settings without reading or exposing arbitrary environment data."""
        return {
            "data_dir": str(self.data_dir),
            "database_path": str(self.database_path),
            "ollama_base_url": str(self.ollama_base_url),
            "ollama_model": self.ollama_model,
            "allow_remote_ollama": self.allow_remote_ollama,
            "request_timeout_seconds": self.request_timeout_seconds,
            "context_message_limit": self.context_message_limit,
            "max_tool_iterations": self.max_tool_iterations,
        }
