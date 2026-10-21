"""The agent loop (spec hito 4, §1.7 and §4.4, and spec hito 5, §1.4 and
§4.2), with fakes."""

import asyncio
from contextlib import aclosing

import pytest

from mharness.application.agent import Agent
from mharness.application.tools import ToolRegistry
from mharness.domain.agent_events import (
    AgentEvent,
    ApprovalRequested,
    ModelCallFinished,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
)
from mharness.domain.approval import ApprovalRequest
from mharness.domain.errors import ModelUnavailableError
from mharness.domain.events import TextDelta
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.tools import ToolError
from tests.fakes.approval import FakeApproval
from tests.fakes.model import FAKE_MODEL, FakeModelClient, reply, tool_calls
from tests.fakes.tools import EchoParams, FakeTool

MODEL = "glm-5.3-flash"


def call(id: str, text: str = "Hola", name: str = "echo") -> ToolCallBlock:
    return ToolCallBlock(id=id, name=name, arguments=f'{{"text": "{text}"}}')


def user(text: str) -> Message:
    return Message(role="user", blocks=[TextBlock(text=text)])


def agent(
    fake: FakeModelClient,
    *tools: FakeTool,
    max_steps: int = 25,
    gate: FakeApproval | None = None,
) -> Agent:
    registry = ToolRegistry(tools or [FakeTool()])
    # With no script, being asked fails the test.
    return Agent(
        fake, registry, gate=gate or FakeApproval(), model=MODEL, max_steps=max_steps
    )


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
        TurnFinished(reason="end_turn", usage=usage, tool_calls=0, steps=1),
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

    assert events[-1] == TurnFinished(
        reason="max_steps", usage=Usage(), tool_calls=3, steps=3
    )
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
        steps=2,
    )


async def test_the_request_carries_the_tool_specs() -> None:
    fake = FakeModelClient([reply("Hola.")])
    registry = ToolRegistry([FakeTool("echo"), FakeTool("shout")])

    await run(Agent(fake, registry, gate=FakeApproval(), model=MODEL))

    assert fake.requests[0].tools == registry.specs()
    assert fake.requests[0].model == MODEL
    assert fake.requests[0].system is None


# Errors go back to the model (spec hito 4, §1.8).


async def first_result(
    model_call: ToolCallBlock, *tools: FakeTool
) -> tuple[ToolFinished, FakeModelClient]:
    fake = FakeModelClient([tool_calls(model_call), reply("Lo siento.")])
    events = await run(agent(fake, *tools))
    finished = next(e for e in events if isinstance(e, ToolFinished))
    # The loop went on: the model was called again, with the error.
    assert fake.requests[1].messages[-1] == Message(
        role="tool", blocks=[finished.result]
    )
    return finished, fake


@pytest.mark.parametrize(
    ("model_call", "expected"),
    [
        (
            ToolCallBlock(id="c1", name="read", arguments="{}"),
            'error: unknown tool "read". Available: echo',
        ),
        (
            ToolCallBlock(id="c1", name="echo", arguments='{"text": '),
            "error: arguments are not a valid JSON object",
        ),
        (
            ToolCallBlock(id="c1", name="echo", arguments='["Hola"]'),
            "error: arguments are not a valid JSON object",
        ),
        (
            ToolCallBlock(id="c1", name="echo", arguments='{"text": 3}'),
            "error: invalid arguments: text: Input should be a valid string",
        ),
        (
            ToolCallBlock(id="c1", name="echo", arguments=""),
            "error: invalid arguments: text: Field required",
        ),
    ],
)
async def test_bad_calls_become_error_results(
    model_call: ToolCallBlock, expected: str
) -> None:
    finished, _ = await first_result(model_call)

    assert finished.result == ToolResultBlock(
        call_id="c1", content=expected, is_error=True
    )
    assert finished.summary == expected
    assert finished.internal_error is None


async def test_a_tool_error_becomes_an_error_result() -> None:
    echo = FakeTool(results=[ToolError("file not found: notas.txt")])

    finished, _ = await first_result(call("c1"), echo)

    assert finished.result.content == "error: file not found: notas.txt"
    assert finished.result.is_error


async def test_a_crash_is_hidden_from_the_model_but_reported() -> None:
    echo = FakeTool(results=[KeyError("boom")])

    finished, _ = await first_result(call("c1"), echo)

    assert finished.result.content == 'error: internal error in tool "echo"'
    assert finished.internal_error == "KeyError: 'boom'"


async def test_validation_errors_do_not_echo_the_input() -> None:
    finished, _ = await first_result(
        ToolCallBlock(id="c1", name="echo", arguments='{"text": ["secret-value"]}')
    )

    assert "secret-value" not in finished.result.content


# A failed or cancelled turn is not kept (spec hito 4, §1.7).


async def test_a_model_error_mid_turn_leaves_the_history_as_it_was() -> None:
    fake = FakeModelClient(
        [reply("Hola."), tool_calls(call("c1")), ModelUnavailableError("down")]
    )
    subject = agent(fake)
    await run(subject, "Primero")
    before = subject.messages

    with pytest.raises(ModelUnavailableError):
        await run(subject, "Segundo")

    assert subject.messages == before


async def test_cancelling_during_a_tool_leaves_the_history_as_it_was() -> None:
    gate = asyncio.Event()  # never set: the tool waits until cancelled
    echo = FakeTool(gate=gate)
    fake = FakeModelClient([tool_calls(call("c1"))])
    subject = agent(fake, echo)

    task = asyncio.ensure_future(run(subject))
    for _ in range(100):
        if echo.calls:
            break
        await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert echo.calls  # the tool had started
    assert subject.messages == ()


async def test_turn_is_kept_when_the_caller_stops_at_the_end() -> None:
    # Fixes decision 1.7: kept before TurnFinished is handed over.
    fake = FakeModelClient([reply("Hola, Ane.")])
    subject = agent(fake)

    async with aclosing(subject.run("Hola")) as events:
        async for event in events:
            if isinstance(event, TurnFinished):
                break

    assert len(subject.messages) == 2


# The loop asks before running a call (spec hito 5, §1.2 and §1.4).


def ask(scope: str | None = "echo") -> ApprovalRequest:
    return ApprovalRequest(tool="echo", title="echo Hola", detail="", scope=scope)


def finished(events: list[AgentEvent]) -> list[ToolFinished]:
    return [e for e in events if isinstance(e, ToolFinished)]


async def test_a_read_tool_without_a_request_does_not_ask() -> None:
    # 4.2.1
    fake = FakeModelClient([tool_calls(call("c1")), reply("Ok")])
    gate = FakeApproval()
    echo = FakeTool()

    events = await run(agent(fake, echo, gate=gate))

    assert gate.requests == []
    assert not any(isinstance(e, ApprovalRequested) for e in events)
    assert finished(events)[0].decision is None
    assert echo.calls == [EchoParams(text="Hola")]


async def test_once_asks_first_and_runs() -> None:
    # 4.2.2
    fake = FakeModelClient([tool_calls(call("c1")), reply("Ok")])
    gate = FakeApproval(["once"])
    echo = FakeTool(permission="effect", requests=[ask()])

    events = await run(agent(fake, echo, gate=gate))

    assert [type(e).__name__ for e in events[:4]] == [
        "ModelCallFinished",
        "ToolCallProposed",
        "ApprovalRequested",
        "ToolFinished",
    ]
    assert events[2] == ApprovalRequested(call=call("c1"), request=ask())
    done = finished(events)[0]
    assert done.decision == "once"
    assert done.result == ToolResultBlock(call_id="c1", content="echo: Hola")
    assert gate.requests == [ask()]
    assert echo.calls == [EchoParams(text="Hola")]


async def test_session_covers_the_same_scope_without_asking() -> None:
    # 4.2.3, same scope: the second call runs with decision None.
    fake = FakeModelClient(
        [tool_calls(call("c1")), tool_calls(call("c2")), reply("Ok")]
    )
    gate = FakeApproval(["session"])
    echo = FakeTool(permission="effect", requests=[ask(), ask()])

    events = await run(agent(fake, echo, gate=gate))

    assert [f.decision for f in finished(events)] == ["session", None]
    assert sum(isinstance(e, ApprovalRequested) for e in events) == 1
    assert len(echo.calls) == 2


async def test_session_lasts_for_the_next_turns() -> None:
    fake = FakeModelClient(
        [tool_calls(call("c1")), reply("Ok"), tool_calls(call("c2")), reply("Ok")]
    )
    gate = FakeApproval(["session"])
    echo = FakeTool(permission="effect", requests=[ask(), ask()])
    subject = agent(fake, echo, gate=gate)
    await run(subject, "Primero")

    events = await run(subject, "Segundo")

    assert finished(events)[0].decision is None
    assert len(gate.requests) == 1
    assert len(echo.calls) == 2


async def test_session_does_not_cover_another_scope() -> None:
    # 4.2.3, another scope.
    fake = FakeModelClient([tool_calls(call("c1"), call("c2")), reply("Ok")])
    gate = FakeApproval(["session", "once"])
    echo = FakeTool(permission="effect", requests=[ask("write"), ask("edit")])

    events = await run(agent(fake, echo, gate=gate))

    assert [f.decision for f in finished(events)] == ["session", "once"]
    assert gate.requests == [ask("write"), ask("edit")]


async def test_without_a_scope_it_always_asks() -> None:
    # 4.2.3, scope None: never kept for the session.
    fake = FakeModelClient([tool_calls(call("c1"), call("c2")), reply("Ok")])
    gate = FakeApproval(["session", "session"])
    echo = FakeTool(permission="effect", requests=[ask(None), ask(None)])

    events = await run(agent(fake, echo, gate=gate))

    assert [f.decision for f in finished(events)] == ["session", "session"]
    assert len(gate.requests) == 2


async def test_deny_ends_the_turn_without_calling_the_model() -> None:
    # 4.2.4. Only one answer is scripted: another call to the model fails.
    fake = FakeModelClient([tool_calls(call("c1"), call("c2"), call("c3"))])
    gate = FakeApproval(["deny"])
    echo = FakeTool(permission="effect", requests=[ask(), ask(), ask()])
    subject = agent(fake, echo, gate=gate)

    events = await run(subject)

    denied = ToolResultBlock(
        call_id="c1", content="error: the user denied this call", is_error=True
    )
    not_run = "error: not run: a previous call was denied"
    skipped = [
        ToolResultBlock(call_id=id, content=not_run, is_error=True)
        for id in ("c2", "c3")
    ]
    assert [(f.result, f.decision) for f in finished(events)] == [
        (denied, "deny"),
        (skipped[0], None),
        (skipped[1], None),
    ]
    # Every call is proposed, so the terminal shows each one with its result.
    proposed = [e.call.id for e in events if isinstance(e, ToolCallProposed)]
    assert proposed == ["c1", "c2", "c3"]
    assert len(gate.requests) == 1
    assert echo.calls == []
    # The calls skipped after the denial do not count.
    assert events[-1] == TurnFinished(
        reason="denied", usage=Usage(), tool_calls=1, steps=1
    )
    assert len(fake.requests) == 1
    # The turn is kept: the next turn, the model knows it was denied.
    assert subject.messages == (
        user("Hola"),
        Message(role="assistant", blocks=[call("c1"), call("c2"), call("c3")]),
        Message(role="tool", blocks=[denied, *skipped]),
    )


async def test_an_effect_tool_without_a_request_does_not_run() -> None:
    # 4.2.5 and §1.2: an effect always asks; without a request it is a bug
    # of ours.
    echo = FakeTool(permission="effect")

    done, _ = await first_result(call("c1"), echo)

    assert done.result == ToolResultBlock(
        call_id="c1", content='error: internal error in tool "echo"', is_error=True
    )
    assert done.internal_error == "effect tool without an approval request"
    assert done.decision is None
    assert echo.calls == []


async def test_a_tool_error_in_approval_is_an_error_result_without_asking() -> None:
    # 4.2.6. The default gate fails the test if asked.
    echo = FakeTool(permission="effect", requests=[ToolError("text not found")])

    done, _ = await first_result(call("c1"), echo)

    assert done.result == ToolResultBlock(
        call_id="c1", content="error: text not found", is_error=True
    )
    assert done.internal_error is None
    assert echo.calls == []


async def test_a_crash_in_approval_is_an_internal_error() -> None:
    echo = FakeTool(permission="effect", requests=[KeyError("boom")])

    done, _ = await first_result(call("c1"), echo)

    assert done.result.content == 'error: internal error in tool "echo"'
    assert done.internal_error == "KeyError: 'boom'"
    assert echo.calls == []
