from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis.config import Settings, default_data_dir


def test_default_data_dir_uses_platform_location() -> None:
    result = default_data_dir({"LOCALAPPDATA": "C:/runtime-data", "XDG_DATA_HOME": "/tmp/data"})

    assert result.name == "JARVIS"
    assert "JARVIS" in result.parts


def test_settings_derive_database_and_ollama_urls(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    assert settings.database_path == tmp_path / "jarvis.db"
    assert settings.voice_settings_path == tmp_path / "voice-settings.json"
    assert settings.voice_model_dir == tmp_path / "models" / "speech-to-text"
    assert settings.voice_wake_model_dir == tmp_path / "models" / "wake-word"
    assert settings.ollama_chat_url == "http://127.0.0.1:11434/api/chat"
    assert settings.ollama_tags_url == "http://127.0.0.1:11434/api/tags"


def test_remote_ollama_requires_explicit_opt_in(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="ALLOW_REMOTE_OLLAMA"):
        Settings(data_dir=tmp_path, ollama_base_url="http://192.0.2.10:11434", _env_file=None)

    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            data_dir=tmp_path,
            ollama_base_url="http://192.0.2.10:11434",
            allow_remote_ollama=True,
            _env_file=None,
        )

    settings = Settings(
        data_dir=tmp_path,
        ollama_base_url="https://models.example.test",
        allow_remote_ollama=True,
        _env_file=None,
    )
    assert settings.allow_remote_ollama is True


@pytest.mark.parametrize("filename", ["", "../jarvis.db", "nested/jarvis.db", "."])
def test_database_filename_cannot_escape_data_dir(tmp_path: Path, filename: str) -> None:
    with pytest.raises(ValidationError, match="plain filename"):
        Settings(data_dir=tmp_path, database_filename=filename, _env_file=None)


def test_safe_summary_contains_only_declared_diagnostics(tmp_path: Path) -> None:
    summary = Settings(data_dir=tmp_path, _env_file=None).safe_summary()

    assert set(summary) == {
        "data_dir",
        "database_path",
        "ollama_base_url",
        "ollama_model",
        "allow_remote_ollama",
        "request_timeout_seconds",
        "max_provider_response_bytes",
        "context_message_limit",
        "context_recent_message_limit",
        "context_summary_max_chars",
        "simple_local_latency_budget_ms",
        "normal_voice_latency_budget_ms",
        "fast_cloud_latency_budget_ms",
        "deep_reasoning_latency_budget_ms",
        "provider_health_window_size",
        "provider_degradation_seconds",
        "max_tool_iterations",
        "local_model",
        "cloud_policy",
        "max_cloud_cost_usd",
        "groq_configured",
        "gemini_configured",
        "nvidia_configured",
        "fast_model",
        "primary_model",
        "reasoning_model",
        "nvidia_max_output_tokens",
        "nvidia_non_reasoning_max_output_tokens",
        "nvidia_reasoning_budget_tokens",
        "nvidia_max_requests_per_minute",
        "nvidia_max_concurrency",
        "web_host",
        "web_port",
        "computer_access_enabled",
        "computer_access_policy_path",
        "memory_retrieval_enabled",
        "research_enabled",
        "research_search_provider",
        "research_search_endpoint",
        "research_search_timeout_seconds",
        "research_search_max_response_bytes",
        "research_pending_ttl_seconds",
        "research_max_pending_runs",
        "task_execution_enabled",
        "task_max_steps",
        "task_max_wall_seconds",
        "task_max_tokens",
        "task_max_provider_requests",
        "task_max_retries",
        "task_max_tool_calls",
        "task_max_cost_usd",
        "task_max_concurrency",
        "vision_capture_enabled",
        "voice_always_listening_enabled",
        "voice_acoustic_always_listening_enabled",
        "voice_sample_rate_hz",
        "voice_max_capture_seconds",
        "voice_stt_model",
        "voice_stt_language",
        "voice_stt_cpu_threads",
        "voice_stt_timeout_seconds",
        "voice_assistant_timeout_seconds",
        "voice_tts_timeout_seconds",
        "voice_barge_in_enabled",
    }


def test_phase_three_computer_access_is_disabled_by_default(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    assert settings.computer_access_enabled is False
    assert settings.computer_access_policy_path == tmp_path / "computer-access.json"
    assert settings.computer_controlled_root == tmp_path / "controlled-files"


def test_phase_seven_capture_is_disabled_by_default(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    assert settings.vision_capture_enabled is False
    assert settings.vision_settings_path == tmp_path / "vision-settings.json"


def test_research_defaults_are_zero_cost_bounded_and_https_only(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    assert settings.research_enabled is True
    assert settings.research_search_provider == "wikimedia"
    assert str(settings.research_search_endpoint) == "https://en.wikipedia.org/w/api.php"
    assert settings.research_pending_ttl_seconds == 900
    with pytest.raises(ValidationError, match="research provider endpoints must use HTTPS"):
        Settings(
            data_dir=tmp_path,
            research_search_endpoint="http://en.wikipedia.org/w/api.php",
            _env_file=None,
        )


def test_task_execution_defaults_off_with_zero_cost_bounded_parallelism(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    assert settings.task_execution_enabled is False
    assert settings.task_max_cost_usd == 0
    assert settings.task_max_concurrency == 4
    with pytest.raises(ValidationError):
        Settings(data_dir=tmp_path, task_max_cost_usd=0.01, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(data_dir=tmp_path, task_max_concurrency=5, _env_file=None)


def test_cloud_credentials_require_free_tier_and_data_terms_confirmation(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="GROQ_FREE_TIER_CONFIRMED"):
        Settings(data_dir=tmp_path, groq_api_key="secret", _env_file=None)
    with pytest.raises(ValidationError, match="data-terms"):
        Settings(
            data_dir=tmp_path,
            gemini_api_key="secret",
            gemini_free_tier_confirmed=True,
            _env_file=None,
        )
    settings = Settings(
        data_dir=tmp_path,
        groq_api_key="secret",
        groq_free_tier_confirmed=True,
        gemini_api_key="secret",
        gemini_free_tier_confirmed=True,
        gemini_unpaid_data_terms_acknowledged=True,
        local_model="custom:latest",
        _env_file=None,
    )
    assert settings.cloud_enabled is True
    assert settings.effective_local_model == "custom:latest"
    assert "secret" not in str(settings.safe_summary())


def test_nvidia_key_alias_requires_terms_and_enables_cloud(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NVIDIA_API_KEY=test-key\n"
        "JARVIS_NVIDIA_FREE_TIER_CONFIRMED=true\n"
        "JARVIS_NVIDIA_TRIAL_TERMS_ACKNOWLEDGED=true\n",
        encoding="utf-8",
    )

    settings = Settings(data_dir=tmp_path, _env_file=env_file)

    assert settings.nvidia_api_key is not None
    assert settings.nvidia_api_key.get_secret_value() == "test-key"
    assert settings.cloud_enabled is True
    assert settings.reasoning_provider == "nvidia"


def test_nvidia_key_fails_closed_without_trial_terms(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="trial-terms"):
        Settings(
            data_dir=tmp_path,
            nvidia_api_key="secret",
            nvidia_free_tier_confirmed=True,
            _env_file=None,
        )


def test_zero_cost_https_and_loopback_settings_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match=r"exactly \$0"):
        Settings(data_dir=tmp_path, max_cloud_cost_usd=0.01, _env_file=None)
    with pytest.raises(ValidationError, match="loopback"):
        Settings(data_dir=tmp_path, web_host="0.0.0.0", _env_file=None)
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(data_dir=tmp_path, groq_base_url="http://example.test", _env_file=None)


def test_local_inference_bounds_and_keep_alive_are_validated(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    assert settings.effective_local_model == "qwen3:0.6b"
    assert settings.ollama_context_tokens == 4_096
    assert settings.ollama_max_output_tokens == 512
    assert settings.ollama_keep_alive == "5m"
    with pytest.raises(ValidationError):
        Settings(data_dir=tmp_path, ollama_context_tokens=511, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(data_dir=tmp_path, ollama_max_output_tokens=0, _env_file=None)
    with pytest.raises(ValidationError, match="keep-alive"):
        Settings(data_dir=tmp_path, ollama_keep_alive=" ", _env_file=None)


def test_nvidia_reasoning_budget_cannot_exceed_output_limit(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    assert settings.nvidia_max_output_tokens == 1_024
    assert settings.nvidia_non_reasoning_max_output_tokens == 256
    assert settings.nvidia_reasoning_budget_tokens == 256
    with pytest.raises(ValidationError, match="reasoning budget"):
        Settings(
            data_dir=tmp_path,
            nvidia_max_output_tokens=511,
            nvidia_reasoning_budget_tokens=512,
            _env_file=None,
        )
    with pytest.raises(ValidationError, match="non-reasoning output limit"):
        Settings(
            data_dir=tmp_path,
            nvidia_max_output_tokens=255,
            nvidia_non_reasoning_max_output_tokens=256,
            nvidia_reasoning_budget_tokens=255,
            _env_file=None,
        )


def test_phase_two_always_listening_is_hard_disabled(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Settings(data_dir=tmp_path, voice_always_listening_enabled=True, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(data_dir=tmp_path, voice_acoustic_always_listening_enabled=True, _env_file=None)
