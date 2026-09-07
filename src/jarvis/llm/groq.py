"""Groq adapter using its OpenAI-compatible HTTPS API."""

from __future__ import annotations

import json
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
    ProviderStreamFrame,
    ProviderUsage,
    ToolCall,
    ToolDefinition,
)

from .base import (
    ProviderAuthenticationError,
    ProviderModelUnavailableError,
    ProviderProtocolError,
    ProviderQuotaError,
    ProviderUnavailableError,
)


class GroqChatProvider:
    """Serve one configured role through Groq without embedding model IDs in core logic."""

    def __init__(
        self,
        *,
        api_key: str,
        profile: ModelProfile,
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_seconds: float = 60.0,
        max_response_bytes: int = 2_000_000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Groq API key must not be empty")
        if profile.provider != "groq" or not profile.is_cloud:
            raise ValueError("Groq profile must identify cloud provider 'groq'")
        self._profile = profile
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        self._max_response_bytes = max_response_bytes
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
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
        reasoning_level: str = "none",
    ) -> ProviderResponse:
        payload: dict[str, object] = {
            "model": self.profile.model_id,
            "messages": [_message_payload(message) for message in messages],
        }
        if tools:
            payload["tools"] = [_tool_payload(tool) for tool in tools]
            payload["tool_choice"] = "auto"
        if self.profile.model_id.startswith("qwen/"):
            payload["reasoning_effort"] = "none" if reasoning_level == "none" else "default"
        elif self.profile.model_id.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low" if reasoning_level == "none" else "medium"

        started = perf_counter()
        response = await self._request("POST", "/chat/completions", json_payload=payload)
        latency_ms = (perf_counter() - started) * 1_000
        document = _json_object(response, "Groq chat")
        choices = document.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ProviderProtocolError("Groq response has no usable choice")
        raw_message = choices[0].get("message")
        if not isinstance(raw_message, Mapping):
            raise ProviderProtocolError("Groq response choice has no message object")
        content = raw_message.get("content")
        if content is not None and not isinstance(content, str):
            raise ProviderProtocolError("Groq message content must be text or null")
        raw_calls = raw_message.get("tool_calls", [])
        if not isinstance(raw_calls, list):
            raise ProviderProtocolError("Groq message tool_calls must be a list")
        calls = tuple(_parse_tool_call(value, index) for index, value in enumerate(raw_calls))
        usage = _usage(document.get("usage"), self.profile, latency_ms, response)
        return ProviderResponse(content=content, tool_calls=calls, usage=usage)

    async def stream_chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        reasoning_level: str = "none",
    ) -> AsyncIterator[ProviderStreamFrame]:
        yield ProviderStreamFrame(
            response=await self.chat(
                messages=messages,
                tools=tools,
                reasoning_level=reasoning_level,
            )
        )

    async def validate_model(self) -> bool:
        response = await self._request("GET", "/models")
        document = _json_object(response, "Groq model catalog")
        entries = document.get("data")
        if not isinstance(entries, list):
            raise ProviderProtocolError("Groq model catalog has no data list")
        return any(
            isinstance(entry, Mapping) and entry.get("id") == self.profile.model_id
            for entry in entries
        )

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
            raise RuntimeError("GroqChatProvider is closed")
        try:
            response = await self._client.request(
                method,
                f"{self._base_url}{path}",
                json=json_payload,
                headers=self._headers,
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as exc:
            raise ProviderUnavailableError(f"Groq request failed: {type(exc).__name__}") from exc
        _raise_status(response, "Groq")
        if len(response.content) > self._max_response_bytes:
            raise ProviderProtocolError("Groq response exceeded configured byte limit")
        return response


def _message_payload(message: Message) -> dict[str, object]:
    payload: dict[str, object] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.role is MessageRole.TOOL:
        payload["tool_call_id"] = message.tool_call_id or ""
        payload.pop("role", None)
        payload["role"] = "tool"
    return payload


def _tool_payload(tool: ToolDefinition) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _parse_tool_call(raw: object, index: int) -> ToolCall:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("function"), Mapping):
        raise ProviderProtocolError(f"Groq tool call {index} is invalid")
    function = raw["function"]
    name = function.get("name")
    arguments = function.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ProviderProtocolError(f"Groq tool call {index} has invalid JSON") from exc
    if not isinstance(name, str) or not isinstance(arguments, dict):
        raise ProviderProtocolError(f"Groq tool call {index} is malformed")
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not identifier:
        identifier = f"groq-{uuid4()}"
    return ToolCall(id=identifier, name=name, arguments=arguments)


def _usage(
    raw: object, profile: ModelProfile, latency_ms: float, response: httpx.Response
) -> ProviderUsage:
    values = raw if isinstance(raw, Mapping) else {}
    remaining = response.headers.get("x-ratelimit-remaining-requests")
    try:
        parsed_remaining = int(remaining) if remaining is not None else None
    except ValueError:
        parsed_remaining = None
    return ProviderUsage(
        provider=profile.provider,
        model_id=profile.model_id,
        input_tokens=int(values.get("prompt_tokens", 0) or 0),
        output_tokens=int(values.get("completion_tokens", 0) or 0),
        latency_ms=latency_ms,
        estimated_cost_usd=0,
        rate_limit_remaining=parsed_remaining,
    )


def _json_object(response: httpx.Response, label: str) -> Mapping[str, Any]:
    try:
        value = response.json()
    except ValueError as exc:
        raise ProviderProtocolError(f"{label} returned invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise ProviderProtocolError(f"{label} must return an object")
    return value


def _raise_status(response: httpx.Response, provider: str) -> None:
    if response.is_success:
        return
    status = response.status_code
    detail = response.text.strip()[:300] or "no response detail"
    if status in {401, 403}:
        raise ProviderAuthenticationError(f"{provider} rejected credentials: {detail}")
    if status == 429:
        raise ProviderQuotaError(f"{provider} free-tier quota exhausted: {detail}")
    if status == 404:
        raise ProviderModelUnavailableError(f"{provider} model unavailable: {detail}")
    if status >= 500:
        raise ProviderUnavailableError(f"{provider} unavailable (HTTP {status}): {detail}")
    raise ProviderProtocolError(f"{provider} returned HTTP {status}: {detail}")
