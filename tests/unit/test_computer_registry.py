from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from jarvis.computer.actions import PreparedAction
from jarvis.computer.registry import BrokeredActionTool, ComputerActionRegistry
from jarvis.core import PermissionLevel
from tests.fakes.phase3 import FakeActionHandler, action_definition


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


class FakeCanonicalHandler(FakeActionHandler):
    @property
    def input_model(self) -> type[BaseModel]:
        return Arguments

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        parsed = Arguments.model_validate(arguments)
        return PreparedAction(
            normalized_arguments={"value": parsed.value},
            human_effect="Apply fake effect.",
            recovery_limits="Fake rollback only.",
        )


def test_brokered_adapter_exposes_schema_but_never_mutates() -> None:
    handler = FakeCanonicalHandler(action_definition(PermissionLevel.LEVEL_1))
    adapter = BrokeredActionTool(handler)

    assert adapter.definition == handler.definition.tool
    assert adapter.input_model == handler.input_model


async def test_brokered_adapter_direct_invoke_is_inert() -> None:
    handler = FakeCanonicalHandler(action_definition(PermissionLevel.LEVEL_1))
    adapter = BrokeredActionTool(handler)
    arguments = handler.input_model.model_validate({"value": "safe"})

    result = await adapter.invoke(arguments)

    assert result.is_error is True
    assert result.data == {"code": "broker_required"}
    assert handler.execute_calls == 0


def test_registry_is_fixed_unique_and_looks_up_only_exact_names() -> None:
    first = FakeCanonicalHandler(action_definition(PermissionLevel.LEVEL_1, name="first"))
    second = FakeCanonicalHandler(action_definition(PermissionLevel.LEVEL_2, name="second"))
    registry = ComputerActionRegistry((first, second))

    assert registry.action("first") is first
    assert registry.action("FIRST") is None
    assert registry.tool("second") is not None
    assert [tool.definition.name for tool in registry.model_tools] == ["first", "second"]
    assert registry.required_capabilities == ("computer.test",)


def test_registry_rejects_empty_and_duplicate_actions() -> None:
    handler = FakeCanonicalHandler(action_definition(PermissionLevel.LEVEL_1, name="same"))
    try:
        ComputerActionRegistry(())
    except ValueError as error:
        assert "at least one" in str(error)
    else:
        raise AssertionError("empty registry must fail")

    try:
        ComputerActionRegistry((handler, handler))
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate registry must fail")
