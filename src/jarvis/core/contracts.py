"""Async ports implemented by provider, persistence, tool, and policy adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, JsonValue

from .models import (
    ContextProjection,
    Conversation,
    Message,
    ModelRole,
    PolicyDecision,
    ProviderResponse,
    ReasoningLevel,
    SensitivityClass,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


@runtime_checkable
class SensitivityClassifier(Protocol):
    def classify(self, text: str) -> SensitivityClass:
        """Classify text locally before it can cross a provider boundary."""
        ...


@runtime_checkable
class ChatProvider(Protocol):
    async def chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> ProviderResponse:
        """Return one normalized chat response.

        Provider output remains untrusted: ``AssistantService`` validates it again.
        """
        ...


@runtime_checkable
class RoutedChatProvider(Protocol):
    async def chat_routed(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
        requested_role: ModelRole | None = None,
        reasoning_level: ReasoningLevel | None = None,
    ) -> ProviderResponse: ...


@runtime_checkable
class ConversationStore(Protocol):
    async def create_conversation(
        self,
        *,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> Conversation: ...

    async def get_conversation(self, conversation_id: str) -> Conversation | None: ...

    async def append_message(self, message: Message) -> Message:
        """Persist and return the message, optionally assigning its id."""
        ...

    async def recent_messages(
        self,
        conversation_id: str,
        *,
        limit: int,
    ) -> Sequence[Message]:
        """Return at most ``limit`` messages in chronological order."""
        ...


@runtime_checkable
class AuditStore(Protocol):
    async def append_audit_record(
        self,
        *,
        conversation_id: str | None,
        action: str,
        outcome: str,
        risk: str,
        detail: Mapping[str, JsonValue] | None = None,
    ) -> object: ...


@runtime_checkable
class MemoryContextPort(Protocol):
    async def capture_candidates(self, message: Message) -> int:
        """Persist candidates only; never silently commit extracted text."""
        ...

    async def project(self, query: str) -> ContextProjection | None:
        """Return bounded provenance-bearing context, or ``None`` on no accepted hit."""
        ...


@runtime_checkable
class Tool(Protocol):
    @property
    def definition(self) -> ToolDefinition: ...

    @property
    def input_model(self) -> type[BaseModel]: ...

    async def invoke(self, arguments: BaseModel) -> ToolResult: ...


@runtime_checkable
class ToolPolicy(Protocol):
    async def authorize(
        self,
        *,
        conversation: Conversation,
        call: ToolCall,
        tool: ToolDefinition,
        arguments: BaseModel,
    ) -> PolicyDecision: ...
