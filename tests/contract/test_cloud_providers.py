from __future__ import annotations

import json

import httpx
import pytest

from jarvis.core import (
    ApprovalRule,
    Message,
    MessageRole,
    ModelCapability,
    ModelLifecycle,
    ModelProfile,
    ModelRole,
    PermissionLevel,
    ReasoningLevel,
    SensitivityClass,
    ToolConcurrency,
    ToolDefinition,
    ToolIdempotency,
    ToolRetryPolicy,
    ToolRisk,
    ToolSideEffect,
)
from jarvis.llm import (
    GeminiChatProvider,
    GroqChatProvider,
    NvidiaChatProvider,
    ProviderProtocolError,
    ProviderQuotaError,
    ProviderUnavailableError,
)


def profile(role: ModelRole, provider: str, model_id: str) -> ModelProfile:
    return ModelProfile(
        role=role,
        provider=provider,
        model_id=model_id,
        capabilities=(ModelCapability.TEXT, ModelCapability.TOOLS),
        lifecycle=ModelLifecycle.STABLE,
        context_window=131_072,
        is_cloud=True,
    )


def messages() -> list[Message]:
    return [
        Message(conversation_id="c", role=MessageRole.SYSTEM, content="Be concise."),
        Message(conversation_id="c", role=MessageRole.USER, content="Weather in Toronto?"),
    ]


def tools() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="weather",
            version="1",
            description="Get public weather.",
            input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
            permission_level=PermissionLevel.LEVEL_0,
            approval_rule=ApprovalRule.NONE,
            risk=ToolRisk.READ_ONLY,
            side_effect=ToolSideEffect.NONE,
            sensitivity=SensitivityClass.PUBLIC,
            required_capabilities=("weather.read",),
            timeout_seconds=5,
            max_result_bytes=8_192,
            max_result_items=1,
            idempotency=ToolIdempotency.SIDE_EFFECT_FREE,
            retry_policy=ToolRetryPolicy.TRANSIENT_ONLY,
            concurrency=ToolConcurrency.PARALLEL,
            postcondition="A bounded public weather result is returned.",
            recovery="No side effect occurs; retry a transient provider failure.",
        )
    ]


@pytest.mark.asyncio
async def test_groq_normalizes_tool_calls_usage_reasoning_and_catalog() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen/test"}]})
        payload = json.loads(request.content)
        expected_effort = "default" if payload.get("tools") else "none"
        assert payload["reasoning_effort"] == expected_effort
        if payload.get("tools"):
            assert payload["tools"][0]["function"]["name"] == "weather"
        return httpx.Response(
            200,
            headers={"x-ratelimit-remaining-requests": "29"},
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "weather",
                                        "arguments": '{"city":"Toronto"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GroqChatProvider(
        api_key="test",
        profile=profile(ModelRole.PRIMARY, "groq", "qwen/test"),
        client=client,
    )
    response = await provider.chat(
        messages=messages(), tools=tools(), reasoning_level=ReasoningLevel.MODERATE.value
    )
    assert response.tool_calls[0].arguments == {"city": "Toronto"}
    assert response.usage is not None
    assert response.usage.input_tokens == 10
    assert response.usage.rate_limit_remaining == 29
    assert await provider.validate_model() is True
    streamed = [frame async for frame in provider.stream_chat(messages=messages(), tools=[])]
    assert streamed[0].tool_calls
    assert all(request.headers["authorization"] == "Bearer test" for request in requests)
    await provider.close()
    await provider.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_groq_maps_quota_bad_json_and_connection_failures() -> None:
    async def quota(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="quota")

    client = httpx.AsyncClient(transport=httpx.MockTransport(quota))
    provider = GroqChatProvider(
        api_key="test",
        profile=profile(ModelRole.FAST, "groq", "openai/test"),
        client=client,
    )
    with pytest.raises(ProviderQuotaError):
        await provider.chat(messages=messages(), tools=[])
    await client.aclose()

    async def invalid(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    invalid_client = httpx.AsyncClient(transport=httpx.MockTransport(invalid))
    invalid_provider = GroqChatProvider(
        api_key="test",
        profile=profile(ModelRole.FAST, "groq", "openai/test"),
        client=invalid_client,
    )
    with pytest.raises(ProviderProtocolError, match="invalid JSON"):
        await invalid_provider.chat(messages=messages(), tools=[])
    await invalid_client.aclose()

    async def disconnected(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    down_client = httpx.AsyncClient(transport=httpx.MockTransport(disconnected))
    down_provider = GroqChatProvider(
        api_key="test",
        profile=profile(ModelRole.FAST, "groq", "openai/test"),
        client=down_client,
    )
    with pytest.raises(ProviderUnavailableError, match="ConnectError"):
        await down_provider.validate_model()
    await down_client.aclose()

    large_client = httpx.AsyncClient(transport=httpx.MockTransport(invalid))
    large_provider = GroqChatProvider(
        api_key="test",
        profile=profile(ModelRole.FAST, "groq", "openai/test"),
        client=large_client,
        max_response_bytes=2,
    )
    with pytest.raises(ProviderProtocolError, match="byte limit"):
        await large_provider.chat(messages=messages(), tools=[])
    await large_client.aclose()


@pytest.mark.asyncio
async def test_gemini_normalizes_multimodal_rest_shape_usage_and_catalog() -> None:
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"models": [{"name": "models/gemini-test"}]})
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Checking."},
                                {
                                    "functionCall": {
                                        "name": "weather",
                                        "args": {"city": "Toronto"},
                                    }
                                },
                            ]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 3},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeminiChatProvider(
        api_key="test",
        profile=profile(ModelRole.REASONING, "gemini", "gemini-test"),
        client=client,
    )
    response = await provider.chat(messages=messages(), tools=tools(), reasoning_level="deep")
    assert response.content == "Checking."
    assert response.tool_calls[0].name == "weather"
    assert response.usage is not None and response.usage.output_tokens == 3
    assert payloads[0]["systemInstruction"] == {"parts": [{"text": "Be concise."}]}
    generation = payloads[0]["generationConfig"]
    assert isinstance(generation, dict)
    assert generation["thinkingConfig"] == {"thinkingLevel": "high"}
    assert await provider.validate_model() is True
    streamed = [frame async for frame in provider.stream_chat(messages=messages(), tools=[])]
    assert streamed[0].content == "Checking."
    await provider.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_gemini_rejects_malformed_candidate() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeminiChatProvider(
        api_key="test",
        profile=profile(ModelRole.REASONING, "gemini", "gemini-test"),
        client=client,
    )
    with pytest.raises(ProviderProtocolError, match="no candidate"):
        await provider.chat(messages=messages(), tools=[])
    await client.aclose()


@pytest.mark.asyncio
async def test_nvidia_normalizes_tools_usage_thinking_and_catalog() -> None:
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={"data": [{"id": "nvidia/nemotron-3-ultra-550b-a55b"}]},
            )
        payload = json.loads(request.content)
        payloads.append(payload)
        return httpx.Response(
            200,
            headers={"x-ratelimit-remaining-requests": "9"},
            json={
                "choices": [
                    {
                        "message": {
                            "content": "private scratchpad</think>Checking.",
                            "tool_calls": [
                                {
                                    "id": "call-nv-1",
                                    "function": {
                                        "name": "weather",
                                        "arguments": '{"city":"Toronto"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = NvidiaChatProvider(
        api_key="test",
        profile=profile(
            ModelRole.REASONING,
            "nvidia",
            "nvidia/nemotron-3-ultra-550b-a55b",
        ),
        max_output_tokens=4_096,
        client=client,
    )

    response = await provider.chat(messages=messages(), tools=tools(), reasoning_level="deep")

    assert response.tool_calls[0].arguments == {"city": "Toronto"}
    assert response.content == "Checking."
    assert response.usage is not None
    assert response.usage.input_tokens == 12
    assert response.usage.rate_limit_remaining == 9
    assert payloads[0]["temperature"] == 1.0
    assert payloads[0]["top_p"] == 0.95
    assert payloads[0]["max_tokens"] == 4_096
    assert payloads[0]["chat_template_kwargs"] == {
        "enable_thinking": True,
        "force_nonempty_content": True,
    }
    assert await provider.validate_model() is True
    await provider.close()
    await provider.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_nvidia_client_rate_guard_fails_over_before_extra_request() -> None:
    request_count = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Ready."}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = NvidiaChatProvider(
        api_key="test",
        profile=profile(ModelRole.REASONING, "nvidia", "nvidia/test"),
        max_requests_per_minute=1,
        client=client,
    )

    await provider.chat(messages=messages(), tools=[])
    with pytest.raises(ProviderQuotaError, match="client-side request cap"):
        await provider.chat(messages=messages(), tools=[])

    assert request_count == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_nvidia_stream_hides_reasoning_and_reports_missing_catalog_model() -> None:
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "nvidia/other"}]})
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"x-ratelimit-remaining-requests": "unknown"},
            json={
                "choices": [{"message": {"content": "scratchpad</think>Final."}}],
                "usage": {},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = NvidiaChatProvider(
        api_key="test",
        profile=profile(ModelRole.REASONING, "nvidia", "nvidia/test"),
        client=client,
    )

    frames = [frame async for frame in provider.stream_chat(messages=messages(), tools=[])]

    assert frames[0].content == "Final."
    assert frames[0].usage is not None
    assert frames[0].usage.rate_limit_remaining is None
    assert payloads[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert await provider.validate_model() is False
    await client.aclose()


@pytest.mark.asyncio
async def test_nvidia_rejects_malformed_tool_arguments() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "weather",
                                        "arguments": "{broken",
                                    }
                                }
                            ],
                        }
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = NvidiaChatProvider(
        api_key="test",
        profile=profile(ModelRole.REASONING, "nvidia", "nvidia/test"),
        client=client,
    )

    with pytest.raises(ProviderProtocolError, match="invalid JSON"):
        await provider.chat(messages=messages(), tools=tools())

    await client.aclose()


def test_cloud_provider_constructors_reject_wrong_profiles_and_blank_keys() -> None:
    groq_profile = profile(ModelRole.FAST, "groq", "model")
    gemini_profile = profile(ModelRole.REASONING, "gemini", "model")
    with pytest.raises(ValueError, match="key"):
        GroqChatProvider(api_key=" ", profile=groq_profile)
    with pytest.raises(ValueError, match="profile"):
        GroqChatProvider(api_key="x", profile=gemini_profile)
    with pytest.raises(ValueError, match="key"):
        GeminiChatProvider(api_key=" ", profile=gemini_profile)
    with pytest.raises(ValueError, match="profile"):
        GeminiChatProvider(api_key="x", profile=groq_profile)
    with pytest.raises(ValueError, match="max_response_bytes"):
        GroqChatProvider(api_key="x", profile=groq_profile, max_response_bytes=0)
    nvidia_profile = profile(ModelRole.REASONING, "nvidia", "nvidia/model")
    with pytest.raises(ValueError, match="key"):
        NvidiaChatProvider(api_key=" ", profile=nvidia_profile)
    with pytest.raises(ValueError, match="profile"):
        NvidiaChatProvider(api_key="x", profile=groq_profile)
    with pytest.raises(ValueError, match="max_output_tokens"):
        NvidiaChatProvider(api_key="x", profile=nvidia_profile, max_output_tokens=32_769)
    with pytest.raises(ValueError, match="max_response_bytes"):
        NvidiaChatProvider(api_key="x", profile=nvidia_profile, max_response_bytes=0)
    with pytest.raises(ValueError, match="max_requests_per_minute"):
        NvidiaChatProvider(api_key="x", profile=nvidia_profile, max_requests_per_minute=0)
    with pytest.raises(ValueError, match="max_concurrency"):
        NvidiaChatProvider(api_key="x", profile=nvidia_profile, max_concurrency=0)
