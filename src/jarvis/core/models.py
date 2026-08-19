"""Validated domain models shared by the JARVIS core and its adapters."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
ToolName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$",
    ),
]


class CoreModel(BaseModel):
    """Strict, immutable base model for values crossing core boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Conversation(CoreModel):
    id: Identifier
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ToolCall(CoreModel):
    """A provider-requested tool call; always validate it before execution."""

    id: Identifier
    name: ToolName
    arguments: dict[str, JsonValue] = Field(default_factory=dict, max_length=100)


class Message(CoreModel):
    """Provider-neutral message representation persisted by the core."""

    id: Identifier | None = None
    conversation_id: Identifier
    role: MessageRole
    content: Annotated[str, Field(max_length=100_000)] = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: Identifier | None = None
    tool_name: ToolName | None = None

    @model_validator(mode="after")
    def validate_role_shape(self) -> Self:
        has_content = bool(self.content.strip())
        if self.role in {MessageRole.SYSTEM, MessageRole.USER}:
            if not has_content:
                raise ValueError(f"{self.role.value} messages require non-empty content")
            if self.tool_calls or self.tool_call_id or self.tool_name:
                raise ValueError(f"{self.role.value} messages cannot contain tool fields")
        elif self.role is MessageRole.ASSISTANT:
            if not has_content and not self.tool_calls:
                raise ValueError("assistant messages require content or tool calls")
            if self.tool_call_id or self.tool_name:
                raise ValueError("assistant messages cannot reference a tool result")
        elif self.role is MessageRole.TOOL:
            if not has_content:
                raise ValueError("tool messages require non-empty content")
            if not self.tool_call_id or not self.tool_name:
                raise ValueError("tool messages require tool_call_id and tool_name")
            if self.tool_calls:
                raise ValueError("tool messages cannot request more tools")
        return self


class ToolDefinition(CoreModel):
    name: ToolName
    description: Annotated[str, Field(min_length=1, max_length=2_000)]
    input_schema: dict[str, JsonValue]


class ProviderResponse(CoreModel):
    """Normalized provider output; the service revalidates every response."""

    content: Annotated[str, Field(max_length=100_000)] | None = None
    tool_calls: Annotated[tuple[ToolCall, ...], Field(max_length=64)] = ()

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if not (self.content and self.content.strip()) and not self.tool_calls:
            raise ValueError("provider response requires content or at least one tool call")
        call_ids = [call.id for call in self.tool_calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("provider response contains duplicate tool call ids")
        return self


class ToolResult(CoreModel):
    content: Annotated[str, Field(min_length=1, max_length=100_000)]
    is_error: bool = False
    data: JsonValue | None = None

    @field_validator("content")
    @classmethod
    def require_nonblank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tool result content cannot be blank")
        return value


class PolicyDecision(CoreModel):
    allowed: bool
    reason: Annotated[str, Field(max_length=4_000)] | None = None

    @model_validator(mode="after")
    def require_denial_reason(self) -> Self:
        if not self.allowed and not (self.reason and self.reason.strip()):
            raise ValueError("denied policy decisions require a reason")
        return self


class AssistantRequest(CoreModel):
    user_input: Annotated[str, Field(min_length=1, max_length=100_000)]
    conversation_id: Identifier | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("user_input")
    @classmethod
    def normalize_user_input(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("user_input cannot be blank")
        return normalized


class RuntimeStatus(StrEnum):
    COMPLETED = "completed"
    DENIED = "denied"
    FAILED = "failed"
    LIMIT_REACHED = "limit_reached"


class RuntimeErrorCode(StrEnum):
    CONVERSATION_NOT_FOUND = "conversation_not_found"
    STORE_ERROR = "store_error"
    PROVIDER_ERROR = "provider_error"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_TOOL_ARGUMENTS = "invalid_tool_arguments"
    POLICY_ERROR = "policy_error"
    TOOL_DENIED = "tool_denied"
    TOOL_ERROR = "tool_error"
    TOOL_ITERATION_LIMIT = "tool_iteration_limit"


class RuntimeErrorDetail(CoreModel):
    code: RuntimeErrorCode
    message: Annotated[str, Field(min_length=1, max_length=4_000)]
    tool_call_id: Identifier | None = None
    tool_name: ToolName | None = None


class RuntimeEventType(StrEnum):
    CONVERSATION_CREATED = "conversation_created"
    CONVERSATION_RESUMED = "conversation_resumed"
    MESSAGE_PERSISTED = "message_persisted"
    PROVIDER_REQUESTED = "provider_requested"
    PROVIDER_RESPONDED = "provider_responded"
    TOOL_REQUESTED = "tool_requested"
    TOOL_VALIDATED = "tool_validated"
    TOOL_AUTHORIZED = "tool_authorized"
    TOOL_DENIED = "tool_denied"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    RUNTIME_COMPLETED = "runtime_completed"
    RUNTIME_FAILED = "runtime_failed"


class RuntimeEvent(CoreModel):
    sequence: Annotated[int, Field(ge=1)]
    type: RuntimeEventType
    conversation_id: Identifier | None = None
    detail: str | None = None
    message: Message | None = None
    tool_call: ToolCall | None = None


class RuntimeResult(CoreModel):
    conversation_id: Identifier | None = None
    status: RuntimeStatus
    reply: str | None = None
    messages: tuple[Message, ...] = ()
    events: tuple[RuntimeEvent, ...] = ()
    error: RuntimeErrorDetail | None = None
    tool_iterations: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.status is RuntimeStatus.COMPLETED:
            if not (self.reply and self.reply.strip()):
                raise ValueError("completed results require a reply")
            if self.error is not None:
                raise ValueError("completed results cannot contain an error")
        elif self.error is None:
            raise ValueError("non-completed results require an error")
        return self
