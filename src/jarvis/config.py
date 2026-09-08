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
    ollama_model: str = "qwen3:0.6b"
    ollama_context_tokens: int = Field(default=4_096, ge=512, le=262_144)
    ollama_max_output_tokens: int = Field(default=512, ge=1, le=32_768)
    ollama_keep_alive: str = Field(default="5m", min_length=1, max_length=32)
    local_provider: Literal["ollama"] = "ollama"
    local_model: str | None = None
    fast_provider: Literal["groq"] = "groq"
    fast_model: str = "openai/gpt-oss-20b"
    primary_provider: Literal["groq"] = "groq"
    primary_model: str = "qwen/qwen3.6-27b"
    reasoning_provider: Literal["gemini", "nvidia"] = "nvidia"
    reasoning_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
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
    nvidia_max_output_tokens: int = Field(default=1_024, ge=1, le=32_768)
    nvidia_non_reasoning_max_output_tokens: int = Field(default=256, ge=1, le=32_768)
    nvidia_reasoning_budget_tokens: int = Field(default=256, ge=0, le=32_768)
    nvidia_max_requests_per_minute: int = Field(default=30, ge=1, le=1_000)
    nvidia_max_concurrency: int = Field(default=1, ge=1, le=16)
    allow_remote_ollama: bool = False
    request_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    max_provider_response_bytes: int = Field(default=2_000_000, ge=1_024, le=20_000_000)
    context_message_limit: int = Field(default=40, ge=2, le=500)
    context_recent_message_limit: int = Field(default=8, ge=2, le=40)
    context_summary_max_chars: int = Field(default=2_000, ge=128, le=20_000)
    simple_local_latency_budget_ms: int = Field(default=3_000, ge=100, le=120_000)
    normal_voice_latency_budget_ms: int = Field(default=2_500, ge=100, le=120_000)
    fast_cloud_latency_budget_ms: int = Field(default=2_500, ge=100, le=120_000)
    deep_reasoning_latency_budget_ms: int = Field(default=7_000, ge=100, le=600_000)
    provider_health_window_size: int = Field(default=50, ge=5, le=1_000)
    provider_degradation_seconds: int = Field(default=120, ge=10, le=3_600)
    max_tool_iterations: int = Field(default=4, ge=1, le=10)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    web_host: str = "127.0.0.1"
    web_port: int = Field(default=8765, ge=1, le=65535)
    computer_access_enabled: bool = False
    memory_retrieval_enabled: bool = True
    research_enabled: bool = True
    research_search_provider: Literal["wikimedia"] = "wikimedia"
    research_search_endpoint: AnyHttpUrl = AnyHttpUrl("https://en.wikipedia.org/w/api.php")
    research_search_timeout_seconds: float = Field(default=10, gt=0, le=60)
    research_search_max_response_bytes: int = Field(default=512 * 1_024, ge=1_024, le=2_000_000)
    research_pending_ttl_seconds: int = Field(default=900, ge=30, le=3_600)
    research_max_pending_runs: int = Field(default=10, ge=1, le=100)
    task_execution_enabled: bool = False
    task_max_steps: int = Field(default=100, ge=1, le=100)
    task_max_wall_seconds: float = Field(default=3_600, gt=0, le=86_400)
    task_max_tokens: int = Field(default=100_000, ge=0, le=1_000_000)
    task_max_provider_requests: int = Field(default=100, ge=0, le=1_000)
    task_max_retries: int = Field(default=5, ge=0, le=10)
    task_max_tool_calls: int = Field(default=100, ge=0, le=1_000)
    task_max_cost_usd: float = Field(default=0, ge=0, le=0)
    task_max_concurrency: int = Field(default=4, ge=1, le=4)
    vision_capture_enabled: bool = False
    voice_always_listening_enabled: Literal[False] = False
    voice_acoustic_always_listening_enabled: Literal[False] = False
    voice_sample_rate_hz: Literal[16_000] = 16_000
    voice_frame_samples: Literal[512] = 512
    voice_max_capture_seconds: int = Field(default=30, ge=1, le=120)
    voice_stt_model: str = "base.en"
    voice_stt_language: str = "en"
    voice_stt_cpu_threads: int = Field(default=4, ge=1, le=12)
    voice_stt_timeout_seconds: float = Field(default=90, gt=0, le=300)
    voice_assistant_timeout_seconds: float = Field(default=120, gt=0, le=600)
    voice_tts_timeout_seconds: float = Field(default=30, gt=0, le=120)
    voice_barge_in_enabled: bool = True
    voice_wake_model_path: Path | None = None
    voice_wake_word: str = "hey_jarvis"
    voice_wake_threshold: float = Field(default=0.5, gt=0, le=1)

    @field_validator("data_dir", mode="before")
    @classmethod
    def expand_data_dir(cls, value: object) -> object:
        if isinstance(value, (str, Path)):
            return Path(value).expanduser()
        return value

    @field_validator("voice_wake_model_path", mode="before")
    @classmethod
    def expand_voice_wake_model_path(cls, value: object) -> object:
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

    @field_validator("ollama_keep_alive")
    @classmethod
    def validate_ollama_keep_alive(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Ollama keep-alive must not be blank")
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
        if self.nvidia_reasoning_budget_tokens > self.nvidia_max_output_tokens:
            raise ValueError("NVIDIA reasoning budget must not exceed maximum output tokens")
        if self.nvidia_non_reasoning_max_output_tokens > self.nvidia_max_output_tokens:
            raise ValueError(
                "NVIDIA non-reasoning output limit must not exceed maximum output tokens"
            )
        if self.context_recent_message_limit > self.context_message_limit:
            raise ValueError("recent context limit cannot exceed context message limit")
        if (
            self.groq_base_url.scheme != "https"
            or self.gemini_base_url.scheme != "https"
            or self.nvidia_base_url.scheme != "https"
            or self.research_search_endpoint.scheme != "https"
        ):
            raise ValueError("cloud and research provider endpoints must use HTTPS")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_filename

    @property
    def voice_settings_path(self) -> Path:
        return self.data_dir / "voice-settings.json"

    @property
    def vision_settings_path(self) -> Path:
        return self.data_dir / "vision-settings.json"

    @property
    def computer_access_policy_path(self) -> Path:
        return self.data_dir / "computer-access.json"

    @property
    def computer_controlled_root(self) -> Path:
        return self.data_dir / "controlled-files"

    @property
    def voice_model_dir(self) -> Path:
        return self.data_dir / "models" / "speech-to-text"

    @property
    def voice_wake_model_dir(self) -> Path:
        return self.data_dir / "models" / "wake-word"

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
            "nvidia_non_reasoning_max_output_tokens": (self.nvidia_non_reasoning_max_output_tokens),
            "nvidia_reasoning_budget_tokens": self.nvidia_reasoning_budget_tokens,
            "nvidia_max_requests_per_minute": self.nvidia_max_requests_per_minute,
            "nvidia_max_concurrency": self.nvidia_max_concurrency,
            "allow_remote_ollama": self.allow_remote_ollama,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_provider_response_bytes": self.max_provider_response_bytes,
            "context_message_limit": self.context_message_limit,
            "context_recent_message_limit": self.context_recent_message_limit,
            "context_summary_max_chars": self.context_summary_max_chars,
            "simple_local_latency_budget_ms": self.simple_local_latency_budget_ms,
            "normal_voice_latency_budget_ms": self.normal_voice_latency_budget_ms,
            "fast_cloud_latency_budget_ms": self.fast_cloud_latency_budget_ms,
            "deep_reasoning_latency_budget_ms": self.deep_reasoning_latency_budget_ms,
            "provider_health_window_size": self.provider_health_window_size,
            "provider_degradation_seconds": self.provider_degradation_seconds,
            "max_tool_iterations": self.max_tool_iterations,
            "web_host": self.web_host,
            "web_port": self.web_port,
            "computer_access_enabled": self.computer_access_enabled,
            "memory_retrieval_enabled": self.memory_retrieval_enabled,
            "research_enabled": self.research_enabled,
            "research_search_provider": self.research_search_provider,
            "research_search_endpoint": str(self.research_search_endpoint),
            "research_search_timeout_seconds": self.research_search_timeout_seconds,
            "research_search_max_response_bytes": self.research_search_max_response_bytes,
            "research_pending_ttl_seconds": self.research_pending_ttl_seconds,
            "research_max_pending_runs": self.research_max_pending_runs,
            "task_execution_enabled": self.task_execution_enabled,
            "task_max_steps": self.task_max_steps,
            "task_max_wall_seconds": self.task_max_wall_seconds,
            "task_max_tokens": self.task_max_tokens,
            "task_max_provider_requests": self.task_max_provider_requests,
            "task_max_retries": self.task_max_retries,
            "task_max_tool_calls": self.task_max_tool_calls,
            "task_max_cost_usd": self.task_max_cost_usd,
            "task_max_concurrency": self.task_max_concurrency,
            "vision_capture_enabled": self.vision_capture_enabled,
            "computer_access_policy_path": str(self.computer_access_policy_path),
            "voice_always_listening_enabled": self.voice_always_listening_enabled,
            "voice_acoustic_always_listening_enabled": (
                self.voice_acoustic_always_listening_enabled
            ),
            "voice_sample_rate_hz": self.voice_sample_rate_hz,
            "voice_max_capture_seconds": self.voice_max_capture_seconds,
            "voice_stt_model": self.voice_stt_model,
            "voice_stt_language": self.voice_stt_language,
            "voice_stt_cpu_threads": self.voice_stt_cpu_threads,
            "voice_stt_timeout_seconds": self.voice_stt_timeout_seconds,
            "voice_assistant_timeout_seconds": self.voice_assistant_timeout_seconds,
            "voice_tts_timeout_seconds": self.voice_tts_timeout_seconds,
            "voice_barge_in_enabled": self.voice_barge_in_enabled,
        }
