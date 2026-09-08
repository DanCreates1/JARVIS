"""Provider-neutral orchestration for one conversational assistant turn."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from contextlib import suppress

from pydantic import JsonValue, ValidationError

from .context import reduce_conversation_context
from .contracts import (
    AuditStore,
    ChatProvider,
    ConversationStore,
    MemoryContextPort,
    RoutedChatProvider,
    RoutedStreamingChatProvider,
    SensitivityClassifier,
    StreamingChatProvider,
    Tool,
    ToolPolicy,
)
from .models import (
    AssistantRequest,
    Conversation,
    LatencyClass,
    Message,
    MessageRole,
    ModelRole,
    PermissionLevel,
    PolicyDecision,
    ProviderResponse,
    ProviderStreamFrame,
    ProviderUsage,
    ReasoningLevel,
    RoutingDecision,
    RuntimeErrorCode,
    RuntimeErrorDetail,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeResult,
    RuntimeStatus,
    RuntimeStreamFrame,
    SensitivityClass,
    ToolCall,
    ToolDefinition,
    ToolResult,
    count_json_leaf_items,
)


class _Events:
    def __init__(self, queue: asyncio.Queue[RuntimeEvent | None] | None = None) -> None:
        self.items: list[RuntimeEvent] = []
        self.queue = queue

    def add(
        self,
        event_type: RuntimeEventType,
        *,
        conversation_id: str | None = None,
        detail: str | None = None,
        message: Message | None = None,
        tool_call: ToolCall | None = None,
        routing: RoutingDecision | None = None,
        usage: ProviderUsage | None = None,
        content_delta: str | None = None,
    ) -> None:
        event = RuntimeEvent(
            sequence=len(self.items) + 1,
            type=event_type,
            conversation_id=conversation_id,
            detail=detail,
            message=message,
            tool_call=tool_call,
            routing=routing,
            usage=usage,
            content_delta=content_delta,
        )
        self.items.append(event)
        if self.queue is not None:
            self.queue.put_nowait(event)


class _ConversationMissing(LookupError):
    """Internal sentinel that distinguishes absence from adapter failures."""


class _InvalidProviderStream(ValueError):
    """Internal sentinel for a provider stream without one terminal response."""


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
        context_recent_message_limit: int | None = None,
        context_summary_max_chars: int = 2_000,
        max_tool_iterations: int = 4,
        memory: MemoryContextPort | None = None,
        sensitivity_classifier: SensitivityClassifier | None = None,
    ) -> None:
        if context_message_limit < 1:
            raise ValueError("context_message_limit must be at least 1")
        effective_recent_limit = min(8, context_message_limit)
        if context_recent_message_limit is not None:
            effective_recent_limit = context_recent_message_limit
        if not 2 <= effective_recent_limit <= context_message_limit:
            raise ValueError("recent context limit must be between 2 and context message limit")
        if context_summary_max_chars < 128:
            raise ValueError("context summary limit must be at least 128 characters")
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
        self.public_tool_definitions = tuple(
            definition
            for definition in self.tool_definitions
            if definition.sensitivity is SensitivityClass.PUBLIC
        )
        self._tool_definitions_by_name = {
            definition.name: definition for definition in self.tool_definitions
        }
        self.system_prompt = system_prompt.strip()
        self.context_message_limit = context_message_limit
        self.context_recent_message_limit = effective_recent_limit
        self.context_summary_max_chars = context_summary_max_chars
        self.max_tool_iterations = max_tool_iterations
        self.memory = memory
        self.sensitivity_classifier = sensitivity_classifier

    async def respond(
        self,
        user_input: str,
        *,
        conversation_id: str | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
        requested_model_role: ModelRole | None = None,
        reasoning_level: ReasoningLevel | None = None,
        latency_class: LatencyClass | None = None,
    ) -> RuntimeResult:
        """Convenience entrypoint for a single user turn."""
        return await self.run(
            AssistantRequest(
                user_input=user_input,
                conversation_id=conversation_id,
                metadata=dict(metadata or {}),
                requested_model_role=requested_model_role,
                reasoning_level=reasoning_level,
                latency_class=latency_class,
            )
        )

    async def run(self, request: AssistantRequest) -> RuntimeResult:
        return await self._execute(request)

    async def stream(self, request: AssistantRequest) -> AsyncIterator[RuntimeStreamFrame]:
        """Yield live orchestration events followed by exactly one terminal result."""
        queue: asyncio.Queue[RuntimeEvent | None] = asyncio.Queue()
        task = asyncio.create_task(self._execute(request, event_queue=queue))
        task.add_done_callback(lambda _task: queue.put_nowait(None))
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield RuntimeStreamFrame(event=event)
            yield RuntimeStreamFrame(result=await task)
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    async def _execute(
        self,
        request: AssistantRequest,
        *,
        event_queue: asyncio.Queue[RuntimeEvent | None] | None = None,
    ) -> RuntimeResult:
        events = _Events(event_queue)
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
            disclosure_sensitivity=self._classify(request.user_input),
            disclosure_source="local-privacy-gate",
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
        if self.memory is not None:
            with suppress(Exception):
                await self.memory.capture_candidates(persisted)

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
                response: ProviderResponse | None = None
                latency_class = request.latency_class
                if latency_class is None and request.metadata.get("interface") == "voice":
                    latency_class = LatencyClass.NORMAL_VOICE
                if isinstance(self.provider, RoutedStreamingChatProvider):
                    provider_stream = self.provider.stream_chat_routed(
                        messages=context,
                        tools=self.tool_definitions,
                        requested_role=request.requested_model_role,
                        reasoning_level=request.reasoning_level,
                        latency_class=latency_class,
                    )
                elif isinstance(self.provider, StreamingChatProvider):
                    provider_stream = self.provider.stream_chat(
                        messages=context,
                        tools=self.public_tool_definitions,
                    )
                else:
                    provider_stream = None

                if provider_stream is not None:
                    async for raw_frame in provider_stream:
                        if response is not None:
                            raise _InvalidProviderStream(
                                "provider stream emitted a frame after its terminal response"
                            )
                        provider_frame = ProviderStreamFrame.model_validate(raw_frame)
                        if provider_frame.routing is not None:
                            events.add(
                                RuntimeEventType.ROUTING_DECIDED,
                                conversation_id=conversation.id,
                                detail=provider_frame.routing.reason,
                                routing=provider_frame.routing,
                            )
                            if provider_frame.routing.fallback_used:
                                events.add(
                                    RuntimeEventType.PROVIDER_FALLBACK,
                                    conversation_id=conversation.id,
                                    detail=provider_frame.routing.reason,
                                    routing=provider_frame.routing,
                                )
                        elif provider_frame.content_delta is not None:
                            events.add(
                                RuntimeEventType.ASSISTANT_DELTA,
                                conversation_id=conversation.id,
                                content_delta=provider_frame.content_delta,
                            )
                        else:
                            response = ProviderResponse.model_validate(provider_frame.response)
                    if response is None:
                        raise _InvalidProviderStream("provider stream omitted terminal response")
                elif isinstance(self.provider, RoutedChatProvider):
                    response = ProviderResponse.model_validate(
                        await self.provider.chat_routed(
                            messages=context,
                            tools=self.tool_definitions,
                            requested_role=request.requested_model_role,
                            reasoning_level=request.reasoning_level,
                            latency_class=latency_class,
                        )
                    )
                else:
                    response = ProviderResponse.model_validate(
                        await self.provider.chat(
                            messages=context,
                            tools=self.public_tool_definitions,
                        )
                    )
            except (ValidationError, _InvalidProviderStream):
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

            if response.routing is not None and not any(
                event.type is RuntimeEventType.ROUTING_DECIDED and event.routing == response.routing
                for event in events.items
            ):
                events.add(
                    RuntimeEventType.ROUTING_DECIDED,
                    conversation_id=conversation.id,
                    detail=response.routing.reason,
                    routing=response.routing,
                )
                if response.routing.fallback_used:
                    events.add(
                        RuntimeEventType.PROVIDER_FALLBACK,
                        conversation_id=conversation.id,
                        detail=response.routing.reason,
                        routing=response.routing,
                    )
            events.add(
                RuntimeEventType.PROVIDER_RESPONDED,
                conversation_id=conversation.id,
                detail=f"Received {len(response.tool_calls)} tool call(s).",
                routing=response.routing,
                usage=response.usage,
            )
            assistant_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=(response.content or "").strip(),
                tool_calls=response.tool_calls,
                disclosure_sensitivity=self._assistant_sensitivity(context, response),
                disclosure_source="assistant-turn",
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
                definition = self._tool_definitions_by_name[call.name]

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
                if (
                    response.routing is not None
                    and response.routing.chosen_role is not ModelRole.LOCAL
                    and definition.sensitivity is not SensitivityClass.PUBLIC
                ):
                    reason = (
                        f"Private tool '{call.name}' is local-only and cannot return data to a "
                        "cloud model."
                    )
                    events.add(
                        RuntimeEventType.TOOL_DENIED,
                        conversation_id=conversation.id,
                        detail=reason,
                        tool_call=call,
                    )
                    await self._audit_tool(
                        conversation.id,
                        call,
                        definition,
                        outcome="denied",
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
                        status=RuntimeStatus.FAILED if store_failure else RuntimeStatus.DENIED,
                        error=store_failure or error,
                        messages=turn_messages,
                        events=events,
                        tool_iterations=tool_iterations,
                    )
                try:
                    raw_decision = await self.policy.authorize(
                        conversation=conversation,
                        call=call,
                        tool=definition,
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
                        (
                            RuntimeEventType.TOOL_APPROVAL_REQUIRED
                            if decision.approval_required
                            else RuntimeEventType.TOOL_DENIED
                        ),
                        conversation_id=conversation.id,
                        detail=reason,
                        tool_call=call,
                    )
                    await self._audit_tool(
                        conversation.id,
                        call,
                        definition,
                        outcome=("requested" if decision.approval_required else "denied"),
                    )
                    error = RuntimeErrorDetail(
                        code=(
                            RuntimeErrorCode.APPROVAL_REQUIRED
                            if decision.approval_required
                            else RuntimeErrorCode.TOOL_DENIED
                        ),
                        message=reason,
                        tool_call_id=call.id,
                        tool_name=call.name,
                        approval_id=decision.approval_id,
                    )
                    store_failure = await self._persist_tool_error(
                        conversation.id, call, error, turn_messages, events
                    )
                    return self._failure(
                        conversation_id=conversation.id,
                        status=(
                            RuntimeStatus.FAILED
                            if store_failure
                            else (
                                RuntimeStatus.APPROVAL_REQUIRED
                                if decision.approval_required
                                else RuntimeStatus.DENIED
                            )
                        ),
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
                await self._audit_tool(
                    conversation.id,
                    call,
                    definition,
                    outcome="allowed",
                )
                if definition.permission_level is not PermissionLevel.LEVEL_0:
                    error = RuntimeErrorDetail(
                        code=RuntimeErrorCode.BROKER_REQUIRED,
                        message=(
                            f"Tool '{call.name}' requires the Phase 3 action broker; "
                            "direct runtime execution is prohibited."
                        ),
                        tool_call_id=call.id,
                        tool_name=call.name,
                    )
                    store_failure = await self._persist_tool_error(
                        conversation.id, call, error, turn_messages, events
                    )
                    return self._failure(
                        conversation_id=conversation.id,
                        status=RuntimeStatus.DENIED,
                        error=store_failure or error,
                        messages=turn_messages,
                        events=events,
                        tool_iterations=tool_iterations,
                    )
                events.add(
                    RuntimeEventType.TOOL_STARTED,
                    conversation_id=conversation.id,
                    detail=f"Running tool '{call.name}'.",
                    tool_call=call,
                )
                tool_iterations += 1
                try:
                    async with asyncio.timeout(definition.timeout_seconds):
                        raw_result = await tool.invoke(arguments)
                    tool_result = ToolResult.model_validate(raw_result)
                    _validate_tool_result_limits(tool_result, definition)
                except TimeoutError:
                    error = RuntimeErrorDetail(
                        code=RuntimeErrorCode.TOOL_TIMEOUT,
                        message=f"Tool '{call.name}' exceeded its fixed timeout.",
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
                except _ToolResultLimitError:
                    error = RuntimeErrorDetail(
                        code=RuntimeErrorCode.TOOL_RESULT_LIMIT,
                        message=f"Tool '{call.name}' exceeded its fixed result limit.",
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

                tool_message = self._tool_message(
                    conversation.id,
                    call,
                    tool_result,
                    definition=definition,
                    inherited_sensitivity=assistant_message.disclosure_sensitivity,
                )
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
                await self._audit_tool(
                    conversation.id,
                    call,
                    definition,
                    outcome="completed",
                )

    async def _audit_tool(
        self,
        conversation_id: str,
        call: ToolCall,
        definition: ToolDefinition,
        *,
        outcome: str,
    ) -> None:
        """Write metadata-only audit entries when the store supports them."""
        if not isinstance(self.store, AuditStore):
            return
        try:
            await self.store.append_audit_record(
                conversation_id=conversation_id,
                action=call.name,
                outcome=outcome,
                risk=definition.risk.value,
                detail={"tool_call_id": call.id},
            )
        except Exception:
            # Phase 1 tools are read-only. Future side effects must fail closed on audit failure.
            return

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
        recent = reduce_conversation_context(
            recent,
            recent_limit=self.context_recent_message_limit,
            summary_max_chars=self.context_summary_max_chars,
            classify=self._classify,
        )
        memory_message: Message | None = None
        if self.memory is not None:
            latest_user = next(
                (
                    message.content
                    for message in reversed(recent)
                    if message.role is MessageRole.USER
                ),
                "",
            )
            if latest_user:
                try:
                    projection = await self.memory.project(latest_user)
                except Exception:
                    projection = None
                if projection is not None:
                    memory_message = Message(
                        conversation_id=conversation.id,
                        role=MessageRole.SYSTEM,
                        content=projection.content,
                        context_sensitivity=projection.sensitivity,
                        context_source=projection.source,
                        disclosure_sensitivity=projection.sensitivity,
                        disclosure_source=projection.source,
                    )
        if not self.system_prompt:
            return ((memory_message,) if memory_message is not None else ()) + recent
        system = Message(
            conversation_id=conversation.id,
            role=MessageRole.SYSTEM,
            content=self.system_prompt,
            disclosure_sensitivity=SensitivityClass.PUBLIC,
            disclosure_source="static-system-prompt",
        )
        return (system, *((memory_message,) if memory_message is not None else ()), *recent)

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
        message = self._tool_message(
            conversation_id,
            call,
            result,
            definition=self._tool_definitions_by_name.get(call.name),
        )
        _, store_failure = await self._persist(message, conversation_id, turn_messages, events)
        return store_failure

    def _tool_message(
        self,
        conversation_id: str,
        call: ToolCall,
        result: ToolResult,
        *,
        definition: ToolDefinition | None = None,
        inherited_sensitivity: SensitivityClass | None = None,
    ) -> Message:
        sensitivity: SensitivityClass | None = inherited_sensitivity
        if definition is not None:
            sensitivity = (
                definition.sensitivity
                if sensitivity is None
                else _more_restrictive(sensitivity, definition.sensitivity)
            )
        scanned = self._classify(call.model_dump_json() + "\n" + result.model_dump_json())
        if sensitivity is None or scanned is SensitivityClass.PRIVATE:
            sensitivity = (
                scanned if sensitivity is None else _more_restrictive(sensitivity, scanned)
            )
        return Message(
            conversation_id=conversation_id,
            role=MessageRole.TOOL,
            content=result.model_dump_json(),
            tool_call_id=call.id,
            tool_name=call.name,
            disclosure_sensitivity=sensitivity,
            disclosure_source="tool-result",
        )

    def _classify(self, text: str) -> SensitivityClass:
        if self.sensitivity_classifier is None:
            return SensitivityClass.UNKNOWN
        return self.sensitivity_classifier.classify(text)

    def _assistant_sensitivity(
        self,
        context: Sequence[Message],
        response: ProviderResponse,
    ) -> SensitivityClass:
        sensitivity = response.routing.sensitivity if response.routing else SensitivityClass.PUBLIC
        for message in context:
            explicit = message.disclosure_sensitivity or message.context_sensitivity
            if explicit is None and message.role is not MessageRole.USER:
                explicit = SensitivityClass.UNKNOWN
            if explicit is not None:
                sensitivity = _more_restrictive(sensitivity, explicit)
            scanned = self._classify(message.content)
            if explicit is None or scanned is SensitivityClass.PRIVATE:
                sensitivity = _more_restrictive(sensitivity, scanned)
        response_text = (
            (response.content or "")
            + "\n"
            + "\n".join(call.model_dump_json() for call in response.tool_calls)
        )
        scanned_response = self._classify(response_text)
        if scanned_response is SensitivityClass.PRIVATE:
            return _more_restrictive(sensitivity, scanned_response)
        return sensitivity

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


class _ToolResultLimitError(ValueError):
    """Internal sentinel for deterministic serialized-result bounds."""


def _more_restrictive(
    left: SensitivityClass,
    right: SensitivityClass,
) -> SensitivityClass:
    order = {
        SensitivityClass.PUBLIC: 0,
        SensitivityClass.UNKNOWN: 1,
        SensitivityClass.PRIVATE: 2,
    }
    return left if order[left] >= order[right] else right


def _validate_tool_result_limits(result: ToolResult, definition: ToolDefinition) -> None:
    serialized = result.model_dump_json().encode("utf-8")
    if len(serialized) > definition.max_result_bytes:
        raise _ToolResultLimitError("serialized result exceeds byte limit")
    if (
        count_json_leaf_items(result.data, stop_after=definition.max_result_items)
        > definition.max_result_items
    ):
        raise _ToolResultLimitError("structured result exceeds item limit")
