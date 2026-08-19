"""Deterministic in-memory implementations of the core runtime ports."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, JsonValue

from jarvis.core import (
    Conversation,
    Message,
    PolicyDecision,
    ProviderResponse,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


@dataclass(frozen=True)
class ProviderRequest:
    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...]


class FakeChatProvider:
    def __init__(self, responses: Iterable[object]) -> None:
        self.responses = deque(responses)
        self.requests: list[ProviderRequest] = []

    async def chat(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition],
    ) -> ProviderResponse:
        self.requests.append(ProviderRequest(messages=tuple(messages), tools=tuple(tools)))
        if not self.responses:
            raise AssertionError("FakeChatProvider has no queued response")
        response = self.responses.popleft()
        if isinstance(response, BaseException):
            raise response
        # Deliberately allow raw values so tests can exercise the trust boundary.
        return response  # type: ignore[return-value]


class InMemoryConversationStore:
    def __init__(self, *, fail_operations: Iterable[str] = ()) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.messages: dict[str, list[Message]] = {}
        self.fail_operations = set(fail_operations)
        self.recent_requests: list[tuple[str, int]] = []
        self._conversation_counter = 0
        self._message_counter = 0

    def add_conversation(
        self,
        conversation_id: str,
        *,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> Conversation:
        conversation = Conversation(
            id=conversation_id,
            metadata=dict(metadata or {}),
        )
        self.conversations[conversation_id] = conversation
        self.messages.setdefault(conversation_id, [])
        return conversation

    async def create_conversation(
        self,
        *,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> Conversation:
        self._fail_if_requested("create_conversation")
        self._conversation_counter += 1
        return self.add_conversation(
            f"conversation-{self._conversation_counter}",
            metadata=metadata,
        )

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        self._fail_if_requested("get_conversation")
        return self.conversations.get(conversation_id)

    async def append_message(self, message: Message) -> Message:
        self._fail_if_requested("append_message")
        if message.conversation_id not in self.conversations:
            raise LookupError(message.conversation_id)
        self._message_counter += 1
        persisted = (
            message
            if message.id is not None
            else message.model_copy(update={"id": f"message-{self._message_counter}"})
        )
        self.messages[message.conversation_id].append(persisted)
        return persisted

    async def recent_messages(
        self,
        conversation_id: str,
        *,
        limit: int,
    ) -> Sequence[Message]:
        self._fail_if_requested("recent_messages")
        if conversation_id not in self.conversations:
            raise LookupError(conversation_id)
        self.recent_requests.append((conversation_id, limit))
        return tuple(self.messages[conversation_id][-limit:])

    def _fail_if_requested(self, operation: str) -> None:
        if operation in self.fail_operations:
            raise RuntimeError(f"forced {operation} failure")


@dataclass(frozen=True)
class PolicyRequest:
    conversation: Conversation
    call: ToolCall
    tool: ToolDefinition
    arguments: BaseModel


class FakeToolPolicy:
    def __init__(self, decisions: Iterable[object] = ()) -> None:
        self.decisions = deque(decisions)
        self.requests: list[PolicyRequest] = []

    async def authorize(
        self,
        *,
        conversation: Conversation,
        call: ToolCall,
        tool: ToolDefinition,
        arguments: BaseModel,
    ) -> PolicyDecision:
        self.requests.append(
            PolicyRequest(
                conversation=conversation,
                call=call,
                tool=tool,
                arguments=arguments,
            )
        )
        if not self.decisions:
            return PolicyDecision(allowed=True)
        decision = self.decisions.popleft()
        if isinstance(decision, BaseException):
            raise decision
        return decision  # type: ignore[return-value]


ToolOutcome = ToolResult | BaseException | Callable[[BaseModel], ToolResult]


class FakeTool:
    def __init__(
        self,
        *,
        name: str,
        input_model: type[BaseModel],
        description: str = "A deterministic fake tool.",
        outcomes: Iterable[ToolOutcome] = (),
    ) -> None:
        self._input_model = input_model
        self._definition = ToolDefinition(
            name=name,
            description=description,
            input_schema=input_model.model_json_schema(),
        )
        self.outcomes = deque(outcomes)
        self.calls: list[BaseModel] = []

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return self._input_model

    async def invoke(self, arguments: BaseModel) -> ToolResult:
        self.calls.append(arguments)
        if self.outcomes:
            outcome = self.outcomes.popleft()
            if isinstance(outcome, BaseException):
                raise outcome
            if callable(outcome):
                return outcome(arguments)
            return outcome
        return ToolResult(
            content=f"{self.definition.name} completed.",
            data=arguments.model_dump(mode="json"),
        )
