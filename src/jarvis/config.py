"""Validated, portable runtime configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr, field_validator, model_validator
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
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        env_prefix="JARVIS_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    data_dir: Path = Field(default_factory=default_data_dir)
    database_filename: str = "jarvis.db"
    ollama_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:11434")
    ollama_model: str = "nemotron-3-nano:4b"
    local_provider: Literal["ollama"] = "ollama"
    local_model: str | None = None
    fast_provider: Literal["groq"] = "groq"
    fast_model: str = "openai/gpt-oss-20b"
    primary_provider: Literal["groq"] = "groq"
    primary_model: str = "qwen/qwen3.6-27b"
    reasoning_provider: Literal["gemini", "nvidia"] = "nvidia"
    reasoning_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    cloud_policy: Literal["privacy_aware", "local_only"] = "privacy_aware"
    max_cloud_cost_usd: float = Field(default=0, ge=0)
    groq_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    nvidia_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("JARVIS_NVIDIA_API_KEY", "NVIDIA_API_KEY"),
    )
    groq_free_tier_confirmed: bool = False
    gemini_free_tier_confirmed: bool = False
    gemini_unpaid_data_terms_acknowledged: bool = False
    nvidia_free_tier_confirmed: bool = False
    nvidia_trial_terms_acknowledged: bool = False
    groq_base_url: AnyHttpUrl = AnyHttpUrl("https://api.groq.com/openai/v1")
    gemini_base_url: AnyHttpUrl = AnyHttpUrl("https://generativelanguage.googleapis.com/v1beta")
    nvidia_base_url: AnyHttpUrl = AnyHttpUrl("https://integrate.api.nvidia.com/v1")
    nvidia_max_output_tokens: int = Field(default=4_096, ge=1, le=32_768)
    nvidia_max_requests_per_minute: int = Field(default=30, ge=1, le=1_000)
    nvidia_max_concurrency: int = Field(default=1, ge=1, le=16)
    allow_remote_ollama: bool = False
    request_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    max_provider_response_bytes: int = Field(default=2_000_000, ge=1_024, le=20_000_000)
    context_message_limit: int = Field(default=40, ge=2, le=500)
    max_tool_iterations: int = Field(default=4, ge=1, le=10)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    web_host: str = "127.0.0.1"
    web_port: int = Field(default=8765, ge=1, le=65535)

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

    @field_validator(
        "ollama_model", "local_model", "fast_model", "primary_model", "reasoning_model"
    )
    @classmethod
    def validate_model_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or len(normalized) > 200:
            raise ValueError("model ID must be non-empty and at most 200 characters")
        return normalized

    @field_validator("web_host")
    @classmethod
    def require_loopback_web_host(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in _LOOPBACK_HOSTS:
            raise ValueError("Phase 1 browser chat must bind to a loopback host")
        return normalized

    @model_validator(mode="after")
    def require_explicit_remote_opt_in(self) -> Settings:
        host = self.ollama_base_url.host
        if host not in _LOOPBACK_HOSTS:
            if not self.allow_remote_ollama:
                raise ValueError("remote Ollama endpoints require JARVIS_ALLOW_REMOTE_OLLAMA=true")
            if self.ollama_base_url.scheme != "https":
                raise ValueError("remote Ollama endpoints must use HTTPS")
        if self.max_cloud_cost_usd != 0:
            raise ValueError("Phase 1 cloud cost is hard-capped at exactly $0")
        if self.groq_api_key is not None and not self.groq_free_tier_confirmed:
            raise ValueError("Groq credentials require JARVIS_GROQ_FREE_TIER_CONFIRMED=true")
        if self.gemini_api_key is not None and not (
            self.gemini_free_tier_confirmed and self.gemini_unpaid_data_terms_acknowledged
        ):
            raise ValueError(
                "Gemini credentials require free-tier confirmation and unpaid data-terms "
                "acknowledgement"
            )
        if self.nvidia_api_key is not None and not (
            self.nvidia_free_tier_confirmed and self.nvidia_trial_terms_acknowledged
        ):
            raise ValueError(
                "NVIDIA credentials require free-tier confirmation and trial-terms acknowledgement"
            )
        if (
            self.groq_base_url.scheme != "https"
            or self.gemini_base_url.scheme != "https"
            or self.nvidia_base_url.scheme != "https"
        ):
            raise ValueError("cloud provider endpoints must use HTTPS")
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

    @property
    def effective_local_model(self) -> str:
        return self.local_model or self.ollama_model

    @property
    def cloud_enabled(self) -> bool:
        return self.cloud_policy == "privacy_aware" and (
            self.groq_api_key is not None
            or self.gemini_api_key is not None
            or self.nvidia_api_key is not None
        )

    def safe_summary(self) -> dict[str, str | int | float | bool]:
        """Return diagnostic settings without reading or exposing arbitrary environment data."""
        return {
            "data_dir": str(self.data_dir),
            "database_path": str(self.database_path),
            "ollama_base_url": str(self.ollama_base_url),
            "ollama_model": self.ollama_model,
            "local_model": self.effective_local_model,
            "cloud_policy": self.cloud_policy,
            "max_cloud_cost_usd": self.max_cloud_cost_usd,
            "groq_configured": self.groq_api_key is not None,
            "gemini_configured": self.gemini_api_key is not None,
            "nvidia_configured": self.nvidia_api_key is not None,
            "fast_model": self.fast_model,
            "primary_model": self.primary_model,
            "reasoning_model": self.reasoning_model,
            "nvidia_max_output_tokens": self.nvidia_max_output_tokens,
            "nvidia_max_requests_per_minute": self.nvidia_max_requests_per_minute,
            "nvidia_max_concurrency": self.nvidia_max_concurrency,
            "allow_remote_ollama": self.allow_remote_ollama,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_provider_response_bytes": self.max_provider_response_bytes,
            "context_message_limit": self.context_message_limit,
            "max_tool_iterations": self.max_tool_iterations,
            "web_host": self.web_host,
            "web_port": self.web_port,
        }
