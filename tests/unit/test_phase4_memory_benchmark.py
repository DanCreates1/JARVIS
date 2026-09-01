from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase4-memory-benchmark.py"
    spec = importlib.util.spec_from_file_location("phase4_memory_benchmark_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = _load_script()


def test_work_directory_is_new_bounded_runtime_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(BENCHMARK, "_RUNTIME_ROOT", runtime.resolve())

    with pytest.raises(ValueError, match="child"):
        BENCHMARK.prepare_work_dir(tmp_path / "outside")
    with pytest.raises(FileExistsError, match="new"):
        BENCHMARK.prepare_work_dir(runtime)
    existing = runtime / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError, match="new"):
        BENCHMARK.prepare_work_dir(existing)

    created = BENCHMARK.prepare_work_dir(runtime / "fresh")
    assert created == (runtime / "fresh").resolve()


def test_benchmark_minimum_counts_and_output_shape_are_enforced() -> None:
    with pytest.raises(SystemExit):
        BENCHMARK.parse_args(
            [
                "--work-dir",
                "runtime/example",
                "--records",
                "2499",
                "--queries",
                "500",
                "--concurrency-operations",
                "100",
            ]
        )
    with pytest.raises(SystemExit):
        BENCHMARK.parse_args(["--work-dir", "runtime/example", "--output", "nested/result.json"])


def test_golden_fixture_covers_all_categories_and_negative_queries() -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "phase4_memory_golden.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    categories = {item["category"] for item in fixture["items"]}
    labels = {item["label"] for item in fixture["items"]}

    assert categories == {"working", "episodic", "profile", "semantic", "task"}
    assert len(fixture["queries"]) >= 25
    assert sum(not query["expected"] for query in fixture["queries"]) >= 5
    assert all(set(query["expected"]).issubset(labels) for query in fixture["queries"])


def test_nearest_rank_summary_and_exclusive_result_write(tmp_path: Path) -> None:
    summary = BENCHMARK.summarize([float(value) for value in range(1, 101)])
    assert summary == {"samples": 100, "p50": 50.5, "p95": 95.0, "max": 100.0}

    output = tmp_path / "result.json"
    BENCHMARK.write_result(output, {"passed": True})
    with pytest.raises(FileExistsError):
        BENCHMARK.write_result(output, {"passed": False})


def test_fixed_targets_do_not_allow_embedding_adoption_without_measured_gain() -> None:
    assert BENCHMARK._TARGETS["precision"] == 0.90
    assert BENCHMARK._TARGETS["recall"] == 0.90
    assert BENCHMARK._TARGETS["false_recall"] == 0.05
    source = Path(BENCHMARK.__file__).read_text(encoding="utf-8")
    assert '"embeddings_enabled": False' in source
    assert '"candidate_samples": 0' in source
    assert "five absolute recall points" in source
