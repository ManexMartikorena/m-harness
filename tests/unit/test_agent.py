"""The agent loop (spec hito 4, §1.7 and §4.4), with fakes."""

from mharness.application.agent import Agent
from mharness.application.tools import ToolRegistry
from mharness.domain.agent_events import (
    AgentEvent,
    ModelCallFinished,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
)
from mharness.domain.events import TextDelta
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from tests.fakes.model import FAKE_MODEL, FakeModelClient, reply, tool_calls
from tests.fakes.tools import EchoParams, FakeTool

MODEL = "glm-5.3-flash"


def call(id: str, text: str = "Hola", name: str = "echo") -> ToolCallBlock:
    return ToolCallBlock(id=id, name=name, arguments=f'{{"text": "{text}"}}')


def user(text: str) -> Message:
    return Message(role="user", blocks=[TextBlock(text=text)])


def agent(fake: FakeModelClient, *tools: FakeTool, max_steps: int = 25) -> Agent:
    registry = ToolRegistry(tools or [FakeTool()])
    return Agent(fake, registry, model=MODEL, max_steps=max_steps)


async def run(subject: Agent, text: str = "Hola") -> list[AgentEvent]:
    return [event async for event in subject.run(text)]


async def test_without_calls_the_turn_ends() -> None:
    usage = Usage(input_tokens=10, output_tokens=3)
    fake = FakeModelClient([reply("Hola, Ane.", usage=usage)])
    subject = agent(fake)

    events = await run(subject)

    assert events == [
        TextDelta(text="Hola,"),
        TextDelta(text=" Ane."),
        ModelCallFinished(usage=usage, model=FAKE_MODEL),
        TurnFinished(reason="end_turn", usage=usage, tool_calls=0),
    ]
    assert subject.messages[0] == user("Hola")
    assert subject.messages[1].text == "Hola, Ane."


async def test_one_call_runs_and_its_result_goes_back() -> None:
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hecho.")])
    echo = FakeTool()

    events = await run(agent(fake, echo))

    result = ToolResultBlock(call_id="c1", content="echo: Hola")
    assert [type(e).__name__ for e in events] == [
        "ModelCallFinished",
        "ToolCallProposed",
        "ToolFinished",
        "TextDelta",
        "TextDelta",
        "ModelCallFinished",
        "TurnFinished",
    ]
    assert events[1] == ToolCallProposed(call=call("c1"))
    finished = events[2]
    assert isinstance(finished, ToolFinished)
    assert (finished.result, finished.summary) == (result, "10 chars")
    # The second step sends the call and its result.
    assert fake.requests[1].messages == [
        user("Hola"),
        Message(role="assistant", blocks=[call("c1")]),
        Message(role="tool", blocks=[result]),
    ]


async def test_two_calls_in_one_answer_run_in_order() -> None:
    fake = FakeModelClient(
        [tool_calls(call("c1", "uno"), call("c2", "dos")), reply("Ok")]
    )
    echo = FakeTool()

    await run(agent(fake, echo))

    assert echo.calls == [EchoParams(text="uno"), EchoParams(text="dos")]
    assert fake.requests[1].messages[-1] == Message(
        role="tool",
        blocks=[
            ToolResultBlock(call_id="c1", content="echo: uno"),
            ToolResultBlock(call_id="c2", content="echo: dos"),
        ],
    )


async def test_the_tool_gets_validated_params() -> None:
    fake = FakeModelClient([tool_calls(call("c1", "Ane")), reply("Ok")])
    echo = FakeTool()

    await run(agent(fake, echo))

    assert echo.calls == [EchoParams(text="Ane")]


async def test_the_step_limit_ends_the_turn_and_keeps_it() -> None:
    # A model that always asks for a tool.
    fake = FakeModelClient([tool_calls(call(f"c{i}")) for i in range(3)])
    subject = agent(fake, max_steps=3)

    events = await run(subject)

    assert events[-1] == TurnFinished(reason="max_steps", usage=Usage(), tool_calls=3)
    assert len(fake.requests) == 3
    assert subject.messages[-1].role == "tool"
    assert len(subject.messages) == 7  # user, then 3 times assistant and tool


async def test_next_turn_carries_calls_and_results() -> None:
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hecho."), reply("Sí.")])
    subject = agent(fake)
    await run(subject, "Primero")

    await run(subject, "Segundo")

    roles = [message.role for message in fake.requests[2].messages]
    assert roles == ["user", "assistant", "tool", "assistant", "user"]


async def test_turn_usage_adds_every_step() -> None:
    fake = FakeModelClient(
        [
            tool_calls(call("c1"), usage=Usage(input_tokens=100, output_tokens=20)),
            reply("Hecho.", usage=Usage(input_tokens=130, output_tokens=8)),
        ]
    )

    *_, finished = await run(agent(fake))

    assert finished == TurnFinished(
        reason="end_turn",
        usage=Usage(input_tokens=230, output_tokens=28),
        tool_calls=1,
    )


async def test_the_request_carries_the_tool_specs() -> None:
    fake = FakeModelClient([reply("Hola.")])
    registry = ToolRegistry([FakeTool("echo"), FakeTool("shout")])

    await run(Agent(fake, registry, model=MODEL))

    assert fake.requests[0].tools == registry.specs()
    assert fake.requests[0].model == MODEL
    assert fake.requests[0].system is None
