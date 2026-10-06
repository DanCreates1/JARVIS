"""Provider-neutral private email data; preparation never represents an effect."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, field_validator

from jarvis.core.models import CoreModel

MAX_MESSAGE_BYTES = 128 * 1_024
MAX_THREAD_MESSAGES = 16
EmailID = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
_RESERVED = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
)


class EmailError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value) or value in _RESERVED:
        raise EmailError("invalid_email_id")
    return value


class EmailMessage(CoreModel):
    id: EmailID
    thread_id: EmailID
    sender: Annotated[str, Field(max_length=512)]
    recipients: Annotated[str, Field(max_length=512)]
    subject: Annotated[str, Field(max_length=512)]
    date: Annotated[str, Field(max_length=512)]
    text: Annotated[str, Field(min_length=1, max_length=32_000)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    truncated: bool = False

    _validate_ids = field_validator("id", "thread_id")(validate_id)


class EmailThread(CoreModel):
    id: EmailID
    messages: Annotated[tuple[EmailMessage, ...], Field(min_length=1, max_length=16)]

    _validate_id = field_validator("id")(validate_id)


class EmailEvidence(CoreModel):
    message_id: EmailID
    quote: Annotated[str, Field(min_length=1, max_length=512)]
    kind: Literal["excerpt", "action_candidate", "date_candidate"]


class EmailPreparation(CoreModel):
    thread_id: EmailID
    evidence: Annotated[tuple[EmailEvidence, ...], Field(max_length=64)]
    summary_kind: Literal["extractive"] = "extractive"
    creates_tasks: Literal[False] = False


class EmailDraft(CoreModel):
    thread_id: EmailID
    recipients: Annotated[tuple[str, ...], Field(min_length=1, max_length=10)]
    subject: Annotated[str, Field(min_length=1, max_length=512)]
    body: Annotated[str, Field(min_length=1, max_length=8_000)]
    sent: Literal[False] = False
    stored: Literal[False] = False

    @field_validator("recipients")
    @classmethod
    def exact_mailboxes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(
            not re.fullmatch(
                r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", item
            )
            or len(item) > 254
            for item in value
        ):
            raise ValueError("explicit bare mailboxes required")
        return value

    @field_validator("subject")
    @classmethod
    def safe_subject(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("invalid draft subject")
        return value

    @field_validator("body")
    @classmethod
    def safe_body(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("invalid draft body")
        return value
