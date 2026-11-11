"""Inspectable memory, approval, and audit records owned by local persistence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, JsonValue

from jarvis.core.models import CoreModel, Identifier, SensitivityClass, ToolRisk


class MemoryKind(StrEnum):
    NOTE = "note"
    PROFILE = "profile"
    TASK = "task"


class MemoryRecord(CoreModel):
    id: Identifier
    kind: MemoryKind
    content: Annotated[str, Field(min_length=1, max_length=100_000)]
    provenance: Annotated[str, Field(min_length=1, max_length=2_000)]
    sensitivity: SensitivityClass = SensitivityClass.PRIVATE
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime


class AuditOutcome(StrEnum):
    REQUESTED = "requested"
    ALLOWED = "allowed"
    DENIED = "denied"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditRecord(CoreModel):
    id: Identifier
    conversation_id: Identifier | None = None
    action: Annotated[str, Field(min_length=1, max_length=200)]
    outcome: AuditOutcome
    risk: ToolRisk
    detail: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class ApprovalRecord(CoreModel):
    id: Identifier
    conversation_id: Identifier
    action: Annotated[str, Field(min_length=1, max_length=200)]
    status: ApprovalStatus = ApprovalStatus.PENDING
    expires_at: datetime
    created_at: datetime
