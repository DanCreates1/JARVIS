"""Language-model provider adapters."""

from jarvis.llm.base import (
    ModelProvider,
    PrivateRouteUnavailableError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderModelUnavailableError,
    ProviderProtocolError,
    ProviderQuotaError,
    ProviderUnavailableError,
    ZeroCostPolicyError,
)
from jarvis.llm.gemini import GeminiChatProvider
from jarvis.llm.groq import GroqChatProvider
from jarvis.llm.health import LatencyBudgets, ProviderHealthSnapshot, ProviderHealthTracker
from jarvis.llm.nvidia import NvidiaChatProvider
from jarvis.llm.ollama import (
    OllamaChatProvider,
    OllamaConnectionError,
    OllamaError,
    OllamaModelDiagnostics,
    OllamaModelNotFoundError,
    OllamaProtocolError,
    OllamaTimeoutError,
)
from jarvis.llm.routing import ModelRouter, PrivacyGate, RoutingPolicy

__all__ = [
    "GeminiChatProvider",
    "GroqChatProvider",
    "LatencyBudgets",
    "ModelProvider",
    "ModelRouter",
    "NvidiaChatProvider",
    "OllamaChatProvider",
    "OllamaConnectionError",
    "OllamaError",
    "OllamaModelDiagnostics",
    "OllamaModelNotFoundError",
    "OllamaProtocolError",
    "OllamaTimeoutError",
    "PrivacyGate",
    "PrivateRouteUnavailableError",
    "ProviderAuthenticationError",
    "ProviderError",
    "ProviderHealthSnapshot",
    "ProviderHealthTracker",
    "ProviderModelUnavailableError",
    "ProviderProtocolError",
    "ProviderQuotaError",
    "ProviderUnavailableError",
    "RoutingPolicy",
    "ZeroCostPolicyError",
]
