"""The text profile cannot inherit active optional integrations from dotenv."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jarvis.bootstrap import build_runtime
from jarvis.config import Settings
from jarvis.web import create_app


@pytest.mark.parametrize("profile", ["prototype-text", "daily-text", "private-garmin"])
def test_text_profile_overrides_existing_feature_flags(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    flags = (
        "research_enabled",
        "automatic_research_enabled",
        "attachments_enabled",
        "email_enabled",
        "coding_context_enabled",
        "current_context_enabled",
        "computer_access_enabled",
        "task_execution_enabled",
        "proactivity_enabled",
        "proactivity_runner_enabled",
        "proactivity_task_handoff_enabled",
        "proactivity_pwa_adapter_enabled",
        "vision_capture_enabled",
        "pwa_voice_enabled",
    )
    for flag in flags:
        monkeypatch.setenv(f"JARVIS_{flag.upper()}", "true")
    settings = Settings(
        _env_file=None,
        runtime_profile=profile,  # type: ignore[arg-type]
        local_model="old-model",
        ollama_model="qwen3:0.6b",
        ollama_temperature=1.2,
    )
    assert settings.cloud_policy == "local_only"
    assert settings.local_model == "qwen3:0.6b"
    assert settings.ollama_temperature == 0
    assert not settings.cloud_enabled
    assert all(getattr(settings, flag) is False for flag in flags)
    assert settings.web_host == "127.0.0.1"


@pytest.mark.parametrize("profile", ["prototype-text", "daily-text", "private-garmin"])
def test_text_profile_rejects_remote_model_even_with_old_opt_in(profile: str) -> None:
    with pytest.raises(ValidationError, match="remote Ollama endpoints require"):
        Settings(
            _env_file=None,
            runtime_profile=profile,  # type: ignore[arg-type]
            allow_remote_ollama=True,
            ollama_base_url="https://model.example.test",
        )


@pytest.mark.parametrize("profile", ["standard", "prototype-text", "daily-text", "private-garmin"])
def test_shell_profile_keeps_security_headers(profile: str) -> None:
    settings = Settings(_env_file=None, runtime_profile=profile)  # type: ignore[arg-type]
    # Shell serving needs no runtime initialization, model or production database.
    client = TestClient(create_app(settings))
    response = client.get("/app/")
    assert response.status_code == 200
    assert f'data-profile="{profile}"' in response.text
    assert "content-security-policy" in response.headers
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"


def test_standard_profile_retains_historical_research() -> None:
    settings = Settings(_env_file=None, runtime_profile="standard", research_enabled=True)
    assert settings.research_enabled
    assert settings.cloud_policy == "privacy_aware"


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["prototype-text", "daily-text", "private-garmin"])
async def test_text_runtime_exposes_only_clock_and_never_model_file_tools(
    tmp_path: Path, profile: str
) -> None:
    async with await build_runtime(
        Settings(_env_file=None, data_dir=tmp_path, runtime_profile=profile)  # type: ignore[arg-type]
    ) as runtime:
        assert set(runtime.service.tools) == {"get_current_time"}
        assert not runtime.provider.advertise_tools
        assert runtime.research is None
        assert runtime.provider.policy.local_text_only == (
            profile in {"daily-text", "private-garmin"}
        )
        assert (runtime.service.response_guidance is not None) == (
            profile in {"daily-text", "private-garmin"}
        )
