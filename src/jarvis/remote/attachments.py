"""Bounded, session-owned upload staging. Only explicit chat submission persists sources."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from jarvis.attachments import AttachmentError, AttachmentService, AttachmentUpload
from jarvis.attachments.models import AttachmentStatus
from jarvis.remote.models import RemoteIdentityContext

MAX_STAGE_BYTES = 1_048_576
STAGE_SECONDS = 600


@dataclass(slots=True)
class StagedAttachment:
    upload: AttachmentUpload
    body: bytes


class PWAUploadStaging:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str, str], tuple[float, StagedAttachment | None]] = {}
        self._timer: asyncio.TimerHandle | None = None

    @staticmethod
    def _key(context: RemoteIdentityContext, identifier: str) -> tuple[str, str, str, str]:
        return context.host_id, context.device_id, context.session_id, identifier

    def _expire(self) -> None:
        self._timer = None
        now = time.monotonic()
        self._items = {key: item for key, item in self._items.items() if item[0] > now}
        if self._items:
            self._timer = asyncio.get_running_loop().call_later(30, self._expire)

    def _schedule(self) -> None:
        if self._timer is None:
            self._timer = asyncio.get_running_loop().call_later(30, self._expire)

    def reserve(self, context: RemoteIdentityContext, identifier: str) -> None:
        key = self._key(context, identifier)
        if key in self._items:
            raise AttachmentError("upload_id_used")
        if len(self._items) >= 128 or sum(k[:3] == key[:3] for k in self._items) >= 16:
            raise AttachmentError("upload_capacity")
        # Reservations count before body collection; at most four live MiB per session,
        # 32 per host process. Tombstones consume metadata capacity, never body capacity.
        if sum(item is not None for _, item in self._items.values()) >= 32:
            raise AttachmentError("upload_capacity")
        self._items[key] = (
            time.monotonic() + STAGE_SECONDS,
            StagedAttachment(
                AttachmentUpload(
                    conversation_id="staged", filename="pending.txt", media_type="text/plain"
                ),
                b"",
            ),
        )
        if sum(k[:3] == key[:3] and item is not None for k, (_, item) in self._items.items()) > 4:
            self._items.pop(key)
            raise AttachmentError("upload_capacity")
        self._schedule()

    def finish(
        self, context: RemoteIdentityContext, identifier: str, upload: AttachmentUpload, body: bytes
    ) -> None:
        key = self._key(context, identifier)
        current = self._items.get(key)
        if current is None or current[0] <= time.monotonic() or current[1] is None:
            raise AttachmentError("upload_cancelled")
        if not body or len(body) > MAX_STAGE_BYTES:
            raise AttachmentError("upload_size")
        self._items[key] = current[0], StagedAttachment(upload, body)

    def discard(self, context: RemoteIdentityContext, identifier: str) -> None:
        key = self._key(context, identifier)
        if key not in self._items and len(self._items) >= 128:
            raise AttachmentError("upload_capacity")
        self._items[key] = time.monotonic() + STAGE_SECONDS, None
        self._schedule()

    def take(
        self, context: RemoteIdentityContext, identifiers: tuple[str, ...]
    ) -> tuple[StagedAttachment, ...]:
        keys = [self._key(context, identifier) for identifier in identifiers]
        values = [self._items.get(key) for key in keys]
        if (
            len(keys) > 4
            or len(set(keys)) != len(keys)
            or any(
                item is None or item[0] <= time.monotonic() or item[1] is None or not item[1].body
                for item in values
            )
        ):
            raise AttachmentError("upload_unavailable")
        result = tuple(item[1] for item in values if item is not None and item[1] is not None)
        for identifier in identifiers:
            self.discard(context, identifier)
        return result

    def clear_session(self, session_id: str) -> None:
        self._items = {key: item for key, item in self._items.items() if key[2] != session_id}

    def close(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = None
        self._items.clear()


async def commit_uploads(
    service: AttachmentService | None,
    context: RemoteIdentityContext,
    conversation_id: str,
    staged: tuple[StagedAttachment, ...],
) -> tuple[str, ...]:
    if not staged:
        return ()
    if service is None or not service.enabled:
        raise AttachmentError("attachments_disabled")
    identifiers = []
    for item in staged:
        record = await service.upload(
            item.upload.model_copy(update={"conversation_id": conversation_id}),
            item.body,
            pwa_device_id=context.device_id,
        )
        if record.status is not AttachmentStatus.READY:
            raise AttachmentError("attachment_not_ready")
        identifiers.append(record.id)
    return tuple(identifiers)
