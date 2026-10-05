"""Provider-neutral extraction, retrieval and image interpretation ports."""

from typing import Protocol

from .models import AttachmentType, ProcessedAttachment


class AttachmentProcessor(Protocol):
    async def process(self, body: bytes, media_type: AttachmentType) -> ProcessedAttachment: ...


class AttachmentVision(Protocol):
    async def describe(self, image: bytes, query: str) -> str:
        """Interpret normalized image locally, with no tools or fallback disclosure."""
        ...
