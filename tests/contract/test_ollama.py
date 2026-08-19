from __future__ import annotations

import json

import httpx
import pytest
import respx

from jarvis.core.models import Message, MessageRole, ToolDefinition
from jarvis.llm.ollama import (
    OllamaChatProvider,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaProtocolError,
    OllamaTimeoutError,
)

BASE_URL = "http://127.0.0.1:11434"


@respx.mock
async def test_chat_normalizes_messages_tools_and_tool_calls() -> None:
    route = respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "test-model",
                "done": True,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "weather", "arguments": '{"city":"Toronto"}'}}
                    ],
                },
            },
        )
    )
    provider = OllamaChatProvider(model="test-model")
    response = await provider.chat(
        messages=[
            Message(
                conversation_id="conversation-1",
                role=MessageRole.USER,
                content="Weather?",
            )
        ],
        tools=[
            ToolDefinition(
                name="weather",
                description="Read the weather",
                input_schema={
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            )
        ],
    )
    await provider.close()
    await provider.close()

    assert response.content == ""
    assert response.tool_calls[0].name == "weather"
    assert response.tool_calls[0].arguments == {"city": "Toronto"}
    assert response.tool_calls[0].id.startswith("ollama-")
    request_payload = json.loads(route.calls.last.request.content)
    assert request_payload == {
        "model": "test-model",
        "stream": False,
        "messages": [{"role": "user", "content": "Weather?"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Read the weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ],
    }


@respx.mock
async def test_chat_normalizes_assistant_tool_calls_and_tool_results() -> None:
    route = respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "complete"}},
        )
    )
    provider = OllamaChatProvider(model="test-model")
    await provider.chat(
        messages=[
            Message(
                conversation_id="conversation-1",
                role=MessageRole.ASSISTANT,
                tool_calls=(
                    {
                        "id": "call-1",
                        "name": "weather",
                        "arguments": {"city": "Toronto"},
                    },
                ),
            ),
            Message(
                conversation_id="conversation-1",
                role=MessageRole.TOOL,
                content='{"temperature":20}',
                tool_call_id="call-1",
                tool_name="weather",
            ),
        ],
        tools=[],
    )
    payload = json.loads(route.calls.last.request.content)
    assert payload["messages"] == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "weather", "arguments": {"city": "Toronto"}}}],
        },
        {"role": "tool", "content": '{"temperature":20}', "tool_name": "weather"},
    ]
    assert "tools" not in payload
    await provider.close()


@respx.mock
async def test_model_diagnostics_lists_models_without_downloading() -> None:
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "z-model"}, {"model": "test-model"}]},
        )
    )
    provider = OllamaChatProvider(model="test-model")
    diagnostics = await provider.model_diagnostics()
    await provider.close()

    assert diagnostics.available
    assert diagnostics.installed_models == ("test-model", "z-model")
    assert all(call.request.url.path != "/api/pull" for call in respx.calls)


@respx.mock
async def test_missing_model_reports_installed_models_and_never_pulls() -> None:
    respx.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(404, json={"error": "model not found"})
    )
    respx.get(f"{BASE_URL}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "other:latest"}]})
    )
    provider = OllamaChatProvider(model="missing:latest")

    with pytest.raises(OllamaModelNotFoundError, match="will not download") as error:
        await provider.chat(
            messages=[
                Message(
                    conversation_id="conversation-1",
                    role=MessageRole.USER,
                    content="hello",
                )
            ],
            tools=[],
        )
    await provider.close()

    assert error.value.installed_models == ("other:latest",)
    assert all(call.request.url.path != "/api/pull" for call in respx.calls)


@pytest.mark.parametrize(
    ("exception", "expected_type", "match"),
    [
        (
            httpx.ReadTimeout("slow"),
            OllamaTimeoutError,
            "timed out",
        ),
        (
            httpx.ConnectError("refused"),
            OllamaConnectionError,
            "Cannot connect",
        ),
    ],
)
@respx.mock
async def test_transport_errors_are_clear(
    exception: httpx.RequestError,
    expected_type: type[Exception],
    match: str,
) -> None:
    respx.post(f"{BASE_URL}/api/chat").mock(side_effect=exception)
    provider = OllamaChatProvider(model="test-model")
    with pytest.raises(expected_type, match=match):
        await provider.chat(
            messages=[
                Message(
                    conversation_id="conversation-1",
                    role=MessageRole.USER,
                    content="hello",
                )
            ],
            tools=[],
        )
    await provider.close()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error": "server failed"}),
        httpx.Response(200, content=b"{", headers={"content-type": "application/json"}),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"message": {"content": 7}}),
        httpx.Response(200, json={"message": {"content": "", "tool_calls": "bad"}}),
        httpx.Response(200, json={"message": {"content": ""}}),
        httpx.Response(
            200,
            json={"message": {"content": "", "tool_calls": [{"function": {}}]}},
        ),
    ],
)
@respx.mock
async def test_protocol_errors_are_clear(response: httpx.Response) -> None:
    respx.post(f"{BASE_URL}/api/chat").mock(return_value=response)
    provider = OllamaChatProvider(model="test-model")
    with pytest.raises(OllamaProtocolError):
        await provider.chat(
            messages=[
                Message(
                    conversation_id="conversation-1",
                    role=MessageRole.USER,
                    content="hello",
                )
            ],
            tools=[],
        )
    await provider.close()


def test_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="base_url"):
        OllamaChatProvider(base_url="", model="test")
    with pytest.raises(ValueError, match="model"):
        OllamaChatProvider(model=" ")
    with pytest.raises(ValueError, match="timeout_seconds"):
        OllamaChatProvider(model="test", timeout_seconds=0)
