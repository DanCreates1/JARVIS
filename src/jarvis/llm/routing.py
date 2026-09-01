"""Deterministic privacy gate and capability-aware zero-cost model router."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from uuid import uuid4

from jarvis.core.models import (
    Message,
    MessageRole,
    ModelRole,
    ProviderResponse,
    ReasoningLevel,
    RoutingDecision,
    SensitivityClass,
    ToolCall,
    ToolDefinition,
)

from .base import (
    ModelProvider,
    PrivateRouteUnavailableError,
    ProviderAuthenticationError,
    ProviderModelUnavailableError,
    ProviderProtocolError,
    ProviderQuotaError,
    ProviderUnavailableError,
    ZeroCostPolicyError,
)

_PRIVATE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(password|passcode|api[ _-]?key|secret|token|credential|private key)\b",
        r"\b(ssn|social security|passport|driver'?s license|credit card|bank account)\b",
        r"\b(my (?:email|phone|address|medical|health|tax|salary|finances?|messages?|files?))\b",
        r"\b(my|mine|our|ours|remember (?:that|this)|you know about me)\b",
        r"\bI (?:am|live|work|have|feel|was|earn|owe|take|need you to remember)\b",
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        r"\b(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}\b",
        r"\b(read|open|delete|move|rename|write|upload|send)\b.{0,40}\b(file|folder|email|message)\b",
        r"(?:[A-Z]:\\|/home/|/Users/|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY)",
        r"\b(?:\d[ -]*?){13,19}\b",
    )
)
_DEEP_PATTERN = re.compile(
    r"\b(research|deep reasoning|prove|architecture review|large document|multimodal|"
    r"difficult coding|complex analysis)\b",
    re.IGNORECASE,
)
_MODERATE_PATTERN = re.compile(
    r"\b(analyze|compare|debug|design|plan|reason|trade-?offs?|explain why)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_PATTERN = re.compile(
    r"\b(this|that|above|attached|attachment|continue|previous|prior|same one|the document|"
    r"the file|confidential|internal|client|customer|patient|employee)\b",
    re.IGNORECASE,
)
_PUBLIC_PATTERN = re.compile(
    r"^(?:"
    r"hello|hi|hey|"
    r"public\b|"
    r"what\s+(?:is|are|was|were|does|do|did|can|could|would|should)\b|"
    r"why\b|how\b|when\b|where\b|who\b|which\b|"
    r"explain\b|name\b|state\b|give\b|reply\b|provide\b|prove\b|"
    r"compare\b|research\b|analy[sz]e\b|do\s+complex\b|"
    r"write\b|draft\b|create\b|summarize\b|tell\s+me\b"
    r")",
    re.IGNORECASE,
)
_TIME_COMMAND = re.compile(
    r"^(?:please\s+)?(?:(?:what(?:'s| is)\s+)?(?:the\s+)?(?:current\s+)?time"
    r"(?:\s+now)?|tell\s+me\s+(?:the\s+)?time)[?.!]*$",
    re.IGNORECASE,
)


class PrivacyGate:
    """Conservative, local-only rules. No request content leaves this object."""

    def classify(self, text: str) -> SensitivityClass:
        normalized = text.strip()
        if not normalized:
            return SensitivityClass.UNKNOWN
        if any(pattern.search(normalized) for pattern in _PRIVATE_PATTERNS):
            return SensitivityClass.PRIVATE
        if "\n" in normalized or _AMBIGUOUS_PATTERN.search(normalized):
            return SensitivityClass.UNKNOWN
        if _PUBLIC_PATTERN.search(normalized):
            return SensitivityClass.PUBLIC
        return SensitivityClass.UNKNOWN

    def direct_tool_call(self, text: str) -> ToolCall | None:
        if _TIME_COMMAND.fullmatch(text.strip()):
            return ToolCall(id=f"local-{uuid4()}", name="get_current_time", arguments={})
        return None


class RoutingPolicy:
    def __init__(self, gate: PrivacyGate | None = None) -> None:
        self.gate = gate or PrivacyGate()

    def decide(
        self,
        text: str,
        *,
        requested_role: ModelRole | None = None,
        requested_reasoning: ReasoningLevel | None = None,
        forced_sensitivity: SensitivityClass | None = None,
    ) -> RoutingDecision:
        sensitivity = forced_sensitivity or self.gate.classify(text)
        if sensitivity is not SensitivityClass.PUBLIC:
            role = ModelRole.LOCAL
            level = ReasoningLevel.NONE
            reason = "Sensitive or uncertain content must remain local."
        elif requested_role is not None:
            role = requested_role
            level = requested_reasoning or _reasoning_for_role(role)
            reason = f"Explicit safe-content override requested role {role.value}."
        elif (
            requested_reasoning is ReasoningLevel.DEEP
            or _DEEP_PATTERN.search(text)
            or len(text) > 4_000
        ):
            role = ModelRole.REASONING
            level = ReasoningLevel.DEEP
            reason = "Safe request requires complex or large-context reasoning."
        elif requested_reasoning is ReasoningLevel.MODERATE or _MODERATE_PATTERN.search(text):
            role = ModelRole.PRIMARY
            level = ReasoningLevel.MODERATE
            reason = "Safe request requires moderate reasoning."
        elif len(text) <= 140:
            role = ModelRole.FAST
            level = ReasoningLevel.NONE
            reason = "Safe bounded request can use the fast role."
        else:
            role = ModelRole.PRIMARY
            level = ReasoningLevel.NONE
            reason = "Safe normal conversation uses the primary non-thinking role."
        return RoutingDecision(
            chosen_role=role,
            reason=reason,
            sensitivity=sensitivity,
            reasoning_level=level,
            fallback_chain=_fallback_chain(role),
            requested_role=requested_role,
        )


class ModelRouter:
    """Route only public content to cloud and fail over without paid execution."""

    def __init__(
        self,
        providers: Mapping[ModelRole, ModelProvider],
        *,
        policy: RoutingPolicy | None = None,
        max_cloud_cost_usd: float = 0,
    ) -> None:
        if max_cloud_cost_usd != 0:
            raise ValueError("Phase 1 requires max_cloud_cost_usd to equal 0")
        if ModelRole.LOCAL not in providers:
            raise ValueError("A LOCAL provider is mandatory")
        self.providers = dict(providers)
        self.policy = policy or RoutingPolicy()
        self.max_cloud_cost_usd = max_cloud_cost_usd

    async def chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> ProviderResponse:
        return await self.chat_routed(messages=messages, tools=tools)

    async def chat_routed(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        requested_role: ModelRole | None = None,
        reasoning_level: ReasoningLevel | None = None,
    ) -> ProviderResponse:
        latest_user = next(
            (message.content for message in reversed(messages) if message.role is MessageRole.USER),
            "",
        )
        latest = messages[-1] if messages else None
        if latest is not None and latest.role is MessageRole.TOOL:
            return ProviderResponse(content=_tool_result_text(latest.content))

        direct_call = self.policy.gate.direct_tool_call(latest_user)
        if direct_call is not None and not any(
            message.role is MessageRole.TOOL for message in messages
        ):
            return ProviderResponse(content=None, tool_calls=(direct_call,))

        disclosure_text = "\n".join(_message_disclosure_text(message) for message in messages)
        forced_sensitivity = _messages_sensitivity(messages, self.policy.gate)
        decision = self.policy.decide(
            disclosure_text,
            requested_role=requested_role,
            requested_reasoning=reasoning_level,
            forced_sensitivity=forced_sensitivity,
        )
        roles = (decision.chosen_role, *decision.fallback_chain)
        failures: list[str] = []
        for role in roles:
            provider = self.providers.get(role)
            if provider is None:
                failures.append(f"{role.value}: not configured")
                continue
            if decision.sensitivity is not SensitivityClass.PUBLIC and provider.profile.is_cloud:
                continue
            response: ProviderResponse | None = None
            last_error: Exception | None = None
            for attempt in range(2):
                try:
                    response = await provider.chat(
                        messages=messages,
                        tools=_tools_for_provider(
                            tools,
                            is_cloud=provider.profile.is_cloud,
                        ),
                        reasoning_level=decision.reasoning_level.value,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    if not _is_retryable(exc) or attempt == 1:
                        break
            if response is None:
                assert last_error is not None
                failures.append(f"{role.value}: {type(last_error).__name__}")
                if decision.sensitivity is not SensitivityClass.PUBLIC:
                    raise PrivateRouteUnavailableError(
                        "Private request could not run locally; cloud fallback is prohibited."
                    ) from last_error
                continue
            if response.usage and response.usage.estimated_cost_usd > self.max_cloud_cost_usd:
                raise ZeroCostPolicyError("Provider usage violates zero-dollar budget")
            actual_decision = decision.model_copy(
                update={
                    "chosen_role": role,
                    "reason": decision.reason
                    + (f" Fallback selected after: {', '.join(failures)}." if failures else ""),
                    "fallback_used": bool(failures),
                }
            )
            return response.model_copy(update={"routing": actual_decision})

        if decision.sensitivity is not SensitivityClass.PUBLIC:
            raise PrivateRouteUnavailableError(
                "Private request could not run locally; cloud fallback is prohibited."
            )
        raise ProviderUnavailableError(
            "No zero-cost provider could serve the request (" + "; ".join(failures) + ")."
        )

    async def stream_chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> AsyncIterator[ProviderResponse]:
        yield await self.chat(messages=messages, tools=tools)

    async def validate_models(self) -> dict[ModelRole, bool]:
        results: dict[ModelRole, bool] = {}
        for role, provider in self.providers.items():
            try:
                results[role] = await provider.validate_model()
            except Exception:
                results[role] = False
        return results

    async def close(self) -> None:
        seen: set[int] = set()
        for provider in self.providers.values():
            if id(provider) in seen:
                continue
            seen.add(id(provider))
            await provider.close()


def _reasoning_for_role(role: ModelRole) -> ReasoningLevel:
    if role is ModelRole.REASONING:
        return ReasoningLevel.DEEP
    if role is ModelRole.PRIMARY:
        return ReasoningLevel.NONE
    return ReasoningLevel.NONE


def _message_disclosure_text(message: Message) -> str:
    parts = [message.content]
    parts.extend(
        json.dumps(call.arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for call in message.tool_calls
    )
    return "\n".join(part for part in parts if part)


def _messages_sensitivity(
    messages: Sequence[Message],
    gate: PrivacyGate,
) -> SensitivityClass:
    sensitivity = SensitivityClass.PUBLIC
    for message in messages:
        explicit = message.disclosure_sensitivity or message.context_sensitivity
        if explicit is not None:
            sensitivity = _more_restrictive(sensitivity, explicit)
        elif message.role is not MessageRole.USER:
            sensitivity = _more_restrictive(sensitivity, SensitivityClass.UNKNOWN)
        scanned = gate.classify(_message_disclosure_text(message))
        if explicit is None or scanned is SensitivityClass.PRIVATE:
            sensitivity = _more_restrictive(sensitivity, scanned)
    return sensitivity


def _more_restrictive(
    left: SensitivityClass,
    right: SensitivityClass,
) -> SensitivityClass:
    order = {
        SensitivityClass.PUBLIC: 0,
        SensitivityClass.UNKNOWN: 1,
        SensitivityClass.PRIVATE: 2,
    }
    return left if order[left] >= order[right] else right


def _tools_for_provider(
    tools: Sequence[ToolDefinition],
    *,
    is_cloud: bool,
) -> tuple[ToolDefinition, ...]:
    """Keep private/unknown tool schemas and host-owned enum values local."""
    if not is_cloud:
        return tuple(tools)
    return tuple(tool for tool in tools if tool.sensitivity is SensitivityClass.PUBLIC)


def _fallback_chain(role: ModelRole) -> tuple[ModelRole, ...]:
    if role is ModelRole.REASONING:
        return (ModelRole.PRIMARY, ModelRole.LOCAL)
    if role is ModelRole.PRIMARY:
        return (ModelRole.FAST, ModelRole.LOCAL)
    if role is ModelRole.FAST:
        return (ModelRole.LOCAL,)
    return ()


def _is_retryable(error: Exception) -> bool:
    return isinstance(error, ProviderUnavailableError) and not isinstance(
        error,
        (
            ProviderQuotaError,
            ProviderModelUnavailableError,
            ProviderAuthenticationError,
            ProviderProtocolError,
        ),
    )


def _tool_result_text(raw: str) -> str:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str):
            return content
    return raw
