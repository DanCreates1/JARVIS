"""Opt-in PROTO-1.2 local smoke. No browser enrollment or AC-09/10 claim."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from jarvis.bootstrap import build_runtime
from jarvis.config import Settings
from jarvis.core import AssistantRequest, ModelRole, RuntimeEventType, RuntimeStatus

ROOT = Path(__file__).resolve().parents[1]


async def smoke(directory: Path) -> dict[str, object]:
    settings = Settings(
        _env_file=None,
        data_dir=directory / "core",
        runtime_profile="prototype-text",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3:0.6b",
        trusted_browser_origins=(),
    )
    async with httpx.AsyncClient(trust_env=False) as client:
        tags = (await client.get("http://127.0.0.1:11434/api/tags", timeout=5)).json()
        version = (await client.get("http://127.0.0.1:11434/api/version", timeout=5)).json()
    model = next(item for item in tags["models"] if item["name"] == settings.ollama_model)
    rows: list[dict[str, object]] = []
    async with await build_runtime(settings) as runtime:
        assert set(runtime.provider.providers) == {ModelRole.LOCAL}
        assert runtime.research is None and runtime.attachments is None
        assert runtime.service.automatic_research is None
        conversation = None
        for identifier, prompt in (
            ("clock", "What is the time?"),
            (
                "C1",
                "Turn these synthetic requirements into exactly three checklist items, preserving "
                "every number: charge two lamps; pack three maps; label one blue box. "
                "Use under 60 words.",
            ),
            (
                "F1",
                "From that checklist, which item mentions a colour? Answer with that item only, "
                "under 20 words.",
            ),
        ):
            started = time.perf_counter()
            before = datetime.now(UTC)
            first_delta = None
            deltas = 0
            result = None
            async for frame in runtime.service.stream(
                AssistantRequest(
                    user_input=prompt,
                    conversation_id=conversation,
                    metadata={"interface": "cli"},
                )
            ):
                if frame.event and frame.event.type is RuntimeEventType.ASSISTANT_DELTA:
                    deltas += 1
                    if first_delta is None:
                        first_delta = time.perf_counter() - started
                if frame.result:
                    result = frame.result
            after = datetime.now(UTC)
            assert result is not None and result.status is RuntimeStatus.COMPLETED
            reply = result.reply or ""
            if identifier == "clock":
                match = re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", reply)
                assert match is not None
                observed = datetime.fromisoformat(match.group())
                assert before.timestamp() - 1 <= observed.timestamp() <= after.timestamp()
                assert all(event.usage is None for event in result.events)
            else:
                assert deltas > 0 and "blue" in reply.casefold() and "box" in reply.casefold()
                conversation = result.conversation_id
            rows.append(
                {
                    "case": identifier,
                    "status": result.status.value,
                    "deltas": deltas,
                    "first_delta_seconds": first_delta,
                    "completion_seconds": round(time.perf_counter() - started, 3),
                    "words": len(reply.split()),
                }
            )
        assert conversation is not None
        messages = await runtime.store.recent_messages(conversation, limit=40)
        assert len(messages) == 4
    # Exercise the documented launcher/module entry with a separate synthetic CLI store.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("JARVIS_") and key.upper() != "NVIDIA_API_KEY"
    }
    environment["JARVIS_DATA_DIR"] = str(directory / "cli")
    cli = await asyncio.to_thread(
        subprocess.run,
        [
            "cmd",
            "/c",
            "scripts\\open-local.cmd",
            "chat",
            "--message",
            "Explain a solar eclipse in two sentences, under 60 words.",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    (directory / "cli-output.txt").write_text(cli.stdout + cli.stderr, encoding="utf-8")
    assert cli.returncode == 0 and "moon" in cli.stdout.casefold()
    return {
        "model": model["name"],
        "digest": model["digest"],
        "ollama_version": version["version"],
        "profile": settings.runtime_profile,
        "samples": rows,
        "cli_exit": cli.returncode,
        "persisted_context_messages": len(messages),
        "limit": "Smoke only; no full corpus, warm percentile or integrated browser acceptance.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow synthetic local inference.")
    arguments = parser.parse_args()
    if not arguments.live:
        parser.error("--live required; runs installed local model using disposable synthetic state")
    base = ROOT / "runtime" / "proto12"
    base.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="text-smoke-", dir=base))
    report = asyncio.run(smoke(directory))
    (directory / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
