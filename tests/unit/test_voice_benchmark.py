from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from jarvis.config import Settings


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "voice-benchmark.py"
    spec = importlib.util.spec_from_file_location("voice_benchmark_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["voice_benchmark_test_module"] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = _load_script()


def test_local_model_residency_uses_effective_default_alias(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)

    assert settings.local_model is None
    assert settings.effective_local_model == "qwen3:0.6b"
    assert BENCHMARK.local_model_is_loaded(settings, ["qwen3:0.6b"])
    assert not BENCHMARK.local_model_is_loaded(settings, ["another:latest"])


def test_local_model_residency_honors_explicit_override(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, local_model="custom:latest", _env_file=None)

    assert BENCHMARK.local_model_is_loaded(settings, ["custom:latest"])
    assert not BENCHMARK.local_model_is_loaded(settings, ["qwen3:0.6b"])


@pytest.mark.parametrize("temperature", ["46", "46.84"])
def test_gpu_memory_measurement_accepts_fractional_driver_temperature(
    monkeypatch: pytest.MonkeyPatch, temperature: str
) -> None:
    monkeypatch.setattr(
        BENCHMARK.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=f"2271, 4096, 0, {temperature}\n"),
    )
    sample = BENCHMARK.nvidia_gpu_snapshot()
    assert sample == {
        "memory_used_mib": 2271,
        "memory_total_mib": 4096,
        "utilization_percent": 0,
        "temperature_c": float(temperature),
    }


@pytest.mark.parametrize("output", ["", "2271,4096", "2271,4096,0,N/A", "2271,4096,0,nan"])
def test_missing_gpu_telemetry_stays_unavailable(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    monkeypatch.setattr(
        BENCHMARK.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=output)
    )
    assert BENCHMARK.nvidia_gpu_snapshot() is None
