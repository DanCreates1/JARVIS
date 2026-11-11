from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from jarvis.core import (
    AssistantRequest,
    AssistantService,
    Message,
    MessageRole,
    PolicyDecision,
    ProviderResponse,
    RuntimeErrorCode,
    RuntimeEventType,
    RuntimeStatus,
    ToolResult,
)
from tests.fakes import (
    FakeChatProvider,
    FakeTool,
    FakeToolPolicy,
    InMemoryConversationStore,
)


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


def tool_response(
    call_id: str,
    *,
    name: str = "echo",
    arguments: object | None = None,
) -> dict[str, object]:
    return {
        "tool_calls": [
            {
                "id": call_id,
                "name": name,
                "arguments": {"text": "hello"} if arguments is None else arguments,
            }
        ]
    }


def make_service(
    responses: list[object],
    *,
    store: InMemoryConversationStore | None = None,
    tool: FakeTool | None = None,
    policy: FakeToolPolicy | None = None,
    system_prompt: str = "",
    context_message_limit: int = 20,
    max_tool_iterations: int = 4,
) -> tuple[
    AssistantService,
    FakeChatProvider,
    InMemoryConversationStore,
    FakeTool,
    FakeToolPolicy,
]:
    provider = FakeChatProvider(responses)
    store = store or InMemoryConversationStore()
    tool = tool or FakeTool(name="echo", input_model=EchoArguments)
    policy = policy or FakeToolPolicy()
    service = AssistantService(
        provider=provider,
        store=store,
        tools=[tool],
        policy=policy,
        system_prompt=system_prompt,
        context_message_limit=context_message_limit,
        max_tool_iterations=max_tool_iterations,
    )
    return service, provider, store, tool, policy


@pytest.mark.asyncio
async def test_creates_conversation_and_persists_completed_turn() -> None:
    service, provider, store, _tool, _policy = make_service(
        [ProviderResponse(content="  Hello there.  ")]
    )

    result = await service.respond("  Hi  ", metadata={"source": "test"})

    assert result.status is RuntimeStatus.COMPLETED
    assert result.reply == "Hello there."
    assert result.conversation_id == "conversation-1"
    assert store.conversations["conversation-1"].metadata == {"source": "test"}
    assert [message.role for message in result.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert [message.content for message in result.messages] == ["Hi", "Hello there."]
    assert all(message.id is not None for message in result.messages)
    assert provider.requests[0].messages[-1].content == "Hi"
    assert result.events[0].type is RuntimeEventType.CONVERSATION_CREATED
    assert result.events[-1].type is RuntimeEventType.RUNTIME_COMPLETED
    assert [event.sequence for event in result.events] == list(range(1, len(result.events) + 1))


@pytest.mark.asyncio
async def test_stream_yields_live_events_then_terminal_result() -> None:
    service, _provider, _store, _tool, _policy = make_service(
        [ProviderResponse(content="Stream complete.")]
    )
    frames = [frame async for frame in service.stream(AssistantRequest(user_input="Hello"))]
    assert frames[0].event is not None
    assert frames[-1].result is not None
    assert frames[-1].result.reply == "Stream complete."


@pytest.mark.asyncio
async def test_read_only_tool_continues_when_optional_audit_write_fails() -> None:
    store = InMemoryConversationStore(fail_operations={"append_audit_record"})
    service, _provider, _store, _tool, _policy = make_service(
        [tool_response("call-1"), ProviderResponse(content="Done.")], store=store
    )
    result = await service.respond("Echo hello")
    assert result.status is RuntimeStatus.COMPLETED
    assert result.reply == "Done."


@pytest.mark.asyncio
async def test_resumes_conversation_with_bounded_recent_context() -> None:
    store = InMemoryConversationStore()
    store.add_conversation("existing")
    for role, content in (
        (MessageRole.USER, "u1"),
        (MessageRole.ASSISTANT, "a1"),
        (MessageRole.USER, "u2"),
        (MessageRole.ASSISTANT, "a2"),
        (MessageRole.USER, "u3"),
    ):
        await store.append_message(Message(conversation_id="existing", role=role, content=content))
    service, provider, _store, _tool, _policy = make_service(
        [ProviderResponse(content="done")],
        store=store,
        system_prompt="You are concise.",
        context_message_limit=3,
    )

    result = await service.respond("latest", conversation_id="existing")

    assert result.status is RuntimeStatus.COMPLETED
    assert result.events[0].type is RuntimeEventType.CONVERSATION_RESUMED
    sent = provider.requests[0].messages
    assert [(message.role, message.content) for message in sent] == [
        (MessageRole.SYSTEM, "You are concise."),
        (MessageRole.ASSISTANT, "a2"),
        (MessageRole.USER, "u3"),
        (MessageRole.USER, "latest"),
    ]
    assert store.recent_requests == [("existing", 3)]


@pytest.mark.asyncio
async def test_executes_validated_tool_and_persists_full_tool_loop() -> None:
    tool = FakeTool(
        name="echo",
        input_model=EchoArguments,
        outcomes=[ToolResult(content="echoed", data={"text": "hello"})],
    )
    service, provider, store, _tool, policy = make_service(
        [tool_response("call-1"), ProviderResponse(content="It echoed.")],
        tool=tool,
    )

    result = await service.respond("echo this")

    assert result.status is RuntimeStatus.COMPLETED
    assert result.reply == "It echoed."
    assert result.tool_iterations == 1
    assert len(provider.requests) == 2
    assert provider.requests[0].tools[0].name == "echo"
    assert isinstance(tool.calls[0], EchoArguments)
    assert tool.calls[0].text == "hello"
    assert policy.requests[0].arguments is tool.calls[0]
    assert [message.role for message in result.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
        MessageRole.ASSISTANT,
    ]
    tool_message = result.messages[2]
    assert tool_message.tool_call_id == "call-1"
    assert tool_message.tool_name == "echo"
    persisted_result = ToolResult.model_validate_json(tool_message.content)
    assert persisted_result == ToolResult(content="echoed", data={"text": "hello"})
    assert provider.requests[1].messages[-1] == tool_message
    assert store.messages[result.conversation_id or ""] == list(result.messages)
    event_types = [event.type for event in result.events]
    assert RuntimeEventType.TOOL_VALIDATED in event_types
    assert RuntimeEventType.TOOL_AUTHORIZED in event_types
    assert RuntimeEventType.TOOL_STARTED in event_types
    assert RuntimeEventType.TOOL_COMPLETED in event_types


@pytest.mark.asyncio
async def test_rejects_malformed_untrusted_provider_tool_call() -> None:
    service, _provider, store, tool, policy = make_service(
        [tool_response("bad-call", arguments=["not", "an", "object"])]
    )

    result = await service.respond("try a tool")

    assert result.status is RuntimeStatus.FAILED
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.INVALID_PROVIDER_RESPONSE
    assert [message.role for message in result.messages] == [MessageRole.USER]
    assert len(store.messages[result.conversation_id or ""]) == 1
    assert tool.calls == []
    assert policy.requests == []


@pytest.mark.asyncio
async def test_rejects_duplicate_provider_tool_call_ids() -> None:
    duplicate_calls = {
        "tool_calls": [
            {"id": "same", "name": "echo", "arguments": {"text": "one"}},
            {"id": "same", "name": "echo", "arguments": {"text": "two"}},
        ]
    }
    service, _provider, _store, tool, _policy = make_service([duplicate_calls])

    result = await service.respond("duplicate")

    assert result.status is RuntimeStatus.FAILED
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.INVALID_PROVIDER_RESPONSE
    assert tool.calls == []


@pytest.mark.asyncio
async def test_unknown_tool_is_persisted_as_error_and_never_authorized() -> None:
    service, _provider, _store, tool, policy = make_service(
        [tool_response("call-unknown", name="missing")]
    )

    result = await service.respond("use missing")

    assert result.status is RuntimeStatus.FAILED
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.UNKNOWN_TOOL
    assert [message.role for message in result.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    tool_error = ToolResult.model_validate_json(result.messages[-1].content)
    assert tool_error.is_error is True
    assert tool_error.data == {"code": "unknown_tool"}
    assert tool.calls == []
    assert policy.requests == []


@pytest.mark.asyncio
async def test_invalid_tool_arguments_fail_before_policy_or_invocation() -> None:
    service, _provider, _store, tool, policy = make_service(
        [tool_response("call-invalid", arguments={"wrong": "field"})]
    )

    result = await service.respond("invalid args")

    assert result.status is RuntimeStatus.FAILED
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.INVALID_TOOL_ARGUMENTS
    assert result.messages[-1].role is MessageRole.TOOL
    assert ToolResult.model_validate_json(result.messages[-1].content).is_error
    assert tool.calls == []
    assert policy.requests == []


@pytest.mark.asyncio
async def test_policy_denial_is_a_structured_persisted_result() -> None:
    policy = FakeToolPolicy([PolicyDecision(allowed=False, reason="User approval is required.")])
    service, _provider, _store, tool, _policy = make_service(
        [tool_response("call-denied")], policy=policy
    )

    result = await service.respond("do a sensitive thing")

    assert result.status is RuntimeStatus.DENIED
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.TOOL_DENIED
    assert result.error.message == "User approval is required."
    assert tool.calls == []
    persisted = ToolResult.model_validate_json(result.messages[-1].content)
    assert persisted.is_error
    assert persisted.content == "User approval is required."
    assert RuntimeEventType.TOOL_DENIED in [event.type for event in result.events]


@pytest.mark.asyncio
async def test_policy_exception_is_surfaced_without_invoking_tool() -> None:
    policy = FakeToolPolicy([RuntimeError("policy backend unavailable")])
    service, _provider, _store, tool, _policy = make_service(
        [tool_response("call-policy-error")], policy=policy
    )

    result = await service.respond("policy fails")

    assert result.status is RuntimeStatus.FAILED
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.POLICY_ERROR
    assert tool.calls == []
    assert ToolResult.model_validate_json(result.messages[-1].content).is_error


@pytest.mark.asyncio
async def test_tool_exception_is_surfaced_and_persisted() -> None:
    tool = FakeTool(
        name="echo",
        input_model=EchoArguments,
        outcomes=[RuntimeError("boom")],
    )
    service, _provider, _store, _tool, _policy = make_service(
        [tool_response("call-boom")], tool=tool
    )

    result = await service.respond("explode")

    assert result.status is RuntimeStatus.FAILED
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.TOOL_ERROR
    assert result.tool_iterations == 1
    assert len(tool.calls) == 1
    persisted = ToolResult.model_validate_json(result.messages[-1].content)
    assert persisted.is_error


@pytest.mark.asyncio
async def test_tool_iteration_limit_stops_repeated_calls() -> None:
    tool = FakeTool(name="echo", input_model=EchoArguments)
    service, provider, _store, _tool, policy = make_service(
        [tool_response("call-1"), tool_response("call-2")],
        tool=tool,
        max_tool_iterations=1,
    )

    result = await service.respond("loop")

    assert result.status is RuntimeStatus.LIMIT_REACHED
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.TOOL_ITERATION_LIMIT
    assert result.tool_iterations == 1
    assert len(provider.requests) == 2
    assert len(tool.calls) == 1
    assert len(policy.requests) == 1
    assert [message.role for message in result.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    limit_result = ToolResult.model_validate_json(result.messages[-1].content)
    assert limit_result.is_error
    assert limit_result.data == {"code": "tool_iteration_limit"}


@pytest.mark.asyncio
async def test_provider_exception_is_returned_as_clean_failure() -> None:
    service, _provider, _store, _tool, _policy = make_service(
        [RuntimeError("provider secret internals")]
    )

    result = await service.respond("hello")

    assert result.status is RuntimeStatus.FAILED
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.PROVIDER_ERROR
    assert "secret internals" not in result.error.message
    assert [message.role for message in result.messages] == [MessageRole.USER]


@pytest.mark.asyncio
async def test_missing_conversation_returns_failure_without_side_effects() -> None:
    service, provider, store, _tool, _policy = make_service([ProviderResponse(content="unused")])

    result = await service.respond("hello", conversation_id="missing")

    assert result.status is RuntimeStatus.FAILED
    assert result.conversation_id == "missing"
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.CONVERSATION_NOT_FOUND
    assert result.messages == ()
    assert provider.requests == []
    assert store.messages == {}


@pytest.mark.asyncio
async def test_store_failure_is_returned_without_leaking_exception() -> None:
    store = InMemoryConversationStore(fail_operations={"create_conversation"})
    service, provider, _store, _tool, _policy = make_service(
        [ProviderResponse(content="unused")], store=store
    )

    result = await service.respond("hello")

    assert result.status is RuntimeStatus.FAILED
    assert result.error is not None
    assert result.error.code is RuntimeErrorCode.STORE_ERROR
    assert "forced" not in result.error.message
    assert provider.requests == []


def test_request_and_provider_models_reject_ambiguous_payloads() -> None:
    with pytest.raises(ValidationError):
        AssistantRequest(user_input="   ")
    with pytest.raises(ValidationError):
        ProviderResponse.model_validate({"content": "", "tool_calls": []})
    with pytest.raises(ValidationError):
        ProviderResponse.model_validate(
            {
                "content": "valid",
                "unexpected": "not adapter-normalized",
            }
        )


def test_service_rejects_duplicate_tools_and_invalid_limits() -> None:
    provider = FakeChatProvider([])
    store = InMemoryConversationStore()
    policy = FakeToolPolicy()
    first = FakeTool(name="echo", input_model=EchoArguments)
    second = FakeTool(name="echo", input_model=EchoArguments)

    with pytest.raises(ValueError, match="duplicate tool name"):
        AssistantService(
            provider=provider,
            store=store,
            tools=[first, second],
            policy=policy,
        )
    with pytest.raises(ValueError, match="context_message_limit"):
        AssistantService(
            provider=provider,
            store=store,
            tools=[],
            policy=policy,
            context_message_limit=0,
        )
    with pytest.raises(ValueError, match="max_tool_iterations"):
        AssistantService(
            provider=provider,
            store=store,
            tools=[],
            policy=policy,
            max_tool_iterations=0,
        )


def test_tool_result_message_is_machine_readable_json() -> None:
    result = ToolResult(content="ok", data={"nested": [1, True, None]})

    payload = json.loads(result.model_dump_json())

    assert payload == {
        "content": "ok",
        "is_error": False,
        "data": {"nested": [1, True, None]},
    }
