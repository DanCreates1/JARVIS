"""Deadline/cancellation/output bounded short-lived extraction process."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
from contextlib import nullcontext, suppress
from pathlib import Path

from pydantic import ValidationError

from .models import (
    MAX_IMAGE_BYTES,
    MAX_UPLOAD_BYTES,
    AttachmentError,
    AttachmentType,
    ProcessedAttachment,
)

_BOOTSTRAP = (
    "import json,runpy,sys;sys.path[:0]=json.loads(sys.argv[1]);"
    "runpy.run_path(sys.argv[2],run_name='__main__')"
)


class IsolatedAttachmentProcessor:
    def __init__(self, *, timeout_seconds: float = 10) -> None:
        if not 0 < timeout_seconds <= 30:
            raise ValueError("invalid parser deadline")
        self.timeout_seconds = timeout_seconds
        self.worker = Path(__file__).with_name("_worker.py").resolve(strict=True)
        self.roots = [
            str(Path(p).resolve()) for p in sys.path if p and Path(p).name == "site-packages"
        ]

    async def process(self, body: bytes, media_type: AttachmentType) -> ProcessedAttachment:
        if not body or len(body) > MAX_UPLOAD_BYTES:
            raise AttachmentError("upload_size")
        # Only installed dependency roots, never checkout/current-directory/PYTHONPATH imports.
        environment = {
            key: value
            for key in ("SystemRoot", "WINDIR")
            if (value := os.environ.get(key)) is not None
        }
        request = json.dumps(
            {
                "body_base64": base64.b64encode(body).decode("ascii"),
                "media_type": media_type.value,
            }
        ).encode("ascii")
        process: asyncio.subprocess.Process | None = None
        working = tempfile.TemporaryDirectory(prefix="jarvis-attachment-")
        try:
            # Cleanup owned below, after child reap; Windows locks a child's current directory.
            with nullcontext(working.name) as cwd:
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-I",
                    "-X",
                    "utf8",
                    "-c",
                    _BOOTSTRAP,
                    json.dumps(self.roots),
                    str(self.worker),
                    cwd=cwd,
                    env=environment,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                assert process.stdin is not None and process.stdout is not None
                async with asyncio.timeout(self.timeout_seconds):
                    # Reader runs during write so neither pipe can deadlock on large input/output.
                    async def read_output() -> bytes:
                        assert process is not None and process.stdout is not None
                        output = bytearray()
                        while piece := await process.stdout.read(65_536):
                            output.extend(piece)
                            if len(output) > 2_900_000:
                                raise AttachmentError("worker_output_limit")
                        return bytes(output)

                    reader = asyncio.create_task(read_output())
                    try:
                        process.stdin.write(request)
                        with suppress(BrokenPipeError, ConnectionResetError):
                            await process.stdin.drain()
                        process.stdin.close()
                        raw = await reader
                        await process.wait()
                    finally:
                        reader.cancel()
                        with suppress(asyncio.CancelledError):
                            await reader
                payload = json.loads(raw)
                if process.returncode != 0:
                    code = payload.get("error") if isinstance(payload, dict) else None
                    raise AttachmentError(
                        "dependency_unavailable"
                        if code == "dependency_unavailable"
                        else "processing_rejected"
                    )
                result = ProcessedAttachment.model_validate(payload)
                if media_type in {AttachmentType.PNG, AttachmentType.JPEG}:
                    if (
                        result.text
                        or not result.image_base64
                        or not result.width
                        or not result.height
                    ):
                        raise AttachmentError("worker_protocol")
                    image = base64.b64decode(result.image_base64, validate=True)
                    if len(image) > MAX_IMAGE_BYTES or not image.startswith(b"\xff\xd8\xff"):
                        raise AttachmentError("worker_protocol")
                elif not result.text.strip() or result.image_base64 is not None:
                    raise AttachmentError("worker_protocol")
                return result
        except TimeoutError:
            raise AttachmentError("processing_timeout") from None
        except (OSError, BrokenPipeError):
            raise AttachmentError("processor_unavailable") from None
        except (ValueError, ValidationError):
            raise AttachmentError("worker_protocol") from None
        finally:
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
            working.cleanup()
