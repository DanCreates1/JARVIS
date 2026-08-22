"""NVIDIA API Catalog adapter using its OpenAI-compatible HTTPS API."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator, Mapping, Sequence
from time import monotonic, perf_counter
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

from .base import (
    ProviderProtocolError,
    ProviderQuotaError,
    ProviderUnavailableError,
)
from .groq import _raise_status


class NvidiaChatProvider:
    """Serve difficult public work through NVIDIA's hosted NIM endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        profile: ModelProfile,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_seconds: float = 120.0,
        max_response_bytes: int = 2_000_000,
        max_output_tokens: int = 4_096,
        max_requests_per_minute: int = 30,
        max_concurrency: int = 1,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("NVIDIA API key must not be empty")
        if profile.provider != "nvidia" or not profile.is_cloud:
            raise ValueError("NVIDIA profile must identify cloud provider 'nvidia'")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        if not 1 <= max_output_tokens <= 32_768:
            raise ValueError("max_output_tokens must be between 1 and 32768")
        if max_requests_per_minute < 1:
            raise ValueError("max_requests_per_minute must be positive")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        self._profile = profile
        self._base_url = base_url.rstrip("/")
        self._max_response_bytes = max_response_bytes
        self._max_output_tokens = max_output_tokens
        self._max_requests_per_minute = max_requests_per_minute
        self._request_times: deque[float] = deque()
        self._rate_lock = asyncio.Lock()
        self._concurrency = asyncio.Semaphore(max_concurrency)
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
        enable_thinking = reasoning_level != "none"
        chat_template_kwargs: dict[str, object] = {"enable_thinking": enable_thinking}
        payload: dict[str, object] = {
            "model": self.profile.model_id,
            "messages": [_message_payload(message) for message in messages],
            "temperature": 1.0,
            "top_p": 0.95,
            "max_tokens": self._max_output_tokens,
            "chat_template_kwargs": chat_template_kwargs,
        }
        if tools:
            payload["tools"] = [_tool_payload(tool) for tool in tools]
            payload["tool_choice"] = "auto"
            chat_template_kwargs["force_nonempty_content"] = True

        started = perf_counter()
        response = await self._request("POST", "/chat/completions", json_payload=payload)
        latency_ms = (perf_counter() - started) * 1_000
        document = _json_object(response, "NVIDIA chat")
        choices = document.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ProviderProtocolError("NVIDIA response has no usable choice")
        raw_message = choices[0].get("message")
        if not isinstance(raw_message, Mapping):
            raise ProviderProtocolError("NVIDIA response choice has no message object")
        raw_content = raw_message.get("content")
        if raw_content is not None and not isinstance(raw_content, str):
            raise ProviderProtocolError("NVIDIA message content must be text or null")
        content = _final_content(raw_content)
        raw_calls = raw_message.get("tool_calls", [])
        if not isinstance(raw_calls, list):
            raise ProviderProtocolError("NVIDIA message tool_calls must be a list")
        calls = tuple(_parse_tool_call(value, index) for index, value in enumerate(raw_calls))
        usage = _usage(document.get("usage"), self.profile, latency_ms, response)
        return ProviderResponse(content=content, tool_calls=calls, usage=usage)

    async def stream_chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        reasoning_level: str = "none",
    ) -> AsyncIterator[ProviderResponse]:
        yield await self.chat(messages=messages, tools=tools, reasoning_level=reasoning_level)

    async def validate_model(self) -> bool:
        response = await self._request("GET", "/models")
        document = _json_object(response, "NVIDIA model catalog")
        entries = document.get("data")
        if not isinstance(entries, list):
            raise ProviderProtocolError("NVIDIA model catalog has no data list")
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
            raise RuntimeError("NvidiaChatProvider is closed")
        await self._claim_rate_slot()
        try:
            async with self._concurrency:
                response = await self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json_payload,
                    headers=self._headers,
                )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as exc:
            raise ProviderUnavailableError(f"NVIDIA request failed: {type(exc).__name__}") from exc
        _raise_status(response, "NVIDIA")
        if len(response.content) > self._max_response_bytes:
            raise ProviderProtocolError("NVIDIA response exceeded configured byte limit")
        return response

    async def _claim_rate_slot(self) -> None:
        now = monotonic()
        async with self._rate_lock:
            while self._request_times and now - self._request_times[0] >= 60:
                self._request_times.popleft()
            if len(self._request_times) >= self._max_requests_per_minute:
                raise ProviderQuotaError(
                    "NVIDIA client-side request cap reached; use local fallback and retry later"
                )
            self._request_times.append(now)


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
        payload["name"] = message.tool_name or ""
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
        raise ProviderProtocolError(f"NVIDIA tool call {index} is invalid")
    function = raw["function"]
    name = function.get("name")
    arguments = function.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ProviderProtocolError(f"NVIDIA tool call {index} has invalid JSON") from exc
    if not isinstance(name, str) or not isinstance(arguments, dict):
        raise ProviderProtocolError(f"NVIDIA tool call {index} is malformed")
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not identifier:
        identifier = f"nvidia-{uuid4()}"
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


def _final_content(content: str | None) -> str | None:
    """Discard Nemotron scratchpad text; never persist or display hidden reasoning."""
    if content is None:
        return None
    if "</think>" in content:
        content = content.rsplit("</think>", 1)[1]
    return content.strip() or None
