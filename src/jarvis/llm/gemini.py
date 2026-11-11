"""Google Gemini adapter using the official REST surface."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx

from jarvis.core.models import (
    Message,
    MessageRole,
    ModelProfile,
    ProviderResponse,
    ProviderUsage,
    ToolCall,
    ToolDefinition,
)

from .base import ProviderProtocolError, ProviderUnavailableError
from .groq import _raise_status


class GeminiChatProvider:
    """Serve the reasoning role through Gemini with normalized messages and usage."""

    def __init__(
        self,
        *,
        api_key: str,
        profile: ModelProfile,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 60.0,
        max_response_bytes: int = 2_000_000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Gemini API key must not be empty")
        if profile.provider != "gemini" or not profile.is_cloud:
            raise ValueError("Gemini profile must identify cloud provider 'gemini'")
        self._profile = profile
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        self._max_response_bytes = max_response_bytes
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._closed = False

    @property
    def profile(self) -> ModelProfile:
        return self._profile

    async def chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        reasoning_level: str = "deep",
    ) -> ProviderResponse:
        system_parts = [
            message.content for message in messages if message.role is MessageRole.SYSTEM
        ]
        payload: dict[str, object] = {
            "contents": [
                value
                for message in messages
                if message.role is not MessageRole.SYSTEM
                for value in [_message_payload(message)]
            ],
            "generationConfig": {
                "thinkingConfig": {"thinkingLevel": _thinking_level(reasoning_level)}
            },
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parametersJsonSchema": tool.input_schema,
                        }
                        for tool in tools
                    ]
                }
            ]

        started = perf_counter()
        path = f"/models/{self.profile.model_id}:generateContent"
        response = await self._request("POST", path, json_payload=payload)
        latency_ms = (perf_counter() - started) * 1_000
        document = _json_object(response, "Gemini chat")
        candidates = document.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ProviderProtocolError("Gemini response has no candidate")
        candidate = candidates[0]
        if not isinstance(candidate, Mapping) or not isinstance(candidate.get("content"), Mapping):
            raise ProviderProtocolError("Gemini candidate has no content")
        parts = candidate["content"].get("parts")
        if not isinstance(parts, list):
            raise ProviderProtocolError("Gemini candidate has no parts list")
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for index, part in enumerate(parts):
            if not isinstance(part, Mapping):
                continue
            text = part.get("text")
            if isinstance(text, str) and text:
                text_parts.append(text)
            function_call = part.get("functionCall")
            if isinstance(function_call, Mapping):
                name = function_call.get("name")
                arguments = function_call.get("args", {})
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    raise ProviderProtocolError(f"Gemini function call {index} is malformed")
                calls.append(ToolCall(id=f"gemini-{uuid4()}", name=name, arguments=arguments))
        usage_raw = document.get("usageMetadata")
        usage_values = usage_raw if isinstance(usage_raw, Mapping) else {}
        usage = ProviderUsage(
            provider=self.profile.provider,
            model_id=self.profile.model_id,
            input_tokens=int(usage_values.get("promptTokenCount", 0) or 0),
            output_tokens=int(usage_values.get("candidatesTokenCount", 0) or 0),
            latency_ms=latency_ms,
            estimated_cost_usd=0,
        )
        return ProviderResponse(
            content="".join(text_parts) or None,
            tool_calls=tuple(calls),
            usage=usage,
        )

    async def stream_chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        reasoning_level: str = "deep",
    ) -> AsyncIterator[ProviderResponse]:
        yield await self.chat(messages=messages, tools=tools, reasoning_level=reasoning_level)

    async def validate_model(self) -> bool:
        response = await self._request("GET", "/models")
        document = _json_object(response, "Gemini model catalog")
        models = document.get("models")
        if not isinstance(models, list):
            raise ProviderProtocolError("Gemini model catalog has no models list")
        expected = f"models/{self.profile.model_id}"
        return any(isinstance(model, Mapping) and model.get("name") == expected for model in models)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self, method: str, path: str, *, json_payload: object | None = None
    ) -> httpx.Response:
        if self._closed:
            raise RuntimeError("GeminiChatProvider is closed")
        try:
            response = await self._client.request(
                method,
                f"{self._base_url}{path}",
                json=json_payload,
                headers=self._headers,
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as exc:
            raise ProviderUnavailableError(f"Gemini request failed: {type(exc).__name__}") from exc
        _raise_status(response, "Gemini")
        if len(response.content) > self._max_response_bytes:
            raise ProviderProtocolError("Gemini response exceeded configured byte limit")
        return response


def _message_payload(message: Message) -> dict[str, object]:
    role = "model" if message.role is MessageRole.ASSISTANT else "user"
    parts: list[dict[str, object]] = []
    if message.content:
        if message.role is MessageRole.TOOL:
            parts.append(
                {
                    "functionResponse": {
                        "name": message.tool_name,
                        "response": {"result": message.content},
                    }
                }
            )
        else:
            parts.append({"text": message.content})
    parts.extend(
        {"functionCall": {"name": call.name, "args": call.arguments}} for call in message.tool_calls
    )
    return {"role": role, "parts": parts}


def _thinking_level(level: str) -> str:
    return {"none": "minimal", "moderate": "medium", "deep": "high"}.get(level, "high")


def _json_object(response: httpx.Response, label: str) -> Mapping[str, Any]:
    try:
        value = response.json()
    except ValueError as exc:
        raise ProviderProtocolError(f"{label} returned invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise ProviderProtocolError(f"{label} must return an object")
    return value
