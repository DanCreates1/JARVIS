"""Async Ollama chat provider with explicit local-model diagnostics."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from jarvis.core.models import (
    Message,
    ModelCapability,
    ModelLifecycle,
    ModelProfile,
    ModelRole,
    ProviderResponse,
    ProviderStreamFrame,
    ProviderUsage,
    ToolCall,
    ToolDefinition,
)


class OllamaError(RuntimeError):
    """Base error for failures reported by the Ollama adapter."""


class OllamaConnectionError(OllamaError):
    """The configured Ollama service could not be reached."""


class OllamaTimeoutError(OllamaError):
    """The configured Ollama service exceeded the request deadline."""


class OllamaProtocolError(OllamaError):
    """Ollama returned an HTTP or JSON response that could not be used safely."""


class OllamaModelNotFoundError(OllamaProtocolError):
    """The configured model is not installed in Ollama."""

    def __init__(self, model: str, installed_models: Sequence[str]) -> None:
        self.model = model
        self.installed_models = tuple(installed_models)
        installed = ", ".join(self.installed_models) or "none"
        super().__init__(
            f"Ollama model {model!r} is not installed (installed models: {installed}). "
            f"Install it explicitly with `ollama pull {model}`; JARVIS will not download "
            "models automatically."
        )


@dataclass(frozen=True, slots=True)
class OllamaModelDiagnostics:
    """Availability information read from Ollama's ``/api/tags`` endpoint."""

    configured_model: str
    installed_models: tuple[str, ...]

    @property
    def available(self) -> bool:
        return self.configured_model in self.installed_models


class OllamaChatProvider:
    """Send bounded streaming chat requests to an existing Ollama installation."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str,
        timeout_seconds: float = 60.0,
        max_response_bytes: int = 2_000_000,
        context_tokens: int = 4_096,
        max_output_tokens: int = 512,
        keep_alive: str = "5m",
        role: ModelRole = ModelRole.LOCAL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized_base_url = base_url.rstrip("/")
        if not normalized_base_url:
            raise ValueError("base_url must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        if context_tokens < 512:
            raise ValueError("context_tokens must be at least 512")
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        if not keep_alive.strip():
            raise ValueError("keep_alive must not be empty")

        self._base_url = normalized_base_url
        self._timeout_seconds = timeout_seconds
        self._model = model.strip()
        self._profile = ModelProfile(
            role=role,
            provider="ollama",
            model_id=self._model,
            capabilities=(ModelCapability.TEXT, ModelCapability.TOOLS),
            lifecycle=ModelLifecycle.LOCAL,
            context_window=context_tokens,
            max_output_tokens=max_output_tokens,
            is_cloud=False,
        )
        self._max_response_bytes = max_response_bytes
        self._context_tokens = context_tokens
        self._max_output_tokens = max_output_tokens
        self._keep_alive = keep_alive.strip()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._closed = False

    @property
    def model(self) -> str:
        return self._model

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
        """Consume the token stream and return its one terminal response."""
        terminal: ProviderResponse | None = None
        async for frame in self.stream_chat(
            messages=messages,
            tools=tools,
            reasoning_level=reasoning_level,
        ):
            if frame.response is not None:
                terminal = frame.response
        if terminal is None:
            raise OllamaProtocolError("Ollama stream ended without a terminal response")
        return terminal

    async def stream_chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        reasoning_level: str = "none",
    ) -> AsyncIterator[ProviderStreamFrame]:
        """Yield genuine Ollama NDJSON text deltas and one terminal response."""
        payload: dict[str, object] = {
            "model": self._model,
            "stream": True,
            "think": reasoning_level != "none",
            "keep_alive": self._keep_alive,
            "options": {
                "num_ctx": self._context_tokens,
                "num_predict": self._max_output_tokens,
            },
            "messages": [_message_payload(message) for message in messages],
        }
        if tools:
            payload["tools"] = [_tool_payload(tool) for tool in tools]

        if self._closed:
            raise RuntimeError("OllamaChatProvider is closed")
        url = f"{self._base_url}/api/chat"
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._client.stream("POST", url, json=payload) as response:
                    async for frame in self._consume_stream(response):
                        yield frame
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise OllamaTimeoutError(
                f"Ollama request timed out at {self._base_url}; verify the service and model"
            ) from exc
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self._base_url}; start Ollama or correct the URL"
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaConnectionError(
                f"Ollama request failed at {self._base_url}: {exc.__class__.__name__}"
            ) from exc

    async def _consume_stream(self, response: httpx.Response) -> AsyncIterator[ProviderStreamFrame]:
        if response.status_code == httpx.codes.NOT_FOUND:
            await response.aread()
            diagnostics = await self._diagnostics_after_missing_model()
            raise OllamaModelNotFoundError(self._model, diagnostics.installed_models)
        if not response.is_success:
            await response.aread()
            self._raise_for_status(response)

        received_bytes = 0
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        final_document: Mapping[str, Any] | None = None
        async for line in response.aiter_lines():
            received_bytes += len(line.encode("utf-8")) + 1
            if received_bytes > self._max_response_bytes:
                raise OllamaProtocolError(
                    "Ollama streaming response exceeded configured byte limit"
                )
            if not line.strip():
                continue
            document = _line_json(line)
            message = document.get("message")
            if not isinstance(message, Mapping):
                raise OllamaProtocolError("Ollama stream frame is missing a message object")
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise OllamaProtocolError("Ollama stream message content must be a string or null")
            if content:
                content_parts.append(content)
                yield ProviderStreamFrame(content_delta=content)
            raw_calls = message.get("tool_calls", [])
            if not isinstance(raw_calls, list):
                raise OllamaProtocolError("Ollama stream message tool_calls must be a list")
            tool_calls.extend(
                _parse_tool_call(raw_call, position=len(tool_calls) + position)
                for position, raw_call in enumerate(raw_calls)
            )
            if document.get("done") is True:
                final_document = document
        if final_document is None:
            raise OllamaProtocolError("Ollama stream ended without a done frame")
        assembled_content = "".join(content_parts)
        if not assembled_content.strip() and not tool_calls:
            raise OllamaProtocolError(
                "Ollama assistant stream must contain text or at least one tool call"
            )
        usage = ProviderUsage(
            provider="ollama",
            model_id=self._model,
            input_tokens=int(final_document.get("prompt_eval_count", 0) or 0),
            output_tokens=int(final_document.get("eval_count", 0) or 0),
            latency_ms=float(final_document.get("total_duration", 0) or 0) / 1_000_000,
            estimated_cost_usd=0,
        )
        yield ProviderStreamFrame(
            response=ProviderResponse(
                content=assembled_content,
                tool_calls=tuple(tool_calls),
                usage=usage,
            )
        )

    async def validate_model(self) -> bool:
        return (await self.model_diagnostics()).available

    async def model_diagnostics(self) -> OllamaModelDiagnostics:
        """List installed models without downloading or changing Ollama state."""
        response = await self._request("GET", "/api/tags")
        self._raise_for_status(response)
        document = _response_json(response, endpoint="/api/tags")
        raw_models = document.get("models")
        if not isinstance(raw_models, list):
            raise OllamaProtocolError("Ollama /api/tags response is missing a models list")

        names: set[str] = set()
        for raw_model in raw_models:
            if not isinstance(raw_model, Mapping):
                raise OllamaProtocolError("Ollama /api/tags returned a non-object model entry")
            name = raw_model.get("name") or raw_model.get("model")
            if not isinstance(name, str) or not name:
                raise OllamaProtocolError("Ollama /api/tags returned a model without a name")
            names.add(name)
        return OllamaModelDiagnostics(
            configured_model=self._model,
            installed_models=tuple(sorted(names)),
        )

    async def close(self) -> None:
        """Close the internally owned HTTP client; repeated calls are harmless."""
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> OllamaChatProvider:
        if self._closed:
            raise RuntimeError("OllamaChatProvider is closed")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: object | None = None,
    ) -> httpx.Response:
        if self._closed:
            raise RuntimeError("OllamaChatProvider is closed")
        url = f"{self._base_url}{path}"
        try:
            return await self._client.request(method, url, json=json_payload)
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Ollama request timed out at {self._base_url}; verify the service and model"
            ) from exc
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self._base_url}; start Ollama or correct the URL"
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaConnectionError(
                f"Ollama request failed at {self._base_url}: {exc.__class__.__name__}"
            ) from exc

    async def _diagnostics_after_missing_model(self) -> OllamaModelDiagnostics:
        try:
            return await self.model_diagnostics()
        except OllamaError:
            return OllamaModelDiagnostics(
                configured_model=self._model,
                installed_models=(),
            )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = _error_detail(response)
        raise OllamaProtocolError(
            f"Ollama returned HTTP {response.status_code} for {response.request.url.path}: {detail}"
        )


def _message_payload(message: Message) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": message.role.value,
        "content": message.content,
    }
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "function": {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                }
            }
            for tool_call in message.tool_calls
        ]
    if message.tool_name is not None:
        payload["tool_name"] = message.tool_name
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


def _parse_tool_call(raw_tool_call: object, *, position: int) -> ToolCall:
    if not isinstance(raw_tool_call, Mapping):
        raise OllamaProtocolError(f"Ollama tool call {position} is not an object")
    function = raw_tool_call.get("function")
    if not isinstance(function, Mapping):
        raise OllamaProtocolError(f"Ollama tool call {position} has no function object")

    name = function.get("name")
    if not isinstance(name, str) or not name:
        raise OllamaProtocolError(f"Ollama tool call {position} has no function name")
    arguments = function.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise OllamaProtocolError(
                f"Ollama tool call {position} arguments are not valid JSON"
            ) from exc
    if not isinstance(arguments, dict):
        raise OllamaProtocolError(f"Ollama tool call {position} arguments must be an object")

    identifier = raw_tool_call.get("id")
    if not isinstance(identifier, str) or not identifier:
        identifier = f"ollama-{uuid4()}"
    return ToolCall(id=identifier, name=name, arguments=arguments)


def _response_json(response: httpx.Response, *, endpoint: str) -> Mapping[str, Any]:
    try:
        document = response.json()
    except ValueError as exc:
        raise OllamaProtocolError(f"Ollama {endpoint} returned invalid JSON") from exc
    if not isinstance(document, Mapping):
        raise OllamaProtocolError(f"Ollama {endpoint} response must be a JSON object")
    return document


def _line_json(line: str) -> Mapping[str, Any]:
    try:
        document = json.loads(line)
    except ValueError as exc:
        raise OllamaProtocolError("Ollama stream returned invalid JSON") from exc
    if not isinstance(document, Mapping):
        raise OllamaProtocolError("Ollama stream frame must be a JSON object")
    return document


def _error_detail(response: httpx.Response) -> str:
    try:
        document = response.json()
    except ValueError:
        document = None
    error = document.get("error") if isinstance(document, Mapping) else None
    detail = error if isinstance(error, str) else response.text.strip() or "no response detail"
    return detail[:300]
