"""Inspectable memory, approval, and audit records owned by local persistence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, StringConstraints, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier, SensitivityClass, ToolRisk


class MemoryKind(StrEnum):
    """Legacy Phase 1 memory kinds retained for database/API compatibility."""

    NOTE = "note"
    PROFILE = "profile"
    TASK = "task"


class MemoryRecord(CoreModel):
    """Legacy Phase 1 memory record retained for migration compatibility."""

    id: Identifier
    kind: MemoryKind
    content: Annotated[str, Field(min_length=1, max_length=100_000)]
    provenance: Annotated[str, Field(min_length=1, max_length=2_000)]
    sensitivity: SensitivityClass = SensitivityClass.PRIVATE
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime


MemoryKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
ContentDigest = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]


class MemoryCategory(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    PROFILE = "profile"
    SEMANTIC = "semantic"
    TASK = "task"


class MemoryState(StrEnum):
    CANDIDATE = "candidate"
    COMMITTED = "committed"
    CORRECTED = "corrected"
    EXPIRED = "expired"
    REJECTED = "rejected"
    DELETED = "deleted"


class ProvenanceSource(StrEnum):
    CONVERSATION = "conversation"
    MESSAGE = "message"
    TOOL = "tool"
    IMPORT = "import"
    EXPLICIT = "explicit"
    DERIVED = "derived"


class ProvenanceTrust(StrEnum):
    TRUSTED_HOST = "trusted_host"
    LOCAL_SYSTEM = "local_system"
    UNTRUSTED_CONTENT = "untrusted_content"


class RetentionClass(StrEnum):
    VOLATILE = "volatile"
    SHORT = "short"
    STANDARD = "standard"
    LONG = "long"
    INDEFINITE = "indefinite"


class ConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class MemoryEventType(StrEnum):
    CANDIDATE_CREATED = "candidate_created"
    EXPLICITLY_COMMITTED = "explicitly_committed"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    CORRECTED = "corrected"
    EXPIRED = "expired"
    CONFLICT_OPENED = "conflict_opened"
    CONFLICT_RESOLVED = "conflict_resolved"
    DEDUPLICATED = "deduplicated"
    EXPORTED = "exported"
    DELETED = "deleted"


class ConfirmationInterface(StrEnum):
    LOCAL_CLI = "local_cli"
    LOCAL_WEB = "local_web"
    TRUSTED_API = "trusted_api"
    TEST = "test"


class MemoryProvenance(CoreModel):
    id: Identifier
    source_type: ProvenanceSource
    source_id: Annotated[str, Field(min_length=1, max_length=500)]
    source_label: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None
    conversation_id: Identifier | None = None
    message_id: Identifier | None = None
    tool_call_id: Identifier | None = None
    import_uri: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None
    source_content_sha256: ContentDigest | None = None
    trust: ProvenanceTrust
    created_at: datetime

    @model_validator(mode="after")
    def require_source_reference(self) -> Self:
        required = {
            ProvenanceSource.CONVERSATION: self.conversation_id,
            ProvenanceSource.MESSAGE: self.message_id,
            ProvenanceSource.TOOL: self.tool_call_id,
            ProvenanceSource.IMPORT: self.import_uri,
        }.get(self.source_type)
        if (
            self.source_type
            in {
                ProvenanceSource.CONVERSATION,
                ProvenanceSource.MESSAGE,
                ProvenanceSource.TOOL,
                ProvenanceSource.IMPORT,
            }
            and required is None
        ):
            raise ValueError(f"{self.source_type.value} provenance requires its typed reference")
        if (
            self.source_type in {ProvenanceSource.CONVERSATION, ProvenanceSource.MESSAGE}
            and self.trust is not ProvenanceTrust.UNTRUSTED_CONTENT
        ):
            raise ValueError("conversation/message extraction remains untrusted until confirmed")
        if (
            self.source_type is ProvenanceSource.IMPORT
            and self.trust is not ProvenanceTrust.UNTRUSTED_CONTENT
        ):
            raise ValueError("import provenance must be untrusted content")
        return self


class MemoryItem(CoreModel):
    id: Identifier
    host_id: Identifier
    category: MemoryCategory
    state: MemoryState
    key: MemoryKey | None = None
    content: Annotated[str, Field(min_length=1, max_length=100_000)]
    content_sha256: ContentDigest
    structured: dict[str, JsonValue] = Field(default_factory=dict)
    sensitivity: SensitivityClass = SensitivityClass.PRIVATE
    confidence: Annotated[float, Field(ge=0, le=1)]
    retention_class: RetentionClass
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    accessed_at: datetime | None = None
    version: Annotated[int, Field(ge=1)]
    supersedes_id: Identifier | None = None
    conflict_group_id: Identifier | None = None
    is_derived: bool = False
    provenance: tuple[MemoryProvenance, ...] = Field(min_length=1, max_length=100)
    derived_from: tuple[Identifier, ...] = Field(default=(), max_length=100)
    conflict_ids: tuple[Identifier, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.state is MemoryState.DELETED:
            raise ValueError("deleted memory content must not remain in a MemoryItem")
        if self.category is MemoryCategory.WORKING and self.expires_at is None:
            raise ValueError("working memory requires an expiry")
        if (
            self.state is MemoryState.CANDIDATE
            and self.provenance[0].source_type is ProvenanceSource.DERIVED
        ):
            raise ValueError("derived output cannot masquerade as an extraction candidate")
        return self


class MemoryConfirmation(CoreModel):
    host_id: Identifier
    interface: ConfirmationInterface
    candidate_id: Identifier
    expected_version: Annotated[int, Field(ge=1)]
    expected_content_sha256: ContentDigest
    confirmed_at: datetime

    @field_validator("confirmed_at")
    @classmethod
    def require_aware_confirmation_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("confirmation timestamp must be timezone-aware")
        return value


class MemoryConflict(CoreModel):
    id: Identifier
    host_id: Identifier
    left_memory_id: Identifier
    right_memory_id: Identifier
    status: ConflictStatus
    winner_memory_id: Identifier | None = None
    reason_code: Annotated[str, Field(min_length=1, max_length=100)]
    created_at: datetime
    resolved_at: datetime | None = None


class MemoryQuery(CoreModel):
    host_id: Identifier
    text: Annotated[str, Field(min_length=1, max_length=10_000)]
    categories: Annotated[tuple[MemoryCategory, ...], Field(max_length=5)] = ()
    limit: Annotated[int, Field(ge=1, le=50)] = 8
    min_score: Annotated[float, Field(ge=0, le=1)] = 0.25
    include_conflicts: bool = True
    now: datetime | None = None


class MemoryHit(CoreModel):
    item: MemoryItem
    score: Annotated[float, Field(ge=0, le=1)]
    lexical_score: Annotated[float, Field(ge=0, le=1)]
    recency_score: Annotated[float, Field(ge=0, le=1)]
    confidence_score: Annotated[float, Field(ge=0, le=1)]
    trust_score: Annotated[float, Field(ge=0, le=1)]
    matched_terms: tuple[str, ...]
    reason: Annotated[str, Field(min_length=1, max_length=2_000)]
    conflict_ids: tuple[Identifier, ...] = ()


class MemoryPromptProjection(CoreModel):
    host_id: Identifier
    query: Annotated[str, Field(min_length=1, max_length=10_000)]
    content: Annotated[str, Field(max_length=20_000)]
    memory_ids: Annotated[tuple[Identifier, ...], Field(max_length=20)]
    sensitivity: SensitivityClass
    created_at: datetime


class MemoryDeletionReceipt(CoreModel):
    host_id: Identifier
    requested_memory_id: Identifier
    deleted_memory_ids: Annotated[tuple[Identifier, ...], Field(max_length=10_000)]
    canonical_rows: Annotated[int, Field(ge=0)]
    provenance_rows: Annotated[int, Field(ge=0)]
    derivation_rows: Annotated[int, Field(ge=0)]
    conflict_rows: Annotated[int, Field(ge=0)]
    fts_rows: Annotated[int, Field(ge=0)]
    tombstones_written: Annotated[int, Field(ge=0)]
    deleted_at: datetime
    reason_code: Annotated[str, Field(min_length=1, max_length=100)]


class MemoryExportReceipt(CoreModel):
    host_id: Identifier
    path: Annotated[str, Field(min_length=1, max_length=4_000)]
    record_count: Annotated[int, Field(ge=0)]
    byte_count: Annotated[int, Field(ge=0)]
    exported_at: datetime


class MemoryRetentionRule(CoreModel):
    host_id: Identifier
    category: MemoryCategory
    retention_days: Annotated[int, Field(ge=1, le=36_500)] | None
    updated_at: datetime


class MemoryRetentionResult(CoreModel):
    host_id: Identifier
    expired_memory_ids: tuple[Identifier, ...]
    evaluated_at: datetime


class MemoryExtraction(CoreModel):
    category: MemoryCategory
    key: MemoryKey | None = None
    content: Annotated[str, Field(min_length=1, max_length=100_000)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    sensitivity: SensitivityClass = SensitivityClass.PRIVATE
    structured: dict[str, JsonValue] = Field(default_factory=dict)
    reason_code: Literal[
        "explicit_preference",
        "explicit_profile_fact",
        "explicit_task",
        "explicit_episode",
        "explicit_semantic_note",
    ]


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
