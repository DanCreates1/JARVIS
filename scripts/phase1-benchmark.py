"""Reproducible Phase 1 text acceptance benchmark using fixed synthetic/public fixtures only."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import hashlib
import json
import math
import os
import platform
import stat
import subprocess
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Final

import httpx
from pydantic import ValidationError

from jarvis.bootstrap import RuntimeComponents, build_runtime
from jarvis.config import Settings
from jarvis.core import (
    AssistantRequest,
    MessageRole,
    ModelRole,
    ReasoningLevel,
    RuntimeEventType,
    RuntimeStatus,
    SensitivityClass,
)
from jarvis.llm import PrivacyGate

LOCAL_MODEL: Final = "nemotron-3-nano:4b"
HOSTED_MODEL: Final = "nvidia/nemotron-3-ultra-550b-a55b"
MIN_SAMPLES: Final = 20
MAX_SAMPLES: Final = 100
MAX_WARMUPS: Final = 5
MAX_REPORT_BYTES: Final = 2 * 1024 * 1024
DEFAULT_HOSTED_INTERVAL_SECONDS: Final = 2.1
HOSTED_CAPACITY_STOP: Final = " ".join(
    (
        "Hosted capacity signal reached a fail-closed stop;",
        "no ceiling probing continued.",
    )
)

THRESHOLDS_MS: Final[dict[str, tuple[float, float]]] = {
    "deterministic": (300.0, 800.0),
    "local": (1_500.0, 3_000.0),
    "hosted-simple": (1_000.0, 2_500.0),
    "hosted-complex": (3_000.0, 7_000.0),
}

DETERMINISTIC_PROMPTS: Final = (
    "What is the current time?",
    "What's the time now?",
    "Current time?",
    "Please tell me the time.",
)
LOCAL_PROMPTS: Final = (
    "My password is synthetic-example-only. Give two general password safety tips.",
    "My medical record is a synthetic fixture. Reply with one privacy reminder.",
    "My email is benchmark@example.invalid. State that it should remain private.",
    "Read C:\\Synthetic\\private-fixture.txt and explain why local handling is required.",
)
HOSTED_SIMPLE_PROMPTS: Final = (
    "Reply with exactly: PUBLIC FIXTURE READY",
    "Name the largest planet in the Solar System in one sentence.",
    "State the chemical symbol for gold in one sentence.",
    "Give one public fact about the Moon without personal context.",
)
HOSTED_COMPLEX_PROMPTS: Final = (
    "Do complex analysis of a public puzzle: explain why a binary search is logarithmic.",
    "Provide a concise architecture review of a public stateless URL shortener design.",
    "Prove the identity: the sum of the first n odd positive integers is n squared.",
    "Explain a difficult coding trade-off between optimistic and pessimistic concurrency.",
)


class BenchmarkBlocked(RuntimeError):
    """A required external condition is unavailable; no unsafe workaround is attempted."""


@dataclass(frozen=True, slots=True)
class Fixture:
    fixture_id: str
    prompt: str


class HostedPacer:
    """Enforce bounded serial hosted requests independently of provider-client reuse."""

    def __init__(self, interval_seconds: float) -> None:
        self._interval_seconds = interval_seconds
        self._last_started: float | None = None

    async def wait(self) -> None:
        if self._last_started is not None:
            remaining = self._interval_seconds - (time.monotonic() - self._last_started)
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_started = time.monotonic()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure Phase 1 first-useful-output and completion latency with fixed fixtures. "
            "Prompts and responses are never written to the report."
        )
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("runtime/phase1-benchmark"),
        help="New direct child of repository runtime/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("phase1-benchmark.json"),
        help="JSON filename directly beneath --work-dir.",
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=tuple(THRESHOLDS_MS),
        default=["deterministic", "local"],
    )
    parser.add_argument("--samples", type=int, default=MIN_SAMPLES)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument(
        "--include-hosted",
        action="store_true",
        help="Permit fixed public NVIDIA fixtures after repository confirmation checks pass.",
    )
    parser.add_argument(
        "--confirm-public-fixtures",
        action="store_true",
        help="Confirm that only the compiled-in public fixtures may be sent to NVIDIA.",
    )
    parser.add_argument(
        "--hosted-min-interval-seconds",
        type=float,
        default=DEFAULT_HOSTED_INTERVAL_SECONDS,
    )
    parser.add_argument("--enforce", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not MIN_SAMPLES <= args.samples <= MAX_SAMPLES:
        raise ValueError(f"--samples must be between {MIN_SAMPLES} and {MAX_SAMPLES}")
    if not 0 <= args.warmups <= MAX_WARMUPS:
        raise ValueError(f"--warmups must be between 0 and {MAX_WARMUPS}")
    if args.hosted_min_interval_seconds < DEFAULT_HOSTED_INTERVAL_SECONDS:
        raise ValueError(
            "--hosted-min-interval-seconds cannot be below the conservative 2.1-second guard"
        )
    hosted_requested = any(profile.startswith("hosted-") for profile in args.profiles)
    if hosted_requested and not (args.include_hosted and args.confirm_public_fixtures):
        raise ValueError("hosted profiles require --include-hosted and --confirm-public-fixtures")
    if hosted_requested:
        gate = PrivacyGate()
        hosted_prompts = (*HOSTED_SIMPLE_PROMPTS, *HOSTED_COMPLEX_PROMPTS)
        if any(gate.classify(prompt) is not SensitivityClass.PUBLIC for prompt in hosted_prompts):
            raise ValueError("every compiled hosted fixture must classify public")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def resolve_paths(work_dir_arg: Path, output_arg: Path) -> tuple[Path, Path]:
    repository = _repository_root()
    runtime_root = (repository / "runtime").resolve(strict=True)
    work_dir = (
        work_dir_arg.resolve(strict=False)
        if work_dir_arg.is_absolute()
        else (repository / work_dir_arg).resolve(strict=False)
    )
    if work_dir.parent != runtime_root:
        raise ValueError("--work-dir must be a new direct child of repository runtime/")
    output = (
        output_arg.resolve(strict=False)
        if output_arg.is_absolute()
        else (work_dir / output_arg).resolve(strict=False)
    )
    if output.parent != work_dir or output.suffix.casefold() != ".json":
        raise ValueError("--output must be one JSON file directly beneath --work-dir")
    if work_dir.exists():
        raise ValueError("--work-dir must not already exist")
    work_dir.mkdir(exist_ok=False)
    verified = work_dir.resolve(strict=True)
    if (
        verified != work_dir
        or verified.parent != runtime_root
        or not verified.is_dir()
        or _is_reparse_point(verified)
    ):
        raise ValueError("created work directory is not a normal repository runtime child")
    if output.parent != verified or output.exists():
        raise ValueError("verified output escaped the new work directory or already exists")
    return verified, output


def nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    if not 0 < quantile <= 1:
        raise ValueError("quantile must be in (0, 1]")
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return round(ordered[rank - 1], 3)


def _fixture(prompts: Sequence[str], profile: str, index: int) -> Fixture:
    return Fixture(fixture_id=f"{profile}-{index + 1:03d}", prompt=prompts[index % len(prompts)])


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


async def run_sample(
    runtime: RuntimeComponents,
    fixture: Fixture,
    *,
    requested_role: ModelRole | None,
    reasoning_level: ReasoningLevel | None,
    expected_provider: str,
) -> dict[str, Any]:
    started = time.perf_counter_ns()
    first_useful_ms: float | None = None
    routing = None
    usage = None
    result = None
    request = AssistantRequest(
        user_input=fixture.prompt,
        metadata={"source": "phase1-benchmark", "fixture_id": fixture.fixture_id},
        requested_model_role=requested_role,
        reasoning_level=reasoning_level,
    )
    async for frame in runtime.service.stream(request):
        if frame.event is not None:
            event = frame.event
            if event.routing is not None:
                routing = event.routing
            if event.usage is not None:
                usage = event.usage
            if (
                first_useful_ms is None
                and event.type is RuntimeEventType.MESSAGE_PERSISTED
                and event.message is not None
                and event.message.role is MessageRole.ASSISTANT
                and event.message.content.strip()
            ):
                first_useful_ms = (time.perf_counter_ns() - started) / 1_000_000
        else:
            result = frame.result
    total_ms = (time.perf_counter_ns() - started) / 1_000_000
    if result is None:
        raise RuntimeError("runtime stream ended without a terminal result")
    if first_useful_ms is None and result.status is RuntimeStatus.COMPLETED and result.reply:
        first_useful_ms = total_ms

    if usage is not None:
        actual_provider = usage.provider
        model_id = usage.model_id
    elif routing is not None:
        selected = runtime.provider.providers.get(routing.chosen_role)
        actual_provider = selected.profile.provider if selected is not None else "unconfigured"
        model_id = selected.profile.model_id if selected is not None else None
    else:
        actual_provider = "deterministic"
        model_id = None

    useful_success = (
        result.status is RuntimeStatus.COMPLETED
        and result.reply is not None
        and bool(result.reply.strip())
        and first_useful_ms is not None
    )
    route_success = actual_provider == expected_provider
    failure_code = result.error.code.value if result.error is not None else None
    if useful_success and not route_success:
        failure_code = "unexpected_provider_or_fallback"
    elif not useful_success and failure_code is None:
        failure_code = "no_useful_assistant_output"

    return {
        "fixture_id": fixture.fixture_id,
        "prompt_sha256": _prompt_hash(fixture.prompt),
        "prompt_bytes": len(fixture.prompt.encode("utf-8")),
        "status": result.status.value,
        "successful_useful_response": useful_success,
        "expected_route_success": route_success,
        "first_useful_output_ms": round(first_useful_ms, 3)
        if first_useful_ms is not None
        else None,
        "total_completion_ms": round(total_ms, 3),
        "output_bytes": len((result.reply or "").encode("utf-8")),
        "actual_provider": actual_provider,
        "actual_model": model_id,
        "actual_role": routing.chosen_role.value if routing is not None else "deterministic",
        "fallback_used": routing.fallback_used if routing is not None else False,
        "failure_code": failure_code,
        "provider_latency_ms": round(usage.latency_ms, 3) if usage is not None else None,
        "input_tokens": usage.input_tokens if usage is not None else None,
        "output_tokens": usage.output_tokens if usage is not None else None,
        "rate_limit_remaining": usage.rate_limit_remaining if usage is not None else None,
        "adapter_streaming": False,
        "first_useful_definition": "first persisted nonblank assistant message",
    }


def summarize_state(
    profile: str,
    state: str,
    samples: Sequence[dict[str, Any]],
    *,
    warmups: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    successful = [
        sample
        for sample in samples
        if sample["successful_useful_response"] and sample["expected_route_success"]
    ]
    first = [float(sample["first_useful_output_ms"]) for sample in successful]
    total = [float(sample["total_completion_ms"]) for sample in successful]
    output_sizes = [float(sample["output_bytes"]) for sample in successful]
    p50_target, p95_target = THRESHOLDS_MS[profile]
    p50 = nearest_rank(first, 0.50)
    p95 = nearest_rank(first, 0.95)
    threshold_pass = (
        len(samples) >= MIN_SAMPLES
        and len(successful) == len(samples)
        and p50 is not None
        and p95 is not None
        and p50 <= p50_target
        and p95 <= p95_target
    )
    routes = Counter(str(sample["actual_provider"]) for sample in samples)
    p95_rank = math.ceil(0.95 * len(successful)) if successful else None
    return {
        "profile": profile,
        "state": state,
        "sample_count": len(samples),
        "successful_response_count": len(successful),
        "failure_count": len(samples) - len(successful),
        "warmup_count_excluded": len(warmups),
        "warmups": list(warmups),
        "first_useful_output_ms": {
            "nearest_rank_p50": p50,
            "nearest_rank_p95": p95,
            "p50_target": p50_target,
            "p95_target": p95_target,
        },
        "total_completion_ms": {
            "nearest_rank_p50": nearest_rank(total, 0.50),
            "nearest_rank_p95": nearest_rank(total, 0.95),
        },
        "output_bytes": {
            "nearest_rank_p50": nearest_rank(output_sizes, 0.50),
            "nearest_rank_p95": nearest_rank(output_sizes, 0.95),
        },
        "actual_provider_counts": dict(sorted(routes.items())),
        "uncertainty": {
            "successful_n": len(successful),
            "p95_nearest_rank": p95_rank,
            "tail_observations_at_or_above_p95_rank": (
                len(successful) - p95_rank + 1 if p95_rank is not None else 0
            ),
            "warning": (
                "With fewer than 40 samples the p95 tail is represented by at most two "
                "observations; repeat with 40+ when practical."
                if len(successful) < 40
                else "Tail estimate remains workload- and environment-specific."
            ),
        },
        "threshold_pass": threshold_pass,
        "samples": list(samples),
    }


def _local_settings(data_dir: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=data_dir,
        cloud_policy="local_only",
        local_model=LOCAL_MODEL,
        computer_access_enabled=False,
    )


def _hosted_settings(data_dir: Path) -> Settings:
    try:
        settings = Settings(data_dir=data_dir, computer_access_enabled=False)
    except ValidationError as error:
        raise BenchmarkBlocked(
            "NVIDIA configuration failed closed; verify key presence and both confirmations."
        ) from error
    if settings.reasoning_provider != "nvidia" or settings.reasoning_model != HOSTED_MODEL:
        raise BenchmarkBlocked(
            "Configured hosted reasoning path is not the required Nemotron model."
        )
    if not (
        settings.nvidia_api_key is not None
        and settings.nvidia_free_tier_confirmed
        and settings.nvidia_trial_terms_acknowledged
    ):
        raise BenchmarkBlocked(
            "Hosted access requires an existing key, free-tier confirmation, "
            "and trial acknowledgement."
        )
    if settings.max_cloud_cost_usd != 0:
        raise BenchmarkBlocked("Hosted benchmark requires the unchanged zero-dollar policy.")
    return settings


async def _is_model_loaded(base_url: str, model: str) -> bool:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{base_url.rstrip('/')}/api/ps")
    response.raise_for_status()
    document = response.json()
    entries = document.get("models") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        raise BenchmarkBlocked("Ollama /api/ps did not return a models list.")
    return any(
        isinstance(entry, dict) and (entry.get("name") == model or entry.get("model") == model)
        for entry in entries
    )


async def evict_local_model(settings: Settings) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        process = await asyncio.create_subprocess_exec(
            "ollama",
            "stop",
            LOCAL_MODEL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as error:
        raise BenchmarkBlocked(
            "Could not execute the approved Ollama CLI for model eviction."
        ) from error
    code = await process.wait()
    if code != 0:
        raise BenchmarkBlocked("Ollama refused the explicit model-stop request.")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not await _is_model_loaded(str(settings.ollama_base_url), LOCAL_MODEL):
            return {
                "verified": True,
                "method": "ollama stop plus GET /api/ps absence check",
                "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
                "os_cache_flushed": False,
            }
        await asyncio.sleep(0.25)
    raise BenchmarkBlocked("Local model remained loaded after the bounded eviction check.")


async def _warmups(
    runtime: RuntimeComponents,
    prompts: Sequence[str],
    profile: str,
    count: int,
    *,
    requested_role: ModelRole | None,
    reasoning_level: ReasoningLevel | None,
    expected_provider: str,
    pacer: HostedPacer | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index in range(count):
        if pacer is not None:
            await pacer.wait()
        record = await run_sample(
            runtime,
            _fixture(prompts, f"{profile}-warmup", index),
            requested_role=requested_role,
            reasoning_level=reasoning_level,
            expected_provider=expected_provider,
        )
        records.append(record)
        if not (record["successful_useful_response"] and record["expected_route_success"]):
            raise BenchmarkBlocked(f"{profile} warm-up failed; warm measurements are invalid.")
    return records


async def benchmark_deterministic(args: argparse.Namespace, work_dir: Path) -> dict[str, Any]:
    settings = _local_settings(work_dir / "data-deterministic")
    async with await build_runtime(settings) as runtime:
        samples = [
            await run_sample(
                runtime,
                _fixture(DETERMINISTIC_PROMPTS, "deterministic", index),
                requested_role=None,
                reasoning_level=None,
                expected_provider="deterministic",
            )
            for index in range(args.samples)
        ]
    return {"states": [summarize_state("deterministic", "steady", samples)]}


async def benchmark_local(args: argparse.Namespace, work_dir: Path) -> dict[str, Any]:
    cold_samples: list[dict[str, Any]] = []
    evictions: list[dict[str, Any]] = []
    for index in range(args.samples):
        settings = _local_settings(work_dir / "data-local-cold" / f"sample-{index + 1:03d}")
        evictions.append(await evict_local_model(settings))
        async with await build_runtime(settings) as runtime:
            cold_samples.append(
                await run_sample(
                    runtime,
                    _fixture(LOCAL_PROMPTS, "local-cold", index),
                    requested_role=None,
                    reasoning_level=None,
                    expected_provider="ollama",
                )
            )

    warm_settings = _local_settings(work_dir / "data-local-warm")
    async with await build_runtime(warm_settings) as runtime:
        warmups = await _warmups(
            runtime,
            LOCAL_PROMPTS,
            "local",
            args.warmups,
            requested_role=None,
            reasoning_level=None,
            expected_provider="ollama",
        )
        if not await _is_model_loaded(str(warm_settings.ollama_base_url), LOCAL_MODEL):
            raise BenchmarkBlocked("Local warm-up did not leave the required model resident.")
        warm_samples = [
            await run_sample(
                runtime,
                _fixture(LOCAL_PROMPTS, "local-warm", index),
                requested_role=None,
                reasoning_level=None,
                expected_provider="ollama",
            )
            for index in range(args.samples)
        ]
    return {
        "cold_eviction": {
            "required_before_each_sample": True,
            "verified_count": sum(bool(item["verified"]) for item in evictions),
            "observations": evictions,
        },
        "states": [
            summarize_state("local", "cold", cold_samples),
            summarize_state("local", "warm", warm_samples, warmups=warmups),
        ],
    }


async def _validate_hosted_catalog(settings: Settings) -> None:
    async with await build_runtime(settings) as runtime:
        results = await runtime.provider.validate_models()
    if not results.get(ModelRole.REASONING, False):
        raise BenchmarkBlocked("NVIDIA catalog did not expose the exact configured Nemotron model.")


async def benchmark_hosted(
    args: argparse.Namespace,
    work_dir: Path,
    profile: str,
    prompts: Sequence[str],
    reasoning_level: ReasoningLevel,
    pacer: HostedPacer,
) -> dict[str, Any]:
    validation_settings = _hosted_settings(work_dir / f"data-{profile}-catalog")
    await pacer.wait()
    await _validate_hosted_catalog(validation_settings)

    cold_samples: list[dict[str, Any]] = []
    for index in range(args.samples):
        await pacer.wait()
        settings = _hosted_settings(work_dir / f"data-{profile}-cold" / f"sample-{index + 1:03d}")
        async with await build_runtime(settings) as runtime:
            record = await run_sample(
                runtime,
                _fixture(prompts, f"{profile}-cold", index),
                requested_role=ModelRole.REASONING,
                reasoning_level=reasoning_level,
                expected_provider="nvidia",
            )
        cold_samples.append(record)
        if (
            record["fallback_used"]
            or record["rate_limit_remaining"] == 0
            or record["failure_code"] == "provider_error"
        ):
            return {
                "hosted_cold_definition": (
                    "fresh JARVIS runtime and HTTP client; not provider eviction"
                ),
                "bounded_serial_interval_seconds": args.hosted_min_interval_seconds,
                "states": [summarize_state(profile, "cold-client", cold_samples)],
                "blocked": True,
                "blocker": HOSTED_CAPACITY_STOP,
            }

    warm_settings = _hosted_settings(work_dir / f"data-{profile}-warm")
    async with await build_runtime(warm_settings) as runtime:
        warmups = await _warmups(
            runtime,
            prompts,
            profile,
            args.warmups,
            requested_role=ModelRole.REASONING,
            reasoning_level=reasoning_level,
            expected_provider="nvidia",
            pacer=pacer,
        )
        warm_samples: list[dict[str, Any]] = []
        for index in range(args.samples):
            await pacer.wait()
            record = await run_sample(
                runtime,
                _fixture(prompts, f"{profile}-warm", index),
                requested_role=ModelRole.REASONING,
                reasoning_level=reasoning_level,
                expected_provider="nvidia",
            )
            warm_samples.append(record)
            if (
                record["fallback_used"]
                or record["rate_limit_remaining"] == 0
                or record["failure_code"] == "provider_error"
            ):
                return {
                    "hosted_cold_definition": (
                        "fresh JARVIS runtime and HTTP client; not provider eviction"
                    ),
                    "bounded_serial_interval_seconds": args.hosted_min_interval_seconds,
                    "states": [
                        summarize_state(profile, "cold-client", cold_samples),
                        summarize_state(profile, "warm-client", warm_samples, warmups=warmups),
                    ],
                    "blocked": True,
                    "blocker": HOSTED_CAPACITY_STOP,
                }
    return {
        "hosted_cold_definition": "fresh JARVIS runtime and HTTP client; not provider eviction",
        "bounded_serial_interval_seconds": args.hosted_min_interval_seconds,
        "states": [
            summarize_state(profile, "cold-client", cold_samples),
            summarize_state(profile, "warm-client", warm_samples, warmups=warmups),
        ],
    }


async def collect_local_model_metadata() -> dict[str, Any]:
    settings = _local_settings(_repository_root() / "runtime" / "phase1-metadata-unused")
    base_url = str(settings.ollama_base_url).rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        tags_response, show_response = await asyncio.gather(
            client.get(f"{base_url}/api/tags"),
            client.post(f"{base_url}/api/show", json={"model": LOCAL_MODEL, "verbose": False}),
        )
    tags_response.raise_for_status()
    show_response.raise_for_status()
    tags = tags_response.json()
    show = show_response.json()
    entries = tags.get("models", []) if isinstance(tags, dict) else []
    entry = next(
        (
            item
            for item in entries
            if isinstance(item, dict)
            and (item.get("name") == LOCAL_MODEL or item.get("model") == LOCAL_MODEL)
        ),
        {},
    )
    model_info = show.get("model_info", {}) if isinstance(show, dict) else {}
    selected_info = {
        key: value
        for key, value in model_info.items()
        if isinstance(key, str)
        and (
            key.endswith("context_length")
            or key in {"general.parameter_count", "general.file_type"}
        )
    }
    return {
        "model": LOCAL_MODEL,
        "installed": bool(entry),
        "digest": entry.get("digest") if isinstance(entry, dict) else None,
        "size_bytes": entry.get("size") if isinstance(entry, dict) else None,
        "details": show.get("details") if isinstance(show, dict) else None,
        "capabilities": show.get("capabilities") if isinstance(show, dict) else None,
        "parameters": show.get("parameters") if isinstance(show, dict) else None,
        "selected_model_info": selected_info,
    }


def _version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _command_output(argv: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return (completed.stdout or completed.stderr).strip()[:500] or None


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("memory_load", ctypes.c_ulong),
        ("total_physical", ctypes.c_ulonglong),
        ("available_physical", ctypes.c_ulonglong),
        ("total_page_file", ctypes.c_ulonglong),
        ("available_page_file", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("available_virtual", ctypes.c_ulonglong),
        ("available_extended_virtual", ctypes.c_ulonglong),
    ]


def host_snapshot() -> dict[str, Any]:
    memory = _MemoryStatus()
    memory.length = ctypes.sizeof(_MemoryStatus)
    memory_ok = bool(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)))
    gpu = _command_output(
        (
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        )
    )
    return {
        "captured_utc": datetime.now(UTC).isoformat(),
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_logical_count": os.cpu_count(),
        "memory_total_bytes": memory.total_physical if memory_ok else None,
        "memory_available_bytes": memory.available_physical if memory_ok else None,
        "nvidia_smi": gpu,
    }


async def run(args: argparse.Namespace, work_dir: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_git_sha": _command_output(("git", "rev-parse", "HEAD")),
        "fixed_fixture_policy": {
            "only_compiled_synthetic_or_public_prompts": True,
            "prompt_or_response_content_written": False,
            "prompt_sha256_written": True,
            "fresh_conversation_per_observation": True,
            "unsuccessful_observations_preserved": True,
        },
        "versions": {
            "python": platform.python_version(),
            "jarvis_assistant": _version("jarvis-assistant"),
            "httpx": _version("httpx"),
            "pydantic": _version("pydantic"),
            "ollama": _command_output(("ollama", "--version")),
            "uv": _command_output(("uv", "--version")),
        },
        "model_settings": {
            "local_model": LOCAL_MODEL,
            "hosted_model": HOSTED_MODEL,
            "cloud_cost_limit_usd": 0,
            "adapter_response_mode": "buffered complete responses",
            "token_streaming_claimed": False,
        },
        "host_before": host_snapshot(),
        "local_model_metadata": None,
        "requested_profiles": list(args.profiles),
        "sample_target_per_state": args.samples,
        "profiles": {},
        "blockers": [],
    }
    try:
        report["local_model_metadata"] = await collect_local_model_metadata()
    except Exception as error:
        report["blockers"].append({"scope": "local-model-metadata", "error": type(error).__name__})

    pacer = HostedPacer(args.hosted_min_interval_seconds)
    profile_runners: dict[str, Callable[[], Awaitable[dict[str, Any]]]] = {
        "deterministic": lambda: benchmark_deterministic(args, work_dir),
        "local": lambda: benchmark_local(args, work_dir),
        "hosted-simple": lambda: benchmark_hosted(
            args,
            work_dir,
            "hosted-simple",
            HOSTED_SIMPLE_PROMPTS,
            ReasoningLevel.NONE,
            pacer,
        ),
        "hosted-complex": lambda: benchmark_hosted(
            args,
            work_dir,
            "hosted-complex",
            HOSTED_COMPLEX_PROMPTS,
            ReasoningLevel.DEEP,
            pacer,
        ),
    }
    for profile in args.profiles:
        try:
            result = await profile_runners[profile]()
            report["profiles"][profile] = result
            if result.get("blocked"):
                report["blockers"].append({"scope": profile, "error": str(result["blocker"])})
        except BenchmarkBlocked as error:
            report["profiles"][profile] = {
                "states": [],
                "blocked": True,
                "blocker": str(error),
            }
            report["blockers"].append({"scope": profile, "error": str(error)})
        except Exception as error:
            report["profiles"][profile] = {
                "states": [],
                "blocked": True,
                "blocker": type(error).__name__,
            }
            report["blockers"].append({"scope": profile, "error": type(error).__name__})

    states = [
        state for profile in report["profiles"].values() for state in profile.get("states", [])
    ]
    report["host_after"] = host_snapshot()
    report["required_state_count"] = sum(
        1 if profile == "deterministic" else 2 for profile in args.profiles
    )
    report["completed_state_count"] = len(states)
    report["threshold_pass"] = (
        not report["blockers"]
        and len(states) == report["required_state_count"]
        and all(bool(state["threshold_pass"]) for state in states)
    )
    return report


def _write_report_exclusive(output: Path, report: dict[str, Any]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if len(encoded) > MAX_REPORT_BYTES:
        raise RuntimeError("Phase 1 benchmark report exceeded the 2 MiB evidence cap")
    with output.open("xb") as stream:
        stream.write(encoded)


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Phase 1 benchmark requires the supported Windows target")
    args = parse_args()
    try:
        validate_args(args)
        work_dir, output = resolve_paths(args.work_dir, args.output)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    report = asyncio.run(run(args, work_dir))
    _write_report_exclusive(output, report)
    summary = {
        "output": str(output),
        "requested_profiles": report["requested_profiles"],
        "completed_state_count": report["completed_state_count"],
        "required_state_count": report["required_state_count"],
        "blocker_count": len(report["blockers"]),
        "threshold_pass": report["threshold_pass"],
    }
    print(json.dumps(summary, indent=2))
    if args.enforce and not report["threshold_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
