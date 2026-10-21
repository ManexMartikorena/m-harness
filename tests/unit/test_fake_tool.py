import pytest

from mharness.domain.tools import ToolError
from mharness.ports.tools import Tool
from tests.fakes.tools import EchoParams, FakeTool


def test_fake_tool_satisfies_the_port() -> None:
    # mypy checks this assignment against the Protocol.
    tool: Tool[EchoParams] = FakeTool()

    assert tool.permission == "read"


async def test_echoes_and_keeps_the_calls() -> None:
    tool = FakeTool()

    assert await tool.run(EchoParams(text="Hola")) == "echo: Hola"
    assert tool.calls == [EchoParams(text="Hola")]


async def test_returns_and_raises_the_script() -> None:
    tool = FakeTool(results=["uno", ToolError("not found")])

    assert await tool.run(EchoParams(text="a")) == "uno"
    with pytest.raises(ToolError, match="not found"):
        await tool.run(EchoParams(text="b"))
