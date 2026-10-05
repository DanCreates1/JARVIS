from __future__ import annotations

import asyncio
import base64
import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from jarvis.attachments.models import AttachmentError, AttachmentType
from jarvis.attachments.processing import IsolatedAttachmentProcessor
from jarvis.attachments.vision import OllamaAttachmentVision


def pdf(*, encrypted=False, pages=1, text="synthetic oracle") -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=100, height=100)
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 10 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {
                        NameObject("/F1"): DictionaryObject(
                            {
                                NameObject("/Type"): NameObject("/Font"),
                                NameObject("/Subtype"): NameObject("/Type1"),
                                NameObject("/BaseFont"): NameObject("/Helvetica"),
                            }
                        ),
                    }
                )
            }
        )
    # Active URI is present but must remain inert during text extraction.
    page[NameObject("/Annots")] = ArrayObject(
        [
            writer._add_object(
                DictionaryObject(
                    {
                        NameObject("/Type"): NameObject("/Annot"),
                        NameObject("/Subtype"): NameObject("/Link"),
                        NameObject("/Rect"): ArrayObject([NumberObject(0)] * 4),
                        NameObject("/A"): DictionaryObject(
                            {
                                NameObject("/S"): NameObject("/URI"),
                                NameObject("/URI"): NameObject("/localhost"),
                            }
                        ),
                    }
                )
            )
        ]
    )
    if encrypted:
        writer.encrypt("synthetic-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


async def test_isolated_text_pdf_and_image_processing():
    processor = IsolatedAttachmentProcessor()
    text = await processor.process(
        b"\xef\xbb\xbfuntrusted source\nsecond line", AttachmentType.TEXT
    )
    assert text.text == "untrusted source\nsecond line"
    parsed = await processor.process(pdf(), AttachmentType.PDF)
    assert "synthetic oracle" in parsed.text
    for format_name, media_type in [("PNG", AttachmentType.PNG), ("JPEG", AttachmentType.JPEG)]:
        output = io.BytesIO()
        source = Image.new("RGB", (2200, 10), "red")
        source.save(output, format_name)
        image = await processor.process(output.getvalue(), media_type)
        assert image.width == 2048 and image.height <= 10
        decoded = base64.b64decode(image.image_base64, validate=True)
        with Image.open(io.BytesIO(decoded)) as normalized:
            assert normalized.format == "JPEG" and not normalized.getexif()


@pytest.mark.parametrize(
    "body,media_type",
    [
        (b"binary\x00data", AttachmentType.TEXT),
        (b"\xff\xfe", AttachmentType.TEXT),
        (b"   ", AttachmentType.TEXT),
        (b"x" * 100001, AttachmentType.TEXT),
        (b"not pdf", AttachmentType.PDF),
        (b"%PDF-1.7 broken", AttachmentType.PDF),
        (b"fake PNG", AttachmentType.PNG),
        (b"fake JPEG", AttachmentType.JPEG),
    ],
    ids=["binary", "encoding", "empty", "text-limit", "signature", "broken-pdf", "png", "jpeg"],
)
async def test_parser_rejects_malformed_binary_and_limits(body, media_type):
    with pytest.raises(AttachmentError, match="processing_rejected"):
        await IsolatedAttachmentProcessor().process(body, media_type)


async def test_pdf_password_pages_empty_and_text_limit():
    for body in [pdf(encrypted=True), pdf(pages=51), pdf(text=""), pdf(text="x" * 100001)]:
        with pytest.raises(AttachmentError, match="processing_rejected"):
            await IsolatedAttachmentProcessor().process(body, AttachmentType.PDF)


async def test_image_bomb_animation_and_spoofed_type():
    processor = IsolatedAttachmentProcessor()
    output = io.BytesIO()
    Image.new("RGB", (3000, 3000), "red").save(output, "PNG")
    with pytest.raises(AttachmentError, match="processing_rejected"):
        await processor.process(output.getvalue(), AttachmentType.PNG)
    output = io.BytesIO()
    first = Image.new("RGB", (10, 10), "red")
    first.save(output, "PNG", save_all=True, append_images=[Image.new("RGB", (10, 10), "blue")])
    with pytest.raises(AttachmentError, match="processing_rejected"):
        await processor.process(output.getvalue(), AttachmentType.PNG)
    with pytest.raises(AttachmentError, match="processing_rejected"):
        await processor.process(output.getvalue(), AttachmentType.JPEG)


async def test_worker_timeout_cancel_and_no_credential_inheritance(tmp_path: Path, monkeypatch):
    worker = tmp_path / "worker.py"
    worker.write_text("import time;time.sleep(10)", encoding="utf-8")
    processor = IsolatedAttachmentProcessor(timeout_seconds=0.05)
    processor.worker = worker
    with pytest.raises(AttachmentError, match="processing_timeout"):
        await processor.process(b"text", AttachmentType.TEXT)
    processor.timeout_seconds = 10
    task = asyncio.create_task(processor.process(b"text", AttachmentType.TEXT))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    monkeypatch.setenv("JARVIS_SENTINEL", "synthetic-secret")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    worker.write_text(
        "import os,json;assert 'JARVIS_SENTINEL' not in os.environ;"
        "assert 'PYTHONPATH' not in os.environ;print(json.dumps({'text':'clean'}))",
        encoding="utf-8",
    )
    assert (await processor.process(b"text", AttachmentType.TEXT)).text == "clean"


@pytest.mark.parametrize(
    "code,expected",
    [
        ("print('invalid-json')", "worker_protocol"),
        ("print('{}')", "worker_protocol"),
        ("import sys;sys.stdout.buffer.write(b'x'*2900001)", "worker_output_limit"),
        (
            'import sys;print(\'{"error":"dependency_unavailable"}\');sys.exit(1)',
            "dependency_unavailable",
        ),
    ],
)
async def test_worker_protocol_output_and_missing_dependency(tmp_path, code, expected):
    worker = tmp_path / "worker.py"
    worker.write_text(code, encoding="utf-8")
    processor = IsolatedAttachmentProcessor()
    processor.worker = worker
    with pytest.raises(AttachmentError, match=expected):
        await processor.process(b"text", AttachmentType.TEXT)


async def test_missing_worker_and_upload_size(tmp_path):
    processor = IsolatedAttachmentProcessor()
    processor.worker = tmp_path / "missing.py"
    with pytest.raises(AttachmentError):
        await processor.process(b"text", AttachmentType.TEXT)
    with pytest.raises(AttachmentError, match="upload_size"):
        await processor.process(b"", AttachmentType.TEXT)


@pytest.mark.parametrize(
    "url,model",
    [
        ("https://127.0.0.1", "vision"),
        ("http://example.com", "vision"),
        ("http://localhost", "vision"),
        ("http://127.0.0.1/private", "vision"),
        ("http://user:pass@127.0.0.1", "vision"),
        ("http://127.0.0.1", "model-cloud"),
    ],
)
def test_vision_denies_remote_endpoint_and_cloud_model(url, model):
    with pytest.raises(ValueError):
        OllamaAttachmentVision(base_url=url, model=model)


async def test_vision_capability_local_payload_and_untrusted_response():
    requests = []

    async def handler(request):
        requests.append(request)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["vision"]})
        payload = json.loads(request.content)
        assert "tools" not in payload and payload["stream"] is False
        assert base64.b64decode(payload["messages"][1]["images"][0]) == b"\xff\xd8\xffsynthetic"
        return httpx.Response(
            200, json={"done": True, "message": {"role": "assistant", "content": "red square"}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vision = OllamaAttachmentVision(
            base_url="http://127.0.0.1:11434", model="local-vision", client=client
        )
        assert await vision.describe(b"\xff\xd8\xffsynthetic", "color") == "red square"
        assert len(requests) == 2
        await vision.close()


@pytest.mark.parametrize(
    "profile,answer,expected",
    [
        ({"capabilities": ["text"]}, {}, "vision_capability_unavailable"),
        ({"capabilities": ["vision"], "remote_host": "cloud"}, {}, "vision_capability_unavailable"),
        (
            {"capabilities": ["vision"]},
            {"done": True, "message": {"role": "assistant", "content": "x", "tool_calls": [{}]}},
            "vision_protocol",
        ),
        (
            {"capabilities": ["vision"]},
            {"done": True, "message": {"role": "assistant", "content": "x" * 4001}},
            "vision_protocol",
        ),
    ],
)
async def test_vision_missing_capability_remote_model_and_bad_response(profile, answer, expected):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(200, json=profile if request.url.path == "/api/show" else answer)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vision = OllamaAttachmentVision(
            base_url="http://127.0.0.1", model="local-vision", client=client
        )
        with pytest.raises(AttachmentError, match=expected):
            await vision.describe(b"\xff\xd8\xffsynthetic", "color")
        if expected == "vision_capability_unavailable":
            assert len(requests) == 1  # No image disclosure before capability/local check.
