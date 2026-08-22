"""Provider-neutral model contracts and normalized provider failures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, runtime_checkable

from jarvis.core.models import Message, ModelProfile, ProviderResponse, ToolDefinition


class ProviderError(RuntimeError):
    """Base class for model-provider failures safe for router classification."""


class ProviderUnavailableError(ProviderError):
    """Provider cannot currently serve the request."""


class ProviderQuotaError(ProviderUnavailableError):
    """Free-tier rate or quota capacity is exhausted."""


class ProviderModelUnavailableError(ProviderUnavailableError):
    """Configured model is missing, retired, or inaccessible."""


class ProviderAuthenticationError(ProviderError):
    """Credential is missing or rejected."""


class ProviderProtocolError(ProviderError):
    """Provider response cannot be normalized safely."""


class PrivateRouteUnavailableError(ProviderUnavailableError):
    """Sensitive work cannot run locally and must not be disclosed to cloud."""


class ZeroCostPolicyError(ProviderError):
    """A response would violate the hard zero-dollar cloud budget."""


@runtime_checkable
class ModelProvider(Protocol):
    @property
    def profile(self) -> ModelProfile: ...

    async def chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        reasoning_level: str = "none",
    ) -> ProviderResponse: ...

    def stream_chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        reasoning_level: str = "none",
    ) -> AsyncIterator[ProviderResponse]: ...

    async def validate_model(self) -> bool: ...

    async def close(self) -> None: ...
