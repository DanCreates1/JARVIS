from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator, Iterable, Sequence
from pathlib import Path

import pytest

from jarvis.core import (
    Message,
    MessageRole,
    ModelCapability,
    ModelLifecycle,
    ModelProfile,
    ModelRole,
    ProviderResponse,
    ProviderUsage,
    ReasoningLevel,
    SensitivityClass,
    ToolCall,
    ToolDefinition,
)
from jarvis.llm import (
    ModelRouter,
    PrivacyGate,
    PrivateRouteUnavailableError,
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
    ) -> AsyncIterator[ProviderResponse]:
        yield await self.chat(messages=messages, tools=tools, reasoning_level=reasoning_level)

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
    assert policy.decide("Hello").chosen_role is ModelRole.FAST
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

    response = await router.chat(
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

    response = await router.chat(
        messages=[public_assistant, user_message("What is the largest planet?")],
        tools=[],
    )
    assert response.content == "cloud answer"
    assert len(cloud.requests) == 1

    private_assistant = public_assistant.model_copy(
        update={"content": "My password is synthetic-secret."}
    )
    response = await router.chat(
        messages=[private_assistant, user_message("What is the largest planet?")],
        tools=[],
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
        messages=[user_message("Public information " * 20)],
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
        messages=[user_message("Public information " * 20)],
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
    assert frames[0].content == "reasoned"
    assert frames[0].routing is not None
    assert frames[0].routing.chosen_role is ModelRole.PRIMARY
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
