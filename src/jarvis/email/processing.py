"""Bounded short-lived email parser; minimal environment, deadline and child reap."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from .models import MAX_MESSAGE_BYTES, EmailError, EmailMessage


class IsolatedEmailParser:
    def __init__(self, *, timeout_seconds: float = 5) -> None:
        if not 0 < timeout_seconds <= 5:
            raise ValueError("invalid email parser deadline")
        self.timeout_seconds = timeout_seconds
        self.worker = Path(__file__).with_name("_worker.py").resolve(strict=True)

    async def parse(self, raw: bytes, *, thread_id: str, message_id: str) -> EmailMessage:
        if not raw or len(raw) > MAX_MESSAGE_BYTES:
            raise EmailError("message_size")
        process: asyncio.subprocess.Process | None = None
        environment = {
            key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ
        }
        working = tempfile.TemporaryDirectory(prefix="jarvis-email-")
        try:
            async with asyncio.timeout(self.timeout_seconds):
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-I",
                    "-X",
                    "utf8",
                    str(self.worker),
                    cwd=working.name,
                    env=environment,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                assert process.stdin is not None and process.stdout is not None
                process.stdin.write(
                    json.dumps({"body": base64.b64encode(raw).decode("ascii")}).encode()
                )
                with suppress(BrokenPipeError, ConnectionResetError):
                    await process.stdin.drain()
                process.stdin.close()
                output = bytearray()
                while chunk := await process.stdout.read(16_384):
                    output.extend(chunk)
                    if len(output) > 210_000:
                        raise EmailError("parser_output_limit")
                await process.wait()
            if process.returncode != 0:
                raise EmailError("message_rejected")
            return EmailMessage.model_validate(
                {**json.loads(output), "thread_id": thread_id, "id": message_id}
            )
        except TimeoutError:
            raise EmailError("parser_timeout") from None
        except OSError:
            raise EmailError("parser_unavailable") from None
        except (ValueError, TypeError) as exc:
            if isinstance(exc, EmailError):
                raise
            raise EmailError("parser_protocol") from None
        finally:
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
            working.cleanup()
