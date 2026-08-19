"""Provider-neutral orchestration for one conversational assistant turn."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from pydantic import JsonValue, ValidationError

from .contracts import ChatProvider, ConversationStore, Tool, ToolPolicy
from .models import (
    AssistantRequest,
    Conversation,
    Message,
    MessageRole,
    PolicyDecision,
    ProviderResponse,
    RuntimeErrorCode,
    RuntimeErrorDetail,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeResult,
    RuntimeStatus,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


class _Events:
    def __init__(self) -> None:
        self.items: list[RuntimeEvent] = []

    def add(
        self,
        event_type: RuntimeEventType,
        *,
        conversation_id: str | None = None,
        detail: str | None = None,
        message: Message | None = None,
        tool_call: ToolCall | None = None,
    ) -> None:
        self.items.append(
            RuntimeEvent(
                sequence=len(self.items) + 1,
                type=event_type,
                conversation_id=conversation_id,
                detail=detail,
                message=message,
                tool_call=tool_call,
            )
        )


class _ConversationMissing(LookupError):
    """Internal sentinel that distinguishes absence from adapter failures."""


class AssistantService:
    """Coordinates persistence, provider calls, policy, and tool execution."""

    def __init__(
        self,
        *,
        provider: ChatProvider,
        store: ConversationStore,
        tools: Iterable[Tool],
        policy: ToolPolicy,
        system_prompt: str = "",
        context_message_limit: int = 20,
        max_tool_iterations: int = 4,
    ) -> None:
        if context_message_limit < 1:
            raise ValueError("context_message_limit must be at least 1")
        if max_tool_iterations < 1:
            raise ValueError("max_tool_iterations must be at least 1")

        tool_map: dict[str, Tool] = {}
        definitions: list[ToolDefinition] = []
        for tool in tools:
            definition = ToolDefinition.model_validate(tool.definition)
            if definition.name in tool_map:
                raise ValueError(f"duplicate tool name: {definition.name}")
            tool_map[definition.name] = tool
            definitions.append(definition)

        self.provider = provider
        self.store = store
        self.policy = policy
        self.tools = tool_map
        self.tool_definitions = tuple(definitions)
        self.system_prompt = system_prompt.strip()
        self.context_message_limit = context_message_limit
        self.max_tool_iterations = max_tool_iterations

    async def respond(
        self,
        user_input: str,
        *,
        conversation_id: str | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> RuntimeResult:
        """Convenience entrypoint for a single user turn."""
        return await self.run(
            AssistantRequest(
                user_input=user_input,
                conversation_id=conversation_id,
                metadata=dict(metadata or {}),
            )
        )

    async def run(self, request: AssistantRequest) -> RuntimeResult:
        events = _Events()
        turn_messages: list[Message] = []
        tool_iterations = 0

        try:
            conversation = await self._open_conversation(request, events)
        except _ConversationMissing:
            error = RuntimeErrorDetail(
                code=RuntimeErrorCode.CONVERSATION_NOT_FOUND,
                message=f"Conversation '{request.conversation_id}' was not found.",
            )
            return self._failure(
                conversation_id=request.conversation_id,
                status=RuntimeStatus.FAILED,
                error=error,
                messages=turn_messages,
                events=events,
                tool_iterations=tool_iterations,
            )
        except Exception:
            error = RuntimeErrorDetail(
                code=RuntimeErrorCode.STORE_ERROR,
                message="Conversation storage failed while opening the conversation.",
            )
            return self._failure(
                conversation_id=request.conversation_id,
                status=RuntimeStatus.FAILED,
                error=error,
                messages=turn_messages,
                events=events,
                tool_iterations=tool_iterations,
            )

        user_message = Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=request.user_input,
        )
        persisted, store_failure = await self._persist(
            user_message, conversation.id, turn_messages, events
        )
        if store_failure:
            return self._failure(
                conversation_id=conversation.id,
                status=RuntimeStatus.FAILED,
                error=store_failure,
                messages=turn_messages,
                events=events,
                tool_iterations=tool_iterations,
            )
        assert persisted is not None

        while True:
            try:
                context = await self._context(conversation)
            except Exception:
                error = RuntimeErrorDetail(
                    code=RuntimeErrorCode.STORE_ERROR,
                    message="Conversation storage failed while loading recent context.",
                )
                return self._failure(
                    conversation_id=conversation.id,
                    status=RuntimeStatus.FAILED,
                    error=error,
                    messages=turn_messages,
                    events=events,
                    tool_iterations=tool_iterations,
                )

            events.add(
                RuntimeEventType.PROVIDER_REQUESTED,
                conversation_id=conversation.id,
                detail=f"Sent {len(context)} messages to the chat provider.",
            )
            try:
                raw_response = await self.provider.chat(
                    messages=context,
                    tools=self.tool_definitions,
                )
                response = ProviderResponse.model_validate(raw_response)
            except ValidationError:
                error = RuntimeErrorDetail(
                    code=RuntimeErrorCode.INVALID_PROVIDER_RESPONSE,
                    message="The chat provider returned an invalid response.",
                )
                return self._failure(
                    conversation_id=conversation.id,
                    status=RuntimeStatus.FAILED,
                    error=error,
                    messages=turn_messages,
                    events=events,
                    tool_iterations=tool_iterations,
                )
            except Exception:
                error = RuntimeErrorDetail(
                    code=RuntimeErrorCode.PROVIDER_ERROR,
                    message="The chat provider failed to produce a response.",
                )
                return self._failure(
                    conversation_id=conversation.id,
                    status=RuntimeStatus.FAILED,
                    error=error,
                    messages=turn_messages,
                    events=events,
                    tool_iterations=tool_iterations,
                )

            events.add(
                RuntimeEventType.PROVIDER_RESPONDED,
                conversation_id=conversation.id,
                detail=f"Received {len(response.tool_calls)} tool call(s).",
            )
            assistant_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=(response.content or "").strip(),
                tool_calls=response.tool_calls,
            )
            _, store_failure = await self._persist(
                assistant_message, conversation.id, turn_messages, events
            )
            if store_failure:
                return self._failure(
                    conversation_id=conversation.id,
                    status=RuntimeStatus.FAILED,
                    error=store_failure,
                    messages=turn_messages,
                    events=events,
                    tool_iterations=tool_iterations,
                )

            if not response.tool_calls:
                reply = (response.content or "").strip()
                events.add(
                    RuntimeEventType.RUNTIME_COMPLETED,
                    conversation_id=conversation.id,
                    detail="Assistant turn completed.",
                )
                return RuntimeResult(
                    conversation_id=conversation.id,
                    status=RuntimeStatus.COMPLETED,
                    reply=reply,
                    messages=tuple(turn_messages),
                    events=tuple(events.items),
                    tool_iterations=tool_iterations,
                )

            for call in response.tool_calls:
                events.add(
                    RuntimeEventType.TOOL_REQUESTED,
                    conversation_id=conversation.id,
                    detail=f"Provider requested tool '{call.name}'.",
                    tool_call=call,
                )

                if tool_iterations >= self.max_tool_iterations:
                    error = RuntimeErrorDetail(
                        code=RuntimeErrorCode.TOOL_ITERATION_LIMIT,
                        message=(
                            "The assistant stopped because the tool iteration limit "
                            f"({self.max_tool_iterations}) was reached."
                        ),
                        tool_call_id=call.id,
                        tool_name=call.name,
                    )
                    store_failure = await self._persist_tool_error(
                        conversation.id, call, error, turn_messages, events
                    )
                    if store_failure:
                        error = store_failure
                        status = RuntimeStatus.FAILED
                    else:
                        status = RuntimeStatus.LIMIT_REACHED
                    return self._failure(
                        conversation_id=conversation.id,
                        status=status,
                        error=error,
                        messages=turn_messages,
                        events=events,
                        tool_iterations=tool_iterations,
                    )

                tool = self.tools.get(call.name)
                if tool is None:
                    error = RuntimeErrorDetail(
                        code=RuntimeErrorCode.UNKNOWN_TOOL,
                        message=f"The provider requested unknown tool '{call.name}'.",
                        tool_call_id=call.id,
                        tool_name=call.name,
                    )
                    store_failure = await self._persist_tool_error(
                        conversation.id, call, error, turn_messages, events
                    )
                    return self._failure(
                        conversation_id=conversation.id,
                        status=RuntimeStatus.FAILED,
                        error=store_failure or error,
                        messages=turn_messages,
                        events=events,
                        tool_iterations=tool_iterations,
                    )

                try:
                    arguments = tool.input_model.model_validate(call.arguments)
                except ValidationError:
                    error = RuntimeErrorDetail(
                        code=RuntimeErrorCode.INVALID_TOOL_ARGUMENTS,
                        message=f"The provider supplied invalid arguments for '{call.name}'.",
                        tool_call_id=call.id,
                        tool_name=call.name,
                    )
                    store_failure = await self._persist_tool_error(
                        conversation.id, call, error, turn_messages, events
                    )
                    return self._failure(
                        conversation_id=conversation.id,
                        status=RuntimeStatus.FAILED,
                        error=store_failure or error,
                        messages=turn_messages,
                        events=events,
                        tool_iterations=tool_iterations,
                    )

                events.add(
                    RuntimeEventType.TOOL_VALIDATED,
                    conversation_id=conversation.id,
                    detail=f"Validated arguments for '{call.name}'.",
                    tool_call=call,
                )
                try:
                    raw_decision = await self.policy.authorize(
                        conversation=conversation,
                        call=call,
                        tool=tool.definition,
                        arguments=arguments,
                    )
                    decision = PolicyDecision.model_validate(raw_decision)
                except Exception:
                    error = RuntimeErrorDetail(
                        code=RuntimeErrorCode.POLICY_ERROR,
                        message=f"Tool policy evaluation failed for '{call.name}'.",
                        tool_call_id=call.id,
                        tool_name=call.name,
                    )
                    store_failure = await self._persist_tool_error(
                        conversation.id, call, error, turn_messages, events
                    )
                    return self._failure(
                        conversation_id=conversation.id,
                        status=RuntimeStatus.FAILED,
                        error=store_failure or error,
                        messages=turn_messages,
                        events=events,
                        tool_iterations=tool_iterations,
                    )

                if not decision.allowed:
                    reason = (decision.reason or "Tool execution was denied.").strip()
                    events.add(
                        RuntimeEventType.TOOL_DENIED,
                        conversation_id=conversation.id,
                        detail=reason,
                        tool_call=call,
                    )
                    error = RuntimeErrorDetail(
                        code=RuntimeErrorCode.TOOL_DENIED,
                        message=reason,
                        tool_call_id=call.id,
                        tool_name=call.name,
                    )
                    store_failure = await self._persist_tool_error(
                        conversation.id, call, error, turn_messages, events
                    )
                    return self._failure(
                        conversation_id=conversation.id,
                        status=(RuntimeStatus.FAILED if store_failure else RuntimeStatus.DENIED),
                        error=store_failure or error,
                        messages=turn_messages,
                        events=events,
                        tool_iterations=tool_iterations,
                    )

                events.add(
                    RuntimeEventType.TOOL_AUTHORIZED,
                    conversation_id=conversation.id,
                    detail=f"Authorized tool '{call.name}'.",
                    tool_call=call,
                )
                events.add(
                    RuntimeEventType.TOOL_STARTED,
                    conversation_id=conversation.id,
                    detail=f"Running tool '{call.name}'.",
                    tool_call=call,
                )
                tool_iterations += 1
                try:
                    raw_result = await tool.invoke(arguments)
                    tool_result = ToolResult.model_validate(raw_result)
                except Exception:
                    error = RuntimeErrorDetail(
                        code=RuntimeErrorCode.TOOL_ERROR,
                        message=f"Tool '{call.name}' failed during execution.",
                        tool_call_id=call.id,
                        tool_name=call.name,
                    )
                    store_failure = await self._persist_tool_error(
                        conversation.id, call, error, turn_messages, events
                    )
                    return self._failure(
                        conversation_id=conversation.id,
                        status=RuntimeStatus.FAILED,
                        error=store_failure or error,
                        messages=turn_messages,
                        events=events,
                        tool_iterations=tool_iterations,
                    )

                tool_message = self._tool_message(conversation.id, call, tool_result)
                _, store_failure = await self._persist(
                    tool_message, conversation.id, turn_messages, events
                )
                if store_failure:
                    return self._failure(
                        conversation_id=conversation.id,
                        status=RuntimeStatus.FAILED,
                        error=store_failure,
                        messages=turn_messages,
                        events=events,
                        tool_iterations=tool_iterations,
                    )
                events.add(
                    RuntimeEventType.TOOL_COMPLETED,
                    conversation_id=conversation.id,
                    detail=f"Tool '{call.name}' completed.",
                    tool_call=call,
                )

    async def _open_conversation(self, request: AssistantRequest, events: _Events) -> Conversation:
        if request.conversation_id is None:
            conversation = Conversation.model_validate(
                await self.store.create_conversation(metadata=request.metadata)
            )
            events.add(
                RuntimeEventType.CONVERSATION_CREATED,
                conversation_id=conversation.id,
                detail="Created a new conversation.",
            )
            return conversation

        stored_conversation = await self.store.get_conversation(request.conversation_id)
        if stored_conversation is None:
            raise _ConversationMissing(request.conversation_id)
        conversation = Conversation.model_validate(stored_conversation)
        if conversation.id != request.conversation_id:
            raise ValueError("conversation store returned a mismatched identifier")
        events.add(
            RuntimeEventType.CONVERSATION_RESUMED,
            conversation_id=conversation.id,
            detail="Resumed an existing conversation.",
        )
        return conversation

    async def _context(self, conversation: Conversation) -> tuple[Message, ...]:
        raw_recent = await self.store.recent_messages(
            conversation.id,
            limit=self.context_message_limit,
        )
        recent = tuple(Message.model_validate(message) for message in raw_recent)
        if len(recent) > self.context_message_limit:
            raise ValueError("conversation store exceeded the context message limit")
        if any(message.conversation_id != conversation.id for message in recent):
            raise ValueError("conversation store returned a message from another conversation")
        if not self.system_prompt:
            return recent
        system = Message(
            conversation_id=conversation.id,
            role=MessageRole.SYSTEM,
            content=self.system_prompt,
        )
        return (system, *recent)

    async def _persist(
        self,
        message: Message,
        conversation_id: str,
        turn_messages: list[Message],
        events: _Events,
    ) -> tuple[Message | None, RuntimeErrorDetail | None]:
        try:
            persisted = Message.model_validate(await self.store.append_message(message))
            if persisted.conversation_id != conversation_id:
                raise ValueError("conversation store persisted a message to another conversation")
        except Exception:
            return None, RuntimeErrorDetail(
                code=RuntimeErrorCode.STORE_ERROR,
                message="Conversation storage failed while persisting a message.",
            )
        turn_messages.append(persisted)
        events.add(
            RuntimeEventType.MESSAGE_PERSISTED,
            conversation_id=conversation_id,
            detail=f"Persisted {persisted.role.value} message.",
            message=persisted,
        )
        return persisted, None

    async def _persist_tool_error(
        self,
        conversation_id: str,
        call: ToolCall,
        error: RuntimeErrorDetail,
        turn_messages: list[Message],
        events: _Events,
    ) -> RuntimeErrorDetail | None:
        result = ToolResult(
            content=error.message,
            is_error=True,
            data={"code": error.code.value},
        )
        message = self._tool_message(conversation_id, call, result)
        _, store_failure = await self._persist(message, conversation_id, turn_messages, events)
        return store_failure

    @staticmethod
    def _tool_message(
        conversation_id: str,
        call: ToolCall,
        result: ToolResult,
    ) -> Message:
        return Message(
            conversation_id=conversation_id,
            role=MessageRole.TOOL,
            content=result.model_dump_json(),
            tool_call_id=call.id,
            tool_name=call.name,
        )

    @staticmethod
    def _failure(
        *,
        conversation_id: str | None,
        status: RuntimeStatus,
        error: RuntimeErrorDetail,
        messages: Sequence[Message],
        events: _Events,
        tool_iterations: int,
    ) -> RuntimeResult:
        events.add(
            RuntimeEventType.RUNTIME_FAILED,
            conversation_id=conversation_id,
            detail=error.message,
        )
        return RuntimeResult(
            conversation_id=conversation_id,
            status=status,
            messages=tuple(messages),
            events=tuple(events.items),
            error=error,
            tool_iterations=tool_iterations,
        )
