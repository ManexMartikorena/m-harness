import pytest

from mharness.application.tools import ToolRegistry
from mharness.domain.model import ToolSpec
from tests.fakes.tools import EchoParams, FakeTool


def test_specs_come_from_the_pydantic_model() -> None:
    registry = ToolRegistry([FakeTool("echo"), FakeTool("shout")])

    assert registry.specs() == [
        ToolSpec(
            name="echo",
            description="Echo a text (echo).",
            input_schema=EchoParams.model_json_schema(),
        ),
        ToolSpec(
            name="shout",
            description="Echo a text (shout).",
            input_schema=EchoParams.model_json_schema(),
        ),
    ]
    assert registry.names() == ["echo", "shout"]


def test_finds_a_tool_by_name() -> None:
    echo = FakeTool("echo")
    registry = ToolRegistry([echo])

    assert registry.get("echo") is echo
    assert registry.get("missing") is None


def test_a_name_registered_twice_fails() -> None:
    with pytest.raises(ValueError, match="registered twice"):
        ToolRegistry([FakeTool("echo"), FakeTool("echo")])


def test_an_effect_tool_is_refused() -> None:
    # Fixes decision 1.5: nothing can approve an effect until hito 5.
    with pytest.raises(ValueError, match="only read tools"):
        ToolRegistry([FakeTool("write", permission="effect")])


def test_empty_registry() -> None:
    registry = ToolRegistry()

    assert registry.specs() == []
    assert registry.names() == []
