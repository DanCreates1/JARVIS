"""Async Ollama chat provider with explicit local-model diagnostics."""

from __future__ import annotations

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
    """Send non-streaming chat requests to an existing Ollama installation."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str,
        timeout_seconds: float = 60.0,
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

        self._base_url = normalized_base_url
        self._model = model.strip()
        self._profile = ModelProfile(
            role=role,
            provider="ollama",
            model_id=self._model,
            capabilities=(ModelCapability.TEXT, ModelCapability.TOOLS),
            lifecycle=ModelLifecycle.LOCAL,
            context_window=32_768,
            is_cloud=False,
        )
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
        """Return one complete assistant response from Ollama's ``/api/chat`` endpoint."""
        payload: dict[str, object] = {
            "model": self._model,
            "stream": False,
            "think": reasoning_level != "none",
            "messages": [_message_payload(message) for message in messages],
        }
        if tools:
            payload["tools"] = [_tool_payload(tool) for tool in tools]

        response = await self._request("POST", "/api/chat", json_payload=payload)
        if response.status_code == httpx.codes.NOT_FOUND:
            diagnostics = await self._diagnostics_after_missing_model()
            raise OllamaModelNotFoundError(self._model, diagnostics.installed_models)
        self._raise_for_status(response)
        document = _response_json(response, endpoint="/api/chat")

        message = document.get("message")
        if not isinstance(message, Mapping):
            raise OllamaProtocolError("Ollama /api/chat response is missing a message object")

        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise OllamaProtocolError("Ollama message content must be a string or null")

        raw_tool_calls = message.get("tool_calls", [])
        if not isinstance(raw_tool_calls, list):
            raise OllamaProtocolError("Ollama message tool_calls must be a list")
        tool_calls = tuple(
            _parse_tool_call(raw_tool_call, position=position)
            for position, raw_tool_call in enumerate(raw_tool_calls)
        )
        if (content is None or not content.strip()) and not tool_calls:
            raise OllamaProtocolError(
                "Ollama assistant message must contain text or at least one tool call"
            )
        usage = ProviderUsage(
            provider="ollama",
            model_id=self._model,
            input_tokens=int(document.get("prompt_eval_count", 0) or 0),
            output_tokens=int(document.get("eval_count", 0) or 0),
            latency_ms=float(document.get("total_duration", 0) or 0) / 1_000_000,
            estimated_cost_usd=0,
        )
        return ProviderResponse(content=content, tool_calls=tool_calls, usage=usage)

    async def stream_chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        reasoning_level: str = "none",
    ) -> AsyncIterator[ProviderResponse]:
        """Expose the provider-neutral stream contract; one normalized frame for now."""
        yield await self.chat(
            messages=messages,
            tools=tools,
            reasoning_level=reasoning_level,
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


def _error_detail(response: httpx.Response) -> str:
    try:
        document = response.json()
    except ValueError:
        document = None
    error = document.get("error") if isinstance(document, Mapping) else None
    detail = error if isinstance(error, str) else response.text.strip() or "no response detail"
    return detail[:300]
