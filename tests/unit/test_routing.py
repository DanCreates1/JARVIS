from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator, Iterable, Sequence
from pathlib import Path

import pytest

from jarvis.core import (
    LatencyClass,
    Message,
    MessageRole,
    ModelCapability,
    ModelLifecycle,
    ModelProfile,
    ModelRole,
    ProviderLatencyBreakdown,
    ProviderResponse,
    ProviderStreamFrame,
    ProviderUsage,
    ReasoningLevel,
    SensitivityClass,
    ToolCall,
    ToolDefinition,
)
from jarvis.llm import (
    LatencyBudgets,
    ModelRouter,
    PrivacyGate,
    PrivateRouteUnavailableError,
    ProviderHealthTracker,
    ProviderQuotaError,
    ProviderUnavailableError,
    RoutingPolicy,
    ZeroCostPolicyError,
)
from jarvis.tools.clock import CurrentTimeTool
from jarvis.tools.system_status import SystemStatusTool


class FakeModelProvider:
    def __init__(
        self,
        role: ModelRole,
        *,
        cloud: bool,
        outcomes: Iterable[ProviderResponse | BaseException],
        available: bool = True,
    ) -> None:
        self._profile = ModelProfile(
            role=role,
            provider="cloud" if cloud else "ollama",
            model_id=f"model-{role.value}",
            capabilities=(ModelCapability.TEXT, ModelCapability.TOOLS),
            lifecycle=ModelLifecycle.PRODUCTION if cloud else ModelLifecycle.LOCAL,
            context_window=8_192,
            is_cloud=cloud,
        )
        self.outcomes = deque(outcomes)
        self.available = available
        self.requests: list[str] = []
        self.message_requests: list[tuple[Message, ...]] = []
        self.tool_requests: list[tuple[ToolDefinition, ...]] = []
        self.closed = False

    @property
    def profile(self) -> ModelProfile:
        return self._profile

    async def chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        reasoning_level: str = "none",
    ) -> ProviderResponse:
        self.message_requests.append(tuple(messages))
        self.requests.append(reasoning_level)
        self.tool_requests.append(tuple(tools))
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def stream_chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        reasoning_level: str = "none",
    ) -> AsyncIterator[ProviderStreamFrame]:
        response = await self.chat(messages=messages, tools=tools, reasoning_level=reasoning_level)
        yield ProviderStreamFrame(response=response)

    async def validate_model(self) -> bool:
        return self.available

    async def close(self) -> None:
        self.closed = True


def user_message(text: str) -> Message:
    return Message(conversation_id="conversation", role=MessageRole.USER, content=text)


def test_privacy_gate_and_routing_policy_cover_all_roles() -> None:
    gate = PrivacyGate()
    assert gate.classify("My password is hunter2") is SensitivityClass.PRIVATE
    assert gate.classify("Read C:\\Users\\me\\private.txt") is SensitivityClass.PRIVATE
    assert gate.classify("Explain photosynthesis") is SensitivityClass.PUBLIC
    assert gate.classify("Use that one") is SensitivityClass.UNKNOWN
    assert gate.classify("opaque payload") is SensitivityClass.UNKNOWN
    assert gate.classify("  ") is SensitivityClass.UNKNOWN
    assert gate.direct_tool_call("What's the current time?") is not None
    assert gate.direct_tool_call("Please tell me the time.") is not None
    assert gate.direct_tool_call("Explain time zones") is None

    policy = RoutingPolicy(gate)
    assert policy.decide("Hello").chosen_role is ModelRole.LOCAL
    assert (
        policy.decide("Hello", latency_class=LatencyClass.FAST_CLOUD).chosen_role is ModelRole.FAST
    )
    assert policy.decide("Compare these two public algorithms").chosen_role is ModelRole.PRIMARY
    assert (
        policy.decide("Do complex analysis of public benchmark data").chosen_role
        is ModelRole.REASONING
    )
    assert policy.decide("My API key is secret").chosen_role is ModelRole.LOCAL
    overridden = policy.decide("Public weather data", requested_role=ModelRole.REASONING)
    assert overridden.chosen_role is ModelRole.REASONING
    assert overridden.reasoning_level is ReasoningLevel.DEEP
    protected = policy.decide("My medical records", requested_role=ModelRole.REASONING)
    assert protected.chosen_role is ModelRole.LOCAL


@pytest.mark.asyncio
async def test_router_direct_command_and_tool_result_do_not_call_any_model() -> None:
    local = FakeModelProvider(
        ModelRole.LOCAL, cloud=False, outcomes=[ProviderResponse(content="unused")]
    )
    router = ModelRouter({ModelRole.LOCAL: local})
    response = await router.chat(messages=[user_message("What is the time?")], tools=[])
    assert response.tool_calls[0].name == "get_current_time"
    assert not local.requests

    tool_message = Message(
        conversation_id="conversation",
        role=MessageRole.TOOL,
        content="It is noon.",
        tool_call_id="call",
        tool_name="get_current_time",
    )
    response = await router.chat(messages=[user_message("time"), tool_message], tools=[])
    assert response.content == "It is noon."
    assert not local.requests

    normalized_tool = tool_message.model_copy(
        update={"content": '{"content":"Human result","is_error":false,"data":null}'}
    )
    response = await router.chat(messages=[user_message("time"), normalized_tool], tools=[])
    assert response.content == "Human result"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_role", [MessageRole.ASSISTANT, MessageRole.TOOL])
async def test_legacy_unlabelled_non_user_history_fails_local(
    legacy_role: MessageRole,
) -> None:
    cloud = FakeModelProvider(
        ModelRole.FAST,
        cloud=True,
        outcomes=[ProviderResponse(content="must not run")],
    )
    local = FakeModelProvider(
        ModelRole.LOCAL,
        cloud=False,
        outcomes=[ProviderResponse(content="local answer")],
    )
    legacy = Message(
        conversation_id="conversation",
        role=legacy_role,
        content="legacy context",
        **(
            {"tool_call_id": "call", "tool_name": "get_current_time"}
            if legacy_role is MessageRole.TOOL
            else {}
        ),
    )
    router = ModelRouter({ModelRole.FAST: cloud, ModelRole.LOCAL: local})

    response = await router.chat_routed(
        messages=[legacy, user_message("What is the largest planet?")],
        tools=[],
    )

    assert response.content == "local answer"
    assert not cloud.requests
    assert len(local.requests) == 1


@pytest.mark.asyncio
async def test_labelled_public_history_can_use_cloud_but_private_scan_overrides_label() -> None:
    cloud = FakeModelProvider(
        ModelRole.FAST,
        cloud=True,
        outcomes=[ProviderResponse(content="cloud answer")],
    )
    local = FakeModelProvider(
        ModelRole.LOCAL,
        cloud=False,
        outcomes=[ProviderResponse(content="local answer")],
    )
    router = ModelRouter({ModelRole.FAST: cloud, ModelRole.LOCAL: local})
    public_assistant = Message(
        conversation_id="conversation",
        role=MessageRole.ASSISTANT,
        content="Jupiter is the largest planet.",
        disclosure_sensitivity=SensitivityClass.PUBLIC,
        disclosure_source="assistant-turn",
    )

    response = await router.chat_routed(
        messages=[public_assistant, user_message("What is the largest planet?")],
        tools=[],
        requested_role=ModelRole.FAST,
    )
    assert response.content == "cloud answer"
    assert len(cloud.requests) == 1

    private_assistant = public_assistant.model_copy(
        update={"content": "My password is synthetic-secret."}
    )
    response = await router.chat_routed(
        messages=[private_assistant, user_message("What is the largest planet?")],
        tools=[],
        requested_role=ModelRole.FAST,
    )
    assert response.content == "local answer"
    assert len(cloud.requests) == 1
    assert len(local.requests) == 1


@pytest.mark.asyncio
async def test_private_tool_call_arguments_force_local_even_when_message_is_labelled_public() -> (
    None
):
    cloud = FakeModelProvider(
        ModelRole.FAST,
        cloud=True,
        outcomes=[ProviderResponse(content="must not run")],
    )
    local = FakeModelProvider(
        ModelRole.LOCAL,
        cloud=False,
        outcomes=[ProviderResponse(content="local answer")],
    )
    assistant = Message(
        conversation_id="conversation",
        role=MessageRole.ASSISTANT,
        tool_calls=(
            ToolCall(
                id="call-private",
                name="get_current_time",
                arguments={"note": "API key secret"},
            ),
        ),
        disclosure_sensitivity=SensitivityClass.PUBLIC,
        disclosure_source="assistant-turn",
    )
    router = ModelRouter({ModelRole.FAST: cloud, ModelRole.LOCAL: local})

    response = await router.chat(
        messages=[assistant, user_message("What is the largest planet?")],
        tools=[],
    )

    assert response.content == "local answer"
    assert not cloud.requests
    assert len(local.requests) == 1


@pytest.mark.asyncio
async def test_safe_primary_falls_back_to_fast_then_records_actual_route() -> None:
    primary = FakeModelProvider(
        ModelRole.PRIMARY,
        cloud=True,
        outcomes=[ProviderQuotaError("quota")],
    )
    fast = FakeModelProvider(
        ModelRole.FAST,
        cloud=True,
        outcomes=[ProviderResponse(content="fallback answer")],
    )
    local = FakeModelProvider(ModelRole.LOCAL, cloud=False, outcomes=[])
    router = ModelRouter(
        {
            ModelRole.PRIMARY: primary,
            ModelRole.FAST: fast,
            ModelRole.LOCAL: local,
        }
    )
    response = await router.chat_routed(
        messages=[user_message("What is the UTC timezone?")],
        tools=[],
        requested_role=ModelRole.PRIMARY,
    )
    assert response.content == "fallback answer"
    assert response.routing is not None
    assert response.routing.chosen_role is ModelRole.FAST
    assert "ProviderQuotaError" in response.routing.reason
    assert primary.requests == ["none"]
    assert fast.requests == ["none"]


@pytest.mark.asyncio
async def test_cloud_provider_never_receives_private_tool_schemas_or_host_enums(
    tmp_path: Path,
) -> None:
    public_tool = CurrentTimeTool().definition
    private_tool = SystemStatusTool(probe_path=tmp_path).definition.model_copy(
        update={
            "input_schema": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "string",
                        "enum": ["private-host-application"],
                    }
                },
                "additionalProperties": False,
            }
        }
    )
    cloud = FakeModelProvider(
        ModelRole.PRIMARY,
        cloud=True,
        outcomes=[ProviderResponse(content="public answer")],
    )
    local = FakeModelProvider(ModelRole.LOCAL, cloud=False, outcomes=[])
    router = ModelRouter({ModelRole.PRIMARY: cloud, ModelRole.LOCAL: local})

    response = await router.chat_routed(
        messages=[user_message("What is the UTC timezone?")],
        tools=(public_tool, private_tool),
        requested_role=ModelRole.PRIMARY,
    )

    assert response.content == "public answer"
    assert cloud.tool_requests == [(public_tool,)]
    assert "private-host-application" not in repr(cloud.tool_requests)
    assert not local.tool_requests


@pytest.mark.asyncio
async def test_local_provider_receives_private_tool_schemas(tmp_path: Path) -> None:
    public_tool = CurrentTimeTool().definition
    private_tool = SystemStatusTool(probe_path=tmp_path).definition
    local = FakeModelProvider(
        ModelRole.LOCAL,
        cloud=False,
        outcomes=[ProviderResponse(content="private answer")],
    )
    router = ModelRouter({ModelRole.LOCAL: local})

    response = await router.chat_routed(
        messages=[user_message("Analyze my medical records")],
        tools=(public_tool, private_tool),
    )

    assert response.content == "private answer"
    assert local.tool_requests == [(public_tool, private_tool)]


@pytest.mark.asyncio
async def test_sensitive_route_uses_only_local_and_fails_privately() -> None:
    cloud = FakeModelProvider(
        ModelRole.REASONING,
        cloud=True,
        outcomes=[ProviderResponse(content="must not run")],
    )
    local = FakeModelProvider(
        ModelRole.LOCAL,
        cloud=False,
        outcomes=[ProviderUnavailableError("offline"), ProviderUnavailableError("offline")],
    )
    router = ModelRouter({ModelRole.REASONING: cloud, ModelRole.LOCAL: local})
    with pytest.raises(PrivateRouteUnavailableError, match="cloud fallback is prohibited"):
        await router.chat_routed(
            messages=[user_message("Analyze my medical records")],
            tools=[],
            requested_role=ModelRole.REASONING,
        )
    assert not cloud.requests
    assert local.requests == ["none", "none"]


@pytest.mark.asyncio
async def test_reasoning_fallback_validation_stream_close_and_zero_cost() -> None:
    reasoning = FakeModelProvider(
        ModelRole.REASONING,
        cloud=True,
        outcomes=[ProviderUnavailableError("outage"), ProviderUnavailableError("outage")],
        available=False,
    )
    primary = FakeModelProvider(
        ModelRole.PRIMARY,
        cloud=True,
        outcomes=[ProviderResponse(content="reasoned")],
    )
    local = FakeModelProvider(ModelRole.LOCAL, cloud=False, outcomes=[])
    router = ModelRouter(
        {
            ModelRole.REASONING: reasoning,
            ModelRole.PRIMARY: primary,
            ModelRole.LOCAL: local,
        }
    )
    frames = [
        frame
        async for frame in router.stream_chat(
            messages=[user_message("Research public climate history")], tools=[]
        )
    ]
    assert frames[0].routing is not None
    assert frames[0].routing.chosen_role is ModelRole.PRIMARY
    assert frames[1].response is not None
    assert frames[1].response.content == "reasoned"
    assert primary.requests == ["deep"]
    assert await router.validate_models() == {
        ModelRole.REASONING: False,
        ModelRole.PRIMARY: True,
        ModelRole.LOCAL: True,
    }
    await router.close()
    assert reasoning.closed and primary.closed and local.closed

    costly = FakeModelProvider(
        ModelRole.FAST,
        cloud=True,
        outcomes=[
            ProviderResponse(
                content="paid",
                usage=ProviderUsage(
                    provider="cloud",
                    model_id="paid",
                    estimated_cost_usd=0.01,
                ),
            )
        ],
    )
    local2 = FakeModelProvider(ModelRole.LOCAL, cloud=False, outcomes=[])
    costly_router = ModelRouter({ModelRole.FAST: costly, ModelRole.LOCAL: local2})
    with pytest.raises(ZeroCostPolicyError):
        await costly_router.chat(messages=[user_message("Hello")], tools=[])


def test_router_requires_local_and_exact_zero_budget() -> None:
    with pytest.raises(ValueError, match="LOCAL"):
        ModelRouter({})
    local = FakeModelProvider(ModelRole.LOCAL, cloud=False, outcomes=[])
    with pytest.raises(ValueError, match="equal 0"):
        ModelRouter({ModelRole.LOCAL: local}, max_cloud_cost_usd=1)


@pytest.mark.asyncio
async def test_cloud_congestion_is_not_retried_and_falls_back_once() -> None:
    fast = FakeModelProvider(
        ModelRole.FAST,
        cloud=True,
        outcomes=[
            ProviderUnavailableError("congested"),
            ProviderResponse(content="must not be retried"),
        ],
    )
    local = FakeModelProvider(
        ModelRole.LOCAL,
        cloud=False,
        outcomes=[ProviderResponse(content="local fallback")],
    )
    router = ModelRouter({ModelRole.FAST: fast, ModelRole.LOCAL: local})

    response = await router.chat_routed(
        messages=[user_message("What is photosynthesis?")],
        tools=[],
        requested_role=ModelRole.FAST,
    )

    assert response.content == "local fallback"
    assert fast.requests == ["none"]
    assert local.requests == ["none"]
    assert router.health_snapshot()[ModelRole.FAST].degraded


@pytest.mark.asyncio
async def test_severely_degraded_nvidia_is_temporarily_deprioritized() -> None:
    health = ProviderHealthTracker(
        minimum_latency_samples=3,
        severe_latency_multiplier=1,
        degradation_seconds=120,
    )
    slow_usage = ProviderUsage(
        provider="cloud",
        model_id="model-reasoning",
        latency_ms=20_000,
        latency=ProviderLatencyBreakdown(
            first_visible_token_ms=20_000,
            completion_ms=21_000,
        ),
    )
    for _ in range(3):
        health.record_success("cloud:model-reasoning", slow_usage, budget_ms=7_000)
    reasoning = FakeModelProvider(
        ModelRole.REASONING,
        cloud=True,
        outcomes=[ProviderResponse(content="slow")],
    )
    primary = FakeModelProvider(
        ModelRole.PRIMARY,
        cloud=True,
        outcomes=[ProviderResponse(content="responsive")],
    )
    local = FakeModelProvider(ModelRole.LOCAL, cloud=False, outcomes=[])
    router = ModelRouter(
        {
            ModelRole.REASONING: reasoning,
            ModelRole.PRIMARY: primary,
            ModelRole.LOCAL: local,
        },
        health=health,
        latency_budgets=LatencyBudgets(deep_reasoning_ms=7_000),
    )

    response = await router.chat(
        messages=[user_message("Do complex analysis of a public algorithm")], tools=[]
    )

    assert response.content == "responsive"
    assert reasoning.requests == []
    assert primary.requests == ["deep"]
    snapshot = router.health_snapshot()[ModelRole.REASONING]
    assert snapshot.degraded
    assert snapshot.ttft_p95_ms == 20_000


@pytest.mark.asyncio
async def test_visible_provider_output_claims_response_and_disables_fallback() -> None:
    class PartialProvider(FakeModelProvider):
        async def stream_chat(self, **_kwargs: object) -> AsyncIterator[ProviderStreamFrame]:
            self.requests.append("none")
            yield ProviderStreamFrame(content_delta="Owned answer")
            raise ProviderUnavailableError("failed after speech-safe output began")

    fast = PartialProvider(ModelRole.FAST, cloud=True, outcomes=[])
    local = FakeModelProvider(
        ModelRole.LOCAL,
        cloud=False,
        outcomes=[ProviderResponse(content="competing answer")],
    )
    router = ModelRouter({ModelRole.FAST: fast, ModelRole.LOCAL: local})

    with pytest.raises(ProviderUnavailableError, match="after speech-safe output"):
        _ = [
            frame
            async for frame in router.stream_chat_routed(
                messages=[user_message("What is photosynthesis?")],
                tools=[],
                requested_role=ModelRole.FAST,
            )
        ]

    assert fast.requests == ["none"]
    assert local.requests == []
    snapshot = router.health_snapshot()[ModelRole.FAST]
    assert snapshot.failure_count == 1
    assert snapshot.error_rate == 1


def test_provider_health_records_quota_and_5xx_without_content() -> None:
    health = ProviderHealthTracker(minimum_latency_samples=3)
    health.record_failure(
        "nvidia:model",
        ProviderQuotaError("quota", status_code=429),
        budget_ms=7_000,
    )
    health.record_failure(
        "nvidia:model",
        ProviderUnavailableError("unavailable", status_code=503),
        budget_ms=7_000,
    )

    snapshot = health.snapshot("nvidia:model", budget_ms=7_000)

    assert snapshot.recent_429_count == 1
    assert snapshot.recent_5xx_count == 1
    assert snapshot.quota_limited
    assert snapshot.degraded
