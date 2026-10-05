"""Fixed local attachment retrieval/parser gate and optional installed vision smoke."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from jarvis.attachments import AttachmentService, AttachmentType, AttachmentUpload  # noqa: E402
from jarvis.attachments.processing import IsolatedAttachmentProcessor  # noqa: E402
from jarvis.attachments.vision import OllamaAttachmentVision  # noqa: E402
from jarvis.core.models import SensitivityClass  # noqa: E402
from jarvis.memory import SQLiteConversationStore  # noqa: E402


def metrics(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 3),
    }


async def benchmark(directory: Path, vision_model: str | None) -> dict[str, object]:
    db = directory / "synthetic.db"
    store = SQLiteConversationStore(db)
    await store.initialize()
    conversation = await store.create_conversation()
    vision = (
        OllamaAttachmentVision(base_url="http://127.0.0.1:11434", model=vision_model)
        if vision_model
        else None
    )
    service = AttachmentService(db, host_id="synthetic-benchmark", enabled=True, vision=vision)
    failures: list[str] = []
    try:
        body = "".join(f"marker{i:03} value{i:03} ".ljust(1000, "x") for i in range(100)).encode()
        record = await service.upload(
            AttachmentUpload(
                conversation_id=conversation.id,
                filename="synthetic.txt",
                media_type=AttachmentType.TEXT,
            ),
            body,
        )
        assert record.status.value == "ready"
        retrieval_ms: list[float] = []
        max_chars = 0
        for index in range(100):
            started = time.perf_counter()
            projection = await service.project(conversation.id, (record.id,), f"marker{index:03}")
            retrieval_ms.append((time.perf_counter() - started) * 1000)
            max_chars = max(max_chars, len(projection.content))
            if f"marker{index:03} value{index:03}" not in projection.content:
                failures.append(f"oracle:{index}")
            if projection.sensitivity is not SensitivityClass.PRIVATE or max_chars > 8000:
                failures.append(f"boundary:{index}")
        processor = IsolatedAttachmentProcessor()
        parse_ms: list[float] = []
        for _ in range(20):
            started = time.perf_counter()
            parsed = await processor.process(b"synthetic parser oracle", AttachmentType.TEXT)
            parse_ms.append((time.perf_counter() - started) * 1000)
            if parsed.text != "synthetic parser oracle":
                failures.append("parser-oracle")
        await service.close()
        await service.initialize()
        assert await service.get(conversation.id, record.id)
        await service.delete(conversation.id, record.id)
        assert not await service.list(conversation.id)
        vision_status = "not_requested"
        vision_ms: float | None = None
        if vision is not None:
            output = io.BytesIO()
            Image.new("RGB", (128, 128), "red").save(output, "PNG")
            image = await service.upload(
                AttachmentUpload(
                    conversation_id=conversation.id,
                    filename="synthetic.png",
                    media_type=AttachmentType.PNG,
                ),
                output.getvalue(),
            )
            started = time.perf_counter()
            projected = await service.project(
                conversation.id, (image.id,), "What color fills this image? Answer briefly."
            )
            vision_ms = round((time.perf_counter() - started) * 1000, 3)
            vision_status = (
                "pass"
                if "red" in projected.content.casefold()
                and "vision_unavailable" not in projected.content
                else "fail"
            )
            if vision_status != "pass":
                failures.append("live-vision-oracle")
            await service.delete(conversation.id, image.id)
        retrieval = metrics(retrieval_ms)
        parsing = metrics(parse_ms)
        if retrieval["p95_ms"] > 100 or parsing["p95_ms"] > 2000:
            failures.append("latency")
        return {
            "retrieval_samples": 100,
            "isolated_parser_samples": 20,
            "retrieval": retrieval,
            "parser": parsing,
            "max_projection_chars": max_chars,
            "failures": failures,
            "restart_delete_smoke": "pass",
            "vision_status": vision_status,
            "vision_model": vision_model,
            "vision_ms": vision_ms,
            "cloud_calls": 0,
            "research_calls": 0,
            "tool_effects": 0,
            "cost_usd": 0,
        }
    finally:
        await service.close()
        await store.close()
        if vision is not None:
            await vision.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument(
        "--vision-model", help="Explicit already-installed local model; no download."
    )
    args = parser.parse_args()
    runtime = REPOSITORY / "runtime"
    runtime.mkdir(exist_ok=True)
    if not runtime.resolve().is_relative_to(REPOSITORY):
        raise ValueError("benchmark runtime outside workspace")
    with tempfile.TemporaryDirectory(prefix="phase-g-", dir=runtime) as directory:
        path = Path(directory).resolve()
        if not path.is_relative_to(runtime.resolve()):
            raise ValueError("benchmark cleanup outside runtime")
        result = asyncio.run(benchmark(path, args.vision_model))
    print(json.dumps(result, indent=2))
    return 1 if args.enforce and result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
