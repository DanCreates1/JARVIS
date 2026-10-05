"""Private, untrusted attachment values; none carries execution authority."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator

from jarvis.core.models import CoreModel, Identifier

MAX_UPLOAD_BYTES = 5 * 1_024 * 1_024
MAX_TEXT_CHARS = 100_000
MAX_IMAGE_BYTES = 2 * 1_024 * 1_024
MAX_PROJECTION_CHARS = 8_000
AttachmentId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]


class AttachmentStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AttachmentType(StrEnum):
    TEXT = "text/plain"
    PDF = "application/pdf"
    PNG = "image/png"
    JPEG = "image/jpeg"


class AttachmentError(RuntimeError):
    """Content-free reason safe to expose on local interfaces."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AttachmentUpload(CoreModel):
    conversation_id: Identifier
    filename: Annotated[str, Field(min_length=1, max_length=120)]
    media_type: AttachmentType

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        # Filename is display-only; exclude paths, controls, devices and active-file suffixes.
        if not re.fullmatch(r"[\w .()-]+\.(txt|md|pdf|png|jpg|jpeg)", value, re.IGNORECASE):
            raise ValueError("unsupported attachment filename")
        if value.startswith((".", " ")) or ".." in value or len(value.encode("utf-8")) > 240:
            raise ValueError("invalid attachment filename")
        if value.split(".")[0].upper() in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)),
        }:
            raise ValueError("reserved attachment filename")
        return value


class Attachment(CoreModel):
    id: AttachmentId
    conversation_id: Identifier
    filename: str
    media_type: AttachmentType
    status: AttachmentStatus
    byte_size: Annotated[int, Field(gt=0, le=MAX_UPLOAD_BYTES)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    created_at: datetime
    expires_at: datetime
    chunk_count: Annotated[int, Field(ge=0, le=100)] = 0
    error_code: str | None = None


class ProcessedAttachment(CoreModel):
    text: Annotated[str, Field(max_length=MAX_TEXT_CHARS)] = ""
    image_base64: Annotated[str | None, Field(max_length=2_800_000)] = None
    width: Annotated[int | None, Field(gt=0, le=2_048)] = None
    height: Annotated[int | None, Field(gt=0, le=2_048)] = None
