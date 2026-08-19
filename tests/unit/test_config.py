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
        "context_message_limit",
        "max_tool_iterations",
    }
