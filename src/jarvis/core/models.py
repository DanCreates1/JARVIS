"""Validated domain models shared by the JARVIS core and its adapters."""

from __future__ import annotations

from enum import IntEnum, StrEnum
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
ToolVersion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[1-9][0-9]*(?:\.[0-9]+){0,2}$",
    ),
]
CapabilityName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]


def count_json_leaf_items(value: JsonValue | None, *, stop_after: int | None = None) -> int:
    """Count recursive scalar leaves; containers/keys and null consume no item quota."""
    if stop_after is not None and stop_after < 0:
        raise ValueError("stop_after must be non-negative")
    if value is None:
        return 0
    if isinstance(value, dict):
        count = 0
        for nested in value.values():
            count += count_json_leaf_items(nested, stop_after=stop_after)
            if stop_after is not None and count > stop_after:
                return count
        return count
    if isinstance(value, list):
        count = 0
        for nested in value:
            count += count_json_leaf_items(nested, stop_after=stop_after)
            if stop_after is not None and count > stop_after:
                return count
        return count
    return 1


class CoreModel(BaseModel):
    """Strict, immutable base model for values crossing core boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ModelRole(StrEnum):
    FAST = "fast"
    PRIMARY = "primary"
    REASONING = "reasoning"
    LOCAL = "local"


class ModelLifecycle(StrEnum):
    PRODUCTION = "production"
    STABLE = "stable"
    PREVIEW = "preview"
    LOCAL = "local"


class ModelCapability(StrEnum):
    TEXT = "text"
    VISION = "vision"
    MULTIMODAL = "multimodal"
    TOOLS = "tools"
    PARALLEL_TOOLS = "parallel_tools"
    STRUCTURED_OUTPUT = "structured_output"
    REASONING = "reasoning"


class LatencyClass(StrEnum):
    """User-experience latency envelope; not a provider authorization."""

    SIMPLE_LOCAL = "simple_local"
    NORMAL_VOICE = "normal_voice"
    FAST_CLOUD = "fast_cloud"
    DEEP_REASONING = "deep_reasoning"


class SensitivityClass(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    UNKNOWN = "unknown"


class ReasoningLevel(StrEnum):
    NONE = "none"
    MODERATE = "moderate"
    DEEP = "deep"


class ToolRisk(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    SENSITIVE = "sensitive"
    DESTRUCTIVE = "destructive"


class PermissionLevel(IntEnum):
    """Deterministic host-action risk levels; model confidence never changes these values."""

    LEVEL_0 = 0
    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3
    LEVEL_4 = 4


class ApprovalRule(StrEnum):
    """Trusted approval behavior required by a tool definition."""

    NONE = "none"
    EXPLICIT_ENABLEMENT = "explicit_enablement"
    POLICY_OR_EXPLICIT = "policy_or_explicit"
    EXACT_RECENT_AUTH = "exact_recent_auth"
    STEP_UP = "step_up"
    DISABLED = "disabled"


class ToolSideEffect(StrEnum):
    NONE = "none"
    REVERSIBLE = "reversible"
    EXTERNAL = "external"
    IRREVERSIBLE = "irreversible"
    ADMINISTRATIVE = "administrative"


class ToolIdempotency(StrEnum):
    SIDE_EFFECT_FREE = "side_effect_free"
    IDEMPOTENT = "idempotent"
    IDEMPOTENCY_KEY = "idempotency_key"
    NON_IDEMPOTENT = "non_idempotent"


class ToolRetryPolicy(StrEnum):
    NEVER = "never"
    TRANSIENT_ONLY = "transient_only"
    RECONCILE_FIRST = "reconcile_first"


class ToolConcurrency(StrEnum):
    PARALLEL = "parallel"
    SERIAL_PER_SESSION = "serial_per_session"
    SERIAL_GLOBAL = "serial_global"


class ModelProfile(CoreModel):
    role: ModelRole
    provider: Identifier
    model_id: Identifier
    capabilities: tuple[ModelCapability, ...] = ()
    lifecycle: ModelLifecycle
    context_window: Annotated[int, Field(gt=0)]
    max_output_tokens: Annotated[int, Field(gt=0)] | None = None
    is_cloud: bool


class ProviderLatencyBreakdown(CoreModel):
    """Provider request milestones measured in milliseconds from request start.

    TCP/TLS markers are absent when a pooled keep-alive connection is reused. DNS is a bounded
    local resolver probe performed immediately before the HTTP request; it stays distinct from the
    transport's combined connect timing.
    """

    request_start_ms: Annotated[float, Field(ge=0)] = 0
    dns_ms: Annotated[float, Field(ge=0)] | None = None
    tcp_connect_ms: Annotated[float, Field(ge=0)] | None = None
    tls_ms: Annotated[float, Field(ge=0)] | None = None
    request_upload_ms: Annotated[float, Field(ge=0)] | None = None
    response_headers_ms: Annotated[float, Field(ge=0)] | None = None
    first_sse_frame_ms: Annotated[float, Field(ge=0)] | None = None
    first_reasoning_token_ms: Annotated[float, Field(ge=0)] | None = None
    first_visible_token_ms: Annotated[float, Field(ge=0)] | None = None
    final_visible_token_ms: Annotated[float, Field(ge=0)] | None = None
    completion_ms: Annotated[float, Field(ge=0)] | None = None


class ProviderUsage(CoreModel):
    provider: Identifier
    model_id: Identifier
    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    latency_ms: Annotated[float, Field(ge=0)] = 0
    estimated_cost_usd: Annotated[float, Field(ge=0)] = 0
    rate_limit_remaining: Annotated[int, Field(ge=0)] | None = None
    message_count: Annotated[int, Field(ge=0)] | None = None
    tool_schema_count: Annotated[int, Field(ge=0)] | None = None
    reasoning_budget_tokens: Annotated[int, Field(ge=0)] | None = None
    latency: ProviderLatencyBreakdown | None = None


class RoutingDecision(CoreModel):
    chosen_role: ModelRole
    reason: Annotated[str, Field(min_length=1, max_length=2_000)]
    sensitivity: SensitivityClass
    reasoning_level: ReasoningLevel
    fallback_chain: tuple[ModelRole, ...]
    requested_role: ModelRole | None = None
    fallback_used: bool = False


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
    context_sensitivity: SensitivityClass | None = None
    context_source: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    disclosure_sensitivity: SensitivityClass | None = None
    disclosure_source: Annotated[str, Field(min_length=1, max_length=100)] | None = None

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
        if self.context_source is not None and self.role is not MessageRole.SYSTEM:
            raise ValueError("only system context messages may carry a context source")
        if self.context_sensitivity is not None and self.context_source is None:
            raise ValueError("context sensitivity requires a named context source")
        if (self.disclosure_sensitivity is None) != (self.disclosure_source is None):
            raise ValueError("disclosure sensitivity and source must be set together")
        return self


class ContextProjection(CoreModel):
    """Bounded untrusted context supplied by a local retrieval adapter."""

    content: Annotated[str, Field(min_length=1, max_length=20_000)]
    sensitivity: SensitivityClass
    source_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=20)]
    source: Annotated[str, Field(min_length=1, max_length=100)]


class ToolDefinition(CoreModel):
    name: ToolName
    version: ToolVersion
    description: Annotated[str, Field(min_length=1, max_length=2_000)]
    input_schema: dict[str, JsonValue]
    permission_level: PermissionLevel
    approval_rule: ApprovalRule
    risk: ToolRisk
    side_effect: ToolSideEffect
    sensitivity: SensitivityClass
    required_capabilities: Annotated[tuple[CapabilityName, ...], Field(min_length=1, max_length=32)]
    timeout_seconds: Annotated[float, Field(gt=0, le=30)]
    max_result_bytes: Annotated[int, Field(ge=1, le=100 * 1_024)]
    max_result_items: Annotated[int, Field(ge=1, le=1_000)]
    idempotency: ToolIdempotency
    retry_policy: ToolRetryPolicy
    concurrency: ToolConcurrency
    postcondition: Annotated[str, Field(min_length=1, max_length=2_000)]
    recovery: Annotated[str, Field(min_length=1, max_length=2_000)]

    @field_validator("input_schema")
    @classmethod
    def require_object_input_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if value.get("type") != "object":
            raise ValueError("tool input schema must describe an object")
        return value

    @field_validator("required_capabilities")
    @classmethod
    def require_distinct_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("required capabilities must be distinct")
        return value

    @model_validator(mode="after")
    def validate_security_semantics(self) -> Self:
        valid_shapes: dict[
            PermissionLevel,
            tuple[frozenset[ToolRisk], frozenset[ToolSideEffect], frozenset[ApprovalRule]],
        ] = {
            PermissionLevel.LEVEL_0: (
                frozenset({ToolRisk.READ_ONLY}),
                frozenset({ToolSideEffect.NONE}),
                frozenset({ApprovalRule.NONE}),
            ),
            PermissionLevel.LEVEL_1: (
                frozenset({ToolRisk.REVERSIBLE}),
                frozenset({ToolSideEffect.REVERSIBLE}),
                frozenset({ApprovalRule.EXPLICIT_ENABLEMENT}),
            ),
            PermissionLevel.LEVEL_2: (
                frozenset({ToolRisk.REVERSIBLE}),
                frozenset({ToolSideEffect.REVERSIBLE, ToolSideEffect.EXTERNAL}),
                frozenset({ApprovalRule.POLICY_OR_EXPLICIT}),
            ),
            PermissionLevel.LEVEL_3: (
                frozenset({ToolRisk.SENSITIVE, ToolRisk.DESTRUCTIVE}),
                frozenset(
                    {
                        ToolSideEffect.NONE,
                        ToolSideEffect.REVERSIBLE,
                        ToolSideEffect.EXTERNAL,
                        ToolSideEffect.IRREVERSIBLE,
                    }
                ),
                frozenset({ApprovalRule.EXACT_RECENT_AUTH, ApprovalRule.DISABLED}),
            ),
            PermissionLevel.LEVEL_4: (
                frozenset({ToolRisk.DESTRUCTIVE}),
                frozenset({ToolSideEffect.IRREVERSIBLE, ToolSideEffect.ADMINISTRATIVE}),
                frozenset({ApprovalRule.STEP_UP, ApprovalRule.DISABLED}),
            ),
        }
        risks, side_effects, approval_rules = valid_shapes[self.permission_level]
        if self.risk not in risks:
            raise ValueError(
                f"risk {self.risk.value!r} is invalid for permission level "
                f"{int(self.permission_level)}"
            )
        if self.side_effect not in side_effects:
            raise ValueError(
                f"side effect {self.side_effect.value!r} is invalid for permission level "
                f"{int(self.permission_level)}"
            )
        if self.approval_rule not in approval_rules:
            raise ValueError(
                f"approval rule {self.approval_rule.value!r} is invalid for permission level "
                f"{int(self.permission_level)}"
            )
        if (
            self.side_effect is ToolSideEffect.NONE
            and self.idempotency is not ToolIdempotency.SIDE_EFFECT_FREE
        ):
            raise ValueError("tools without side effects must declare side-effect-free idempotency")
        if (
            self.side_effect is not ToolSideEffect.NONE
            and self.idempotency is ToolIdempotency.SIDE_EFFECT_FREE
        ):
            raise ValueError("tools with side effects cannot declare side-effect-free idempotency")
        if (
            self.idempotency is ToolIdempotency.NON_IDEMPOTENT
            and self.retry_policy is ToolRetryPolicy.TRANSIENT_ONLY
        ):
            raise ValueError("non-idempotent tools cannot retry without reconciliation")
        if (
            self.side_effect in {ToolSideEffect.IRREVERSIBLE, ToolSideEffect.ADMINISTRATIVE}
            and self.retry_policy is ToolRetryPolicy.TRANSIENT_ONLY
        ):
            raise ValueError("irreversible or administrative tools cannot retry automatically")
        return self

    @property
    def requires_approval(self) -> bool:
        """Compatibility view for Phase 1 policy; richer policy uses ``approval_rule``."""
        return self.approval_rule is not ApprovalRule.NONE


class ProviderResponse(CoreModel):
    """Normalized provider output; the service revalidates every response."""

    content: Annotated[str, Field(max_length=100_000)] | None = None
    tool_calls: Annotated[tuple[ToolCall, ...], Field(max_length=64)] = ()
    usage: ProviderUsage | None = None
    routing: RoutingDecision | None = None

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if not (self.content and self.content.strip()) and not self.tool_calls:
            raise ValueError("provider response requires content or at least one tool call")
        call_ids = [call.id for call in self.tool_calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("provider response contains duplicate tool call ids")
        return self


class ProviderStreamFrame(CoreModel):
    """One provider token/routing update or the terminal normalized response."""

    content_delta: Annotated[str, Field(min_length=1, max_length=100_000)] | None = None
    routing: RoutingDecision | None = None
    response: ProviderResponse | None = None

    @model_validator(mode="after")
    def require_exactly_one_value(self) -> Self:
        populated = sum(
            value is not None for value in (self.content_delta, self.routing, self.response)
        )
        if populated != 1:
            raise ValueError("provider stream frames require exactly one value")
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
    approval_required: bool = False
    approval_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_decision_shape(self) -> Self:
        if not self.allowed and not (self.reason and self.reason.strip()):
            raise ValueError("denied policy decisions require a reason")
        if self.allowed and (self.approval_required or self.approval_id is not None):
            raise ValueError("allowed policy decisions cannot require approval")
        if self.approval_required and self.approval_id is None:
            raise ValueError("approval-required decisions require an approval ID")
        if not self.approval_required and self.approval_id is not None:
            raise ValueError("approval IDs are valid only for approval-required decisions")
        return self


class AssistantRequest(CoreModel):
    user_input: Annotated[str, Field(min_length=1, max_length=100_000)]
    conversation_id: Identifier | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    requested_model_role: ModelRole | None = None
    reasoning_level: ReasoningLevel | None = None
    latency_class: LatencyClass | None = None

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
    APPROVAL_REQUIRED = "approval_required"
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
    APPROVAL_REQUIRED = "approval_required"
    BROKER_REQUIRED = "broker_required"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_RESULT_LIMIT = "tool_result_limit"
    TOOL_ERROR = "tool_error"
    TOOL_ITERATION_LIMIT = "tool_iteration_limit"


class RuntimeErrorDetail(CoreModel):
    code: RuntimeErrorCode
    message: Annotated[str, Field(min_length=1, max_length=4_000)]
    tool_call_id: Identifier | None = None
    tool_name: ToolName | None = None
    approval_id: Identifier | None = None


class RuntimeEventType(StrEnum):
    CONVERSATION_CREATED = "conversation_created"
    CONVERSATION_RESUMED = "conversation_resumed"
    MESSAGE_PERSISTED = "message_persisted"
    PROVIDER_REQUESTED = "provider_requested"
    PROVIDER_RESPONDED = "provider_responded"
    ROUTING_DECIDED = "routing_decided"
    PROVIDER_FALLBACK = "provider_fallback"
    ASSISTANT_DELTA = "assistant_delta"
    TOOL_REQUESTED = "tool_requested"
    TOOL_VALIDATED = "tool_validated"
    TOOL_AUTHORIZED = "tool_authorized"
    TOOL_DENIED = "tool_denied"
    TOOL_APPROVAL_REQUIRED = "tool_approval_required"
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
    routing: RoutingDecision | None = None
    usage: ProviderUsage | None = None
    content_delta: Annotated[str, Field(min_length=1, max_length=100_000)] | None = None


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


class RuntimeStreamFrame(CoreModel):
    """One live runtime event or the terminal result of a streamed turn."""

    event: RuntimeEvent | None = None
    result: RuntimeResult | None = None

    @model_validator(mode="after")
    def require_exactly_one_value(self) -> Self:
        if (self.event is None) == (self.result is None):
            raise ValueError("stream frames require exactly one event or result")
        return self
