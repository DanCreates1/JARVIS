"""Deterministic privacy gate and capability-aware zero-cost model router."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from uuid import uuid4

from jarvis.core.models import (
    LatencyClass,
    Message,
    MessageRole,
    ModelRole,
    ProviderResponse,
    ProviderStreamFrame,
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
from .health import LatencyBudgets, ProviderHealthSnapshot, ProviderHealthTracker

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
        latency_class: LatencyClass | None = None,
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
            or latency_class is LatencyClass.DEEP_REASONING
            or _DEEP_PATTERN.search(text)
            or len(text) > 4_000
        ):
            role = ModelRole.REASONING
            level = ReasoningLevel.DEEP
            reason = "Safe request requires complex or large-context reasoning."
        elif latency_class is LatencyClass.FAST_CLOUD:
            role = ModelRole.FAST
            level = ReasoningLevel.NONE
            reason = "Safe request explicitly requires the responsive cloud tier."
        elif requested_reasoning is ReasoningLevel.MODERATE or _MODERATE_PATTERN.search(text):
            role = ModelRole.PRIMARY
            level = ReasoningLevel.MODERATE
            reason = "Safe request exceeds the normal local tier and uses responsive cloud."
        else:
            role = ModelRole.LOCAL
            level = ReasoningLevel.NONE
            reason = "Safe simple or normal interaction uses the latency-stable local tier."
        return RoutingDecision(
            chosen_role=role,
            reason=reason,
            sensitivity=sensitivity,
            reasoning_level=level,
            fallback_chain=_fallback_chain(role, sensitivity=sensitivity),
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
        health: ProviderHealthTracker | None = None,
        latency_budgets: LatencyBudgets | None = None,
    ) -> None:
        if max_cloud_cost_usd != 0:
            raise ValueError("Phase 1 requires max_cloud_cost_usd to equal 0")
        if ModelRole.LOCAL not in providers:
            raise ValueError("A LOCAL provider is mandatory")
        self.providers = dict(providers)
        self.policy = policy or RoutingPolicy()
        self.max_cloud_cost_usd = max_cloud_cost_usd
        self.health = health or ProviderHealthTracker()
        self.latency_budgets = latency_budgets or LatencyBudgets()

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
        latency_class: LatencyClass | None = None,
    ) -> ProviderResponse:
        response: ProviderResponse | None = None
        async for frame in self.stream_chat_routed(
            messages=messages,
            tools=tools,
            requested_role=requested_role,
            reasoning_level=reasoning_level,
            latency_class=latency_class,
        ):
            if frame.response is not None:
                response = frame.response
        if response is None:
            raise ProviderProtocolError("Provider stream ended without a terminal response")
        return response

    async def stream_chat_routed(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        requested_role: ModelRole | None = None,
        reasoning_level: ReasoningLevel | None = None,
        latency_class: LatencyClass | None = None,
    ) -> AsyncIterator[ProviderStreamFrame]:
        latest_user = next(
            (message.content for message in reversed(messages) if message.role is MessageRole.USER),
            "",
        )
        latest = messages[-1] if messages else None
        if latest is not None and latest.role is MessageRole.TOOL:
            yield ProviderStreamFrame(
                response=ProviderResponse(content=_tool_result_text(latest.content))
            )
            return

        direct_call = self.policy.gate.direct_tool_call(latest_user)
        if direct_call is not None and not any(
            message.role is MessageRole.TOOL for message in messages
        ):
            yield ProviderStreamFrame(
                response=ProviderResponse(content=None, tool_calls=(direct_call,))
            )
            return

        disclosure_text = "\n".join(_message_disclosure_text(message) for message in messages)
        forced_sensitivity = _messages_sensitivity(messages, self.policy.gate)
        decision = self.policy.decide(
            disclosure_text,
            requested_role=requested_role,
            requested_reasoning=reasoning_level,
            forced_sensitivity=forced_sensitivity,
            latency_class=latency_class,
        )
        roles = self._ordered_roles(decision, requested_role=requested_role)
        failures: list[str] = []
        for role in roles:
            provider = self.providers.get(role)
            if provider is None:
                failures.append(f"{role.value}: not configured")
                continue
            if decision.sensitivity is not SensitivityClass.PUBLIC and provider.profile.is_cloud:
                continue
            provider_stream: AsyncIterator[ProviderStreamFrame] | None = None
            first_frame: ProviderStreamFrame | None = None
            last_error: Exception | None = None
            attempts = 1 if provider.profile.is_cloud else 2
            budget_ms = self._budget_for_role(role, latency_class=latency_class)
            for attempt in range(attempts):
                try:
                    provider_stream = provider.stream_chat(
                        messages=messages,
                        tools=_tools_for_provider(
                            tools,
                            is_cloud=provider.profile.is_cloud,
                            query=latest_user,
                        ),
                        reasoning_level=decision.reasoning_level.value,
                    )
                    first_frame = ProviderStreamFrame.model_validate(await anext(provider_stream))
                    break
                except StopAsyncIteration:
                    last_error = ProviderProtocolError(
                        "Provider stream ended without a terminal response"
                    )
                except Exception as exc:
                    last_error = exc
                    self.health.record_failure(
                        _provider_key(provider),
                        exc,
                        budget_ms=budget_ms,
                    )
                if not _is_retryable(last_error) or attempt == attempts - 1:
                    break
            if provider_stream is None or first_frame is None:
                assert last_error is not None
                failures.append(f"{role.value}: {type(last_error).__name__}")
                if decision.sensitivity is not SensitivityClass.PUBLIC:
                    raise PrivateRouteUnavailableError(
                        "Private request could not run locally; cloud fallback is prohibited."
                    ) from last_error
                continue
            actual_decision = decision.model_copy(
                update={
                    "chosen_role": role,
                    "reason": decision.reason
                    + (f" Fallback selected after: {', '.join(failures)}." if failures else ""),
                    "fallback_used": bool(failures),
                }
            )
            yield ProviderStreamFrame(routing=actual_decision)
            terminal_seen = False
            current_frame: ProviderStreamFrame | None = first_frame
            try:
                while current_frame is not None:
                    if current_frame.response is not None:
                        if terminal_seen:
                            raise ProviderProtocolError(
                                "Provider stream returned multiple terminal responses"
                            )
                        terminal_seen = True
                        response = current_frame.response
                        if (
                            response.usage
                            and response.usage.estimated_cost_usd > self.max_cloud_cost_usd
                        ):
                            raise ZeroCostPolicyError("Provider usage violates zero-dollar budget")
                        self.health.record_success(
                            _provider_key(provider),
                            response.usage,
                            budget_ms=budget_ms,
                        )
                        yield ProviderStreamFrame(
                            response=response.model_copy(update={"routing": actual_decision})
                        )
                    else:
                        yield current_frame
                    current_frame = ProviderStreamFrame.model_validate(await anext(provider_stream))
            except StopAsyncIteration:
                current_frame = None
            except Exception as exc:
                self.health.record_failure(
                    _provider_key(provider),
                    exc,
                    budget_ms=budget_ms,
                )
                raise
            if not terminal_seen:
                error = ProviderProtocolError("Provider stream ended without a terminal response")
                self.health.record_failure(
                    _provider_key(provider),
                    error,
                    budget_ms=budget_ms,
                )
                raise error
            return

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
    ) -> AsyncIterator[ProviderStreamFrame]:
        async for frame in self.stream_chat_routed(messages=messages, tools=tools):
            yield frame

    async def validate_models(self) -> dict[ModelRole, bool]:
        results: dict[ModelRole, bool] = {}
        for role, provider in self.providers.items():
            try:
                results[role] = await provider.validate_model()
            except Exception:
                results[role] = False
        return results

    def health_snapshot(self) -> dict[ModelRole, ProviderHealthSnapshot]:
        return {
            role: self.health.snapshot(
                _provider_key(provider), budget_ms=self._budget_for_role(role)
            )
            for role, provider in self.providers.items()
        }

    def _budget_for_role(
        self,
        role: ModelRole,
        *,
        latency_class: LatencyClass | None = None,
    ) -> float:
        if role is ModelRole.REASONING:
            return self.latency_budgets.deep_reasoning_ms
        if latency_class is LatencyClass.NORMAL_VOICE:
            return self.latency_budgets.normal_voice_ms
        if role in {ModelRole.FAST, ModelRole.PRIMARY}:
            return self.latency_budgets.fast_cloud_ms
        return self.latency_budgets.simple_local_ms

    def _ordered_roles(
        self,
        decision: RoutingDecision,
        *,
        requested_role: ModelRole | None,
    ) -> tuple[ModelRole, ...]:
        normal = (decision.chosen_role, *decision.fallback_chain)
        if decision.chosen_role is not ModelRole.REASONING or requested_role is not None:
            return normal
        provider = self.providers.get(ModelRole.REASONING)
        if provider is None:
            return normal
        health = self.health.snapshot(
            _provider_key(provider),
            budget_ms=self.latency_budgets.deep_reasoning_ms,
        )
        if not health.degraded:
            return normal
        return tuple(dict.fromkeys((*decision.fallback_chain, ModelRole.REASONING)))

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
    query: str,
) -> tuple[ToolDefinition, ...]:
    """Keep private/unknown tool schemas and host-owned enum values local."""
    if not is_cloud:
        return tuple(tools)
    query_tokens = _relevance_tokens(query)
    return tuple(
        tool
        for tool in tools
        if tool.sensitivity is SensitivityClass.PUBLIC
        and bool(query_tokens & _relevance_tokens(f"{tool.name} {tool.description}"))
    )


def _fallback_chain(
    role: ModelRole,
    *,
    sensitivity: SensitivityClass,
) -> tuple[ModelRole, ...]:
    if role is ModelRole.REASONING:
        return (ModelRole.PRIMARY, ModelRole.LOCAL)
    if role is ModelRole.PRIMARY:
        return (ModelRole.FAST, ModelRole.LOCAL)
    if role is ModelRole.FAST:
        return (ModelRole.LOCAL,)
    if role is ModelRole.LOCAL and sensitivity is SensitivityClass.PUBLIC:
        return (ModelRole.FAST, ModelRole.PRIMARY)
    return ()


_RELEVANCE_STOPWORDS = frozenset(
    {"a", "an", "and", "for", "get", "in", "is", "of", "on", "or", "the", "to"}
)


def _relevance_tokens(text: str) -> frozenset[str]:
    return frozenset(
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) >= 2 and token not in _RELEVANCE_STOPWORDS
    )


def _provider_key(provider: ModelProvider) -> str:
    return f"{provider.profile.provider}:{provider.profile.model_id}"


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
