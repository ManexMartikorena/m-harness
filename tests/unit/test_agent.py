"""The agent loop (spec hito 4, §1.7 and §4.4, and spec hito 5, §1.4 and
§4.2), with fakes."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from datetime import date
from decimal import Decimal
from typing import cast

import pytest

from mharness.application.agent import Agent
from mharness.application.tools import ToolRegistry
from mharness.domain.agent_events import (
    AgentEvent,
    ApprovalRequested,
    ModelCallFinished,
    ModelFallback,
    ModelRetry,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
    TurnStarted,
)
from mharness.domain.approval import ApprovalRequest, Decision
from mharness.domain.catalog import ModelInfo, Prices
from mharness.domain.errors import (
    ModelAuthError,
    ModelError,
    ModelRateLimitError,
    ModelRequestError,
    ModelResponseError,
    ModelUnavailableError,
)
from mharness.domain.events import TextDelta, ToolCallDelta
from mharness.domain.limits import TurnLimits
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.retry import NO_RETRIES, RetryPolicy
from mharness.domain.tools import ToolError
from mharness.ports.approval import ApprovalGate
from tests.fakes.approval import FakeApproval, HangingApproval
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import FAKE_MODEL, HANG, FakeModelClient, reply, tool_calls
from tests.fakes.tools import EchoParams, FakeTool

MODEL = "glm-5.3-flash"
PROVIDER = "opencode-go"


def call(id: str, text: str = "Hola", name: str = "echo") -> ToolCallBlock:
    return ToolCallBlock(id=id, name=name, arguments=f'{{"text": "{text}"}}')


def user(text: str) -> Message:
    return Message(role="user", blocks=[TextBlock(text=text)])


def agent(
    fake: FakeModelClient,
    *tools: FakeTool,
    max_steps: int = 25,
    gate: ApprovalGate | None = None,
    catalog: MemoryCatalog | None = None,
    limits: TurnLimits | None = None,
    retry: RetryPolicy = NO_RETRIES,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    fallback: str | None = None,
) -> Agent:
    registry = ToolRegistry(tools or [FakeTool()])
    # With no script, being asked fails the test.
    return Agent(
        fake,
        registry,
        gate=gate or FakeApproval(),
        model=MODEL,
        catalog=catalog or MemoryCatalog(),
        provider=PROVIDER,
        limits=limits or TurnLimits(max_steps=max_steps),
        # A failure in a script is one failure, unless a test says.
        retry=retry,
        sleep=sleep or asyncio.sleep,
        fallback=fallback,
    )


async def run(subject: Agent, text: str = "Hola") -> list[AgentEvent]:
    return [event async for event in subject.run(text)]


async def test_without_calls_the_turn_ends() -> None:
    usage = Usage(input_tokens=10, output_tokens=3)
    fake = FakeModelClient([reply("Hola, Ane.", usage=usage)])
    subject = agent(fake)

    events = await run(subject)

    assert events == [
        TurnStarted(text="Hola"),
        TextDelta(text="Hola,"),
        TextDelta(text=" Ane."),
        ModelCallFinished(usage=usage, model=FAKE_MODEL, cost=None),
        TurnFinished(reason="end_turn", usage=usage, tool_calls=0, steps=1, cost=None),
    ]
    assert subject.messages[0] == user("Hola")
    assert subject.messages[1].text == "Hola, Ane."


async def test_one_call_runs_and_its_result_goes_back() -> None:
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hecho.")])
    echo = FakeTool()

    events = await run(agent(fake, echo))

    result = ToolResultBlock(call_id="c1", content="echo: Hola")
    assert [type(e).__name__ for e in events] == [
        "TurnStarted",
        "ModelCallFinished",
        "ToolCallProposed",
        "ToolFinished",
        "TextDelta",
        "TextDelta",
        "ModelCallFinished",
        "TurnFinished",
    ]
    assert events[2] == ToolCallProposed(call=call("c1"))
    finished = events[3]
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
        reason="max_steps",
        usage=Usage(),
        tool_calls=3,
        steps=3,
        cost=None,
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
        cost=None,
    )


async def test_the_request_carries_the_tool_specs() -> None:
    fake = FakeModelClient([reply("Hola.")])
    registry = ToolRegistry([FakeTool("echo"), FakeTool("shout")])

    await run(
        Agent(
            fake,
            registry,
            gate=FakeApproval(),
            model=MODEL,
            catalog=MemoryCatalog(),
            provider=PROVIDER,
        )
    )

    assert fake.requests[0].tools == registry.specs()
    assert fake.requests[0].model == MODEL
    assert fake.requests[0].system is None


# Errors go back to the model (spec hito 4, §1.8).


async def first_result(
    model_call: ToolCallBlock, *tools: FakeTool, gate: FakeApproval | None = None
) -> tuple[ToolFinished, FakeModelClient]:
    fake = FakeModelClient([tool_calls(model_call), reply("Lo siento.")])
    events = await run(agent(fake, *tools, gate=gate))
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


async def test_a_result_that_is_not_text_is_an_internal_error() -> None:
    # A tool that breaks its contract (an MCP one, hito 17) does not cut the
    # turn (spec mejora-2026-10-26-deuda-pre-hito-6, B3).
    echo = FakeTool(results=[cast(str, None)])

    finished, _ = await first_result(call("c1"), echo)

    assert finished.result.content == 'error: internal error in tool "echo"'
    assert finished.internal_error == "run() returned NoneType, not str"


async def test_validation_errors_do_not_echo_the_input() -> None:
    finished, _ = await first_result(
        ToolCallBlock(id="c1", name="echo", arguments='{"text": ["secret-value"]}')
    )

    assert "secret-value" not in finished.result.content


# What ran is kept, also when the turn fails or is cancelled (spec hito 5,
# §1.5 and §4.2.7). With nothing run, nothing is kept (spec hito 4, §1.7).


def failed(id: str, text: str) -> ToolResultBlock:
    return ToolResultBlock(call_id=id, content=f"error: {text}", is_error=True)


async def until(condition: Callable[[], bool]) -> None:
    for _ in range(100):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError("the condition never held")


async def test_a_model_error_after_a_tool_keeps_the_turn_up_to_its_result() -> None:
    # 4.2.7: the half answer of step 2 is dropped.
    fake = FakeModelClient(
        [
            reply("Hola."),
            tool_calls(call("c1")),
            [TextDelta(text="Ya est"), ModelUnavailableError("down")],
        ]
    )
    subject = agent(fake)
    await run(subject, "Primero")
    before = subject.messages

    with pytest.raises(ModelUnavailableError):
        await run(subject, "Segundo")

    assert subject.messages == (
        *before,
        user("Segundo"),
        Message(role="assistant", blocks=[call("c1")]),
        Message(
            role="tool", blocks=[ToolResultBlock(call_id="c1", content="echo: Hola")]
        ),
    )


async def test_a_model_error_before_any_tool_leaves_the_history_as_it_was() -> None:
    # 4.2.7: no tool ran in step 1, only an invalid call.
    bad = ToolCallBlock(id="c1", name="echo", arguments="{}")
    fake = FakeModelClient(
        [reply("Hola."), tool_calls(bad), ModelUnavailableError("down")]
    )
    echo = FakeTool()
    subject = agent(fake, echo)
    await run(subject, "Primero")
    before = subject.messages

    with pytest.raises(ModelUnavailableError):
        await run(subject, "Segundo")

    assert subject.messages == before
    assert echo.calls == []


async def test_a_model_error_in_the_first_step_keeps_nothing() -> None:
    # 4.2.7
    subject = agent(FakeModelClient([ModelUnavailableError("down")]))

    with pytest.raises(ModelUnavailableError):
        await run(subject)

    assert subject.messages == ()


async def test_cancelling_during_the_second_of_three_calls_keeps_them_paired() -> None:
    # 4.2.7
    echo = FakeTool("echo")
    waiting = FakeTool("wait", gate=asyncio.Event())  # never set
    calls = [call("c1"), call("c2", name="wait"), call("c3")]
    fake = FakeModelClient([tool_calls(*calls)])
    subject = agent(fake, echo, waiting)

    task = asyncio.ensure_future(run(subject))
    await until(lambda: bool(waiting.calls))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert subject.messages == (
        user("Hola"),
        Message(role="assistant", blocks=[*calls]),
        Message(
            role="tool",
            blocks=[
                ToolResultBlock(call_id="c1", content="echo: Hola"),
                failed("c2", "cancelled by the user"),
                failed("c3", "not run"),
            ],
        ),
    )
    assert len(echo.calls) == 1


async def test_cancelling_during_the_only_call_keeps_it_as_cancelled() -> None:
    # D2: the tool had started, so the turn is kept.
    echo = FakeTool(gate=asyncio.Event())  # never set
    fake = FakeModelClient([tool_calls(call("c1"))])
    subject = agent(fake, echo)

    task = asyncio.ensure_future(run(subject))
    await until(lambda: bool(echo.calls))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert subject.messages == (
        user("Hola"),
        Message(role="assistant", blocks=[call("c1")]),
        Message(role="tool", blocks=[failed("c1", "cancelled by the user")]),
    )


async def test_cancelling_while_asking_after_a_run_keeps_the_turn() -> None:
    # D3: the call being approved was cancelled; the next one did not run.
    echo = FakeTool("echo")
    write = FakeTool("write", permission="effect", requests=[ask()])
    calls = [call("c1"), call("c2", name="write"), call("c3")]
    fake = FakeModelClient([tool_calls(*calls)])
    gate = HangingApproval()
    subject = Agent(
        fake,
        ToolRegistry([echo, write]),
        gate=gate,
        model=MODEL,
        catalog=MemoryCatalog(),
        provider=PROVIDER,
    )

    task = asyncio.ensure_future(run(subject))
    await until(lambda: bool(gate.requests))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert subject.messages[-1] == Message(
        role="tool",
        blocks=[
            ToolResultBlock(call_id="c1", content="echo: Hola"),
            failed("c2", "cancelled by the user"),
            failed("c3", "not run"),
        ],
    )
    assert write.calls == []


class BrokenApproval:
    """A gate that fails with an error nobody expects."""

    async def decide(self, request: ApprovalRequest) -> Decision:
        raise OSError(5, "Input/output error")


async def test_an_unexpected_error_after_a_run_keeps_the_turn() -> None:
    # Any exception, not only the expected ones (spec
    # mejora-2026-10-23-deuda-hito-5, E4): the model must know what ran.
    echo = FakeTool("echo")
    write = FakeTool("write", permission="effect", requests=[ask()])
    calls = [call("c1"), call("c2", name="write"), call("c3")]
    fake = FakeModelClient([tool_calls(*calls)])
    subject = Agent(
        fake,
        ToolRegistry([echo, write]),
        gate=BrokenApproval(),
        model=MODEL,
        catalog=MemoryCatalog(),
        provider=PROVIDER,
    )

    with pytest.raises(OSError, match="Input/output error"):
        await run(subject)
    assert subject.messages[-1] == Message(
        role="tool",
        blocks=[
            ToolResultBlock(call_id="c1", content="echo: Hola"),
            failed("c2", "interrupted by an internal error"),
            failed("c3", "not run"),
        ],
    )


async def test_cancelling_while_asking_before_any_run_keeps_nothing() -> None:
    write = FakeTool("write", permission="effect", requests=[ask()])
    fake = FakeModelClient([tool_calls(call("c1", name="write"))])
    gate = HangingApproval()
    subject = Agent(
        fake,
        ToolRegistry([write]),
        gate=gate,
        model=MODEL,
        catalog=MemoryCatalog(),
        provider=PROVIDER,
    )

    task = asyncio.ensure_future(run(subject))
    await until(lambda: bool(gate.requests))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert subject.messages == ()


async def test_closing_the_loop_after_a_run_keeps_the_turn() -> None:
    # Ctrl+C while the terminal is the one waiting: the loop gets
    # GeneratorExit at a yield, not CancelledError.
    calls = [call("c1"), call("c2"), call("c3")]
    fake = FakeModelClient([tool_calls(*calls)])
    subject = agent(fake)

    async with aclosing(subject.run("Hola")) as events:
        async for event in events:
            if isinstance(event, ToolFinished):
                break

    assert subject.messages[-1] == Message(
        role="tool",
        blocks=[
            ToolResultBlock(call_id="c1", content="echo: Hola"),
            failed("c2", "cancelled by the user"),
            failed("c3", "not run"),
        ],
    )


async def test_turn_is_kept_when_the_caller_stops_at_the_end() -> None:
    # Fixes decision 1.7: kept before TurnFinished is handed over.
    fake = FakeModelClient([reply("Hola, Ane.")])
    subject = agent(fake)

    async with aclosing(subject.run("Hola")) as events:
        async for event in events:
            if isinstance(event, TurnFinished):
                break

    assert len(subject.messages) == 2


async def test_closing_the_loop_after_a_denial_keeps_the_denial() -> None:
    calls = [call("c1"), call("c2", name="write"), call("c3")]
    fake = FakeModelClient([tool_calls(*calls)])
    write = FakeTool("write", permission="effect", requests=[ask()])
    subject = agent(fake, FakeTool("echo"), write, gate=FakeApproval(["deny"]))

    async with aclosing(subject.run("Hola")) as events:
        async for event in events:
            if isinstance(event, ToolFinished) and event.decision == "deny":
                break

    assert subject.messages[-1] == Message(
        role="tool",
        blocks=[
            ToolResultBlock(call_id="c1", content="echo: Hola"),
            failed("c2", "the user denied this call"),
            failed("c3", "not run: a previous call was denied"),
        ],
    )


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

    assert [type(e).__name__ for e in events[:5]] == [
        "TurnStarted",
        "ModelCallFinished",
        "ToolCallProposed",
        "ApprovalRequested",
        "ToolFinished",
    ]
    assert events[3] == ApprovalRequested(call=call("c1"), request=ask())
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
    assert [(f.result, f.decision, f.skipped) for f in finished(events)] == [
        (denied, "deny", False),
        (skipped[0], None, True),
        (skipped[1], None, True),
    ]
    # Every call is proposed, so the terminal shows each one with its result.
    proposed = [e.call.id for e in events if isinstance(e, ToolCallProposed)]
    assert proposed == ["c1", "c2", "c3"]
    assert len(gate.requests) == 1
    assert echo.calls == []
    # The calls skipped after the denial do not count.
    assert events[-1] == TurnFinished(
        reason="denied",
        usage=Usage(),
        tool_calls=1,
        steps=1,
        cost=None,
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
    gate = FakeApproval()

    done, _ = await first_result(call("c1"), echo, gate=gate)

    assert done.result == ToolResultBlock(
        call_id="c1", content='error: internal error in tool "echo"', is_error=True
    )
    assert done.internal_error == "effect tool without an approval request"
    assert done.decision is None
    assert gate.requests == []
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


@pytest.mark.parametrize("answer", [None, "y", ""])
async def test_an_invalid_decision_does_not_run_the_tool(answer: object) -> None:
    # Fails closed: only "once" or "session" run a call that asked. The cast
    # stands for a broken gate, which the type checker cannot rule out at
    # run time.
    fake = FakeModelClient(
        [tool_calls(call("c1")), tool_calls(call("c2")), reply("Ok")]
    )
    gate = FakeApproval(cast(list[Decision], [answer, "once"]))
    echo = FakeTool(permission="effect", requests=[ask(), ask()])

    events = await run(agent(fake, echo, gate=gate))

    first, second = finished(events)
    assert first.result == ToolResultBlock(
        call_id="c1", content='error: internal error in tool "echo"', is_error=True
    )
    assert first.internal_error == f"invalid approval decision: {answer!r}"
    assert first.decision is None
    # Nothing was kept for the session: the next call asks again.
    assert second.decision == "once"
    assert len(gate.requests) == 2
    assert echo.calls == [EchoParams(text="Hola")]
    # The turn goes on as usual.
    assert events[-1] == TurnFinished(
        reason="end_turn", usage=Usage(), tool_calls=2, steps=3, cost=None
    )


class BrokenSummary(FakeTool):
    """A tool whose summary fails after it ran."""

    def summary(self, result: str) -> str:
        raise ValueError("bad summary")


async def test_a_crash_in_summary_keeps_the_real_result() -> None:
    # The tool already ran: the model gets its real result, so it does not
    # run it again, and the terminal is told about the bug.
    echo = BrokenSummary()

    done, _ = await first_result(call("c1"), echo)

    assert done.result == ToolResultBlock(call_id="c1", content="echo: Hola")
    assert done.summary == "(no summary)"
    assert done.internal_error == "summary: ValueError: bad summary"
    assert echo.calls == [EchoParams(text="Hola")]


async def test_too_deeply_nested_arguments_are_not_valid_json() -> None:
    # json.loads raises RecursionError, not ValueError, on deep nesting.
    deep = '{"text": ' + "[" * 100_000

    done, _ = await first_result(ToolCallBlock(id="c1", name="echo", arguments=deep))

    assert done.result == ToolResultBlock(
        call_id="c1",
        content="error: arguments are not a valid JSON object",
        is_error=True,
    )


async def test_once_then_deny_in_one_answer_keeps_every_call_paired() -> None:
    calls = [call(f"c{i}") for i in range(1, 5)]
    fake = FakeModelClient([tool_calls(*calls)])
    gate = FakeApproval(["once", "deny"])
    echo = FakeTool(permission="effect", requests=[ask(None), ask(None)])
    subject = agent(fake, echo, gate=gate)

    events = await run(subject)

    results = [
        ToolResultBlock(call_id="c1", content="echo: Hola"),
        failed("c2", "the user denied this call"),
        failed("c3", "not run: a previous call was denied"),
        failed("c4", "not run: a previous call was denied"),
    ]
    assert [(f.result, f.decision) for f in finished(events)] == list(
        zip(results, ["once", "deny", None, None], strict=True)
    )
    assert echo.calls == [EchoParams(text="Hola")]
    assert events[-1] == TurnFinished(
        reason="denied", usage=Usage(), tool_calls=2, steps=1, cost=None
    )
    assert subject.messages == (
        user("Hola"),
        Message(role="assistant", blocks=[*calls]),
        Message(role="tool", blocks=[*results]),
    )


async def cancel_once(subject: Agent, seen: AgentEvent | None) -> None:
    """Run a turn and cancel it once `seen` arrives (or at once if None)."""
    events: list[AgentEvent] = []

    async def consume() -> None:
        async for event in subject.run("Hola"):
            events.append(event)

    task = asyncio.ensure_future(consume())
    if seen is None:
        await asyncio.sleep(0.01)
    else:
        await until(lambda: seen in events)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def cut(text: str) -> Message:
    return Message(role="assistant", blocks=[TextBlock(text=text)], interrupted=True)


async def test_cancelling_mid_stream_after_a_run_keeps_the_half_answer() -> None:
    # Spec hito 6, §1.7: it used to be dropped (spec hito 3, §1.6); now it
    # stays, marked, after the results of the tools that ran.
    fake = FakeModelClient([tool_calls(call("c1")), [TextDelta(text="Ya est"), HANG]])
    subject = agent(fake)

    await cancel_once(subject, TextDelta(text="Ya est"))

    assert subject.messages == (
        user("Hola"),
        Message(role="assistant", blocks=[call("c1")]),
        Message(
            role="tool", blocks=[ToolResultBlock(call_id="c1", content="echo: Hola")]
        ),
        cut("Ya est"),
    )


async def test_cancelling_mid_answer_keeps_the_question_and_the_half_answer() -> None:
    fake = FakeModelClient(
        [[TextDelta(text="La capital "), TextDelta(text="es"), HANG]]
    )
    subject = agent(fake)

    await cancel_once(subject, TextDelta(text="es"))

    assert subject.messages == (user("Hola"), cut("La capital es"))


async def test_cancelling_before_any_text_keeps_nothing() -> None:
    subject = agent(FakeModelClient([[HANG]]))

    await cancel_once(subject, None)

    assert subject.messages == ()


async def test_a_half_tool_call_is_dropped_with_the_text_kept() -> None:
    # It never ran: only the text the person saw stays.
    half = ToolCallDelta(index=0, id="c1", name="echo", arguments='{"te')
    fake = FakeModelClient([[TextDelta(text="Voy a mirar"), half, HANG]])
    subject = agent(fake)

    await cancel_once(subject, TextDelta(text="Voy a mirar"))

    assert subject.messages == (user("Hola"), cut("Voy a mirar"))


async def test_closing_the_loop_mid_answer_keeps_the_half_answer() -> None:
    # Ctrl+C while the terminal was the one waiting closes the loop.
    subject = agent(FakeModelClient([[TextDelta(text="Medio"), HANG]]))

    async with aclosing(subject.run("Hola")) as events:
        async for event in events:
            if event == TextDelta(text="Medio"):
                break

    assert subject.messages == (user("Hola"), cut("Medio"))


async def test_a_model_error_mid_answer_keeps_nothing() -> None:
    # The text may be broken: the turn is repeated, as before.
    fake = FakeModelClient([[TextDelta(text="Medio"), ModelUnavailableError("caído")]])
    subject = agent(fake)

    with pytest.raises(ModelUnavailableError):
        await run(subject)

    assert subject.messages == ()


# A resumed session: the history it starts with, and the model it uses
# (spec hito 6, §1.6 and §4.4).


async def test_the_history_given_goes_in_the_first_request() -> None:
    before = (
        user("Me llamo Ana"),
        Message(role="assistant", blocks=[TextBlock(text="Hola, Ana.")]),
    )
    fake = FakeModelClient([reply("Ana.")])
    subject = Agent(
        fake,
        ToolRegistry([FakeTool()]),
        gate=FakeApproval(),
        model=MODEL,
        catalog=MemoryCatalog(),
        provider=PROVIDER,
        history=before,
    )

    await run(subject, "¿Cómo me llamo?")

    assert fake.requests[0].messages == [*before, user("¿Cómo me llamo?")]
    assert subject.messages[:2] == before


async def test_changing_the_model_changes_the_next_request() -> None:
    fake = FakeModelClient([reply("Uno."), reply("Dos.")])
    subject = agent(fake)
    await run(subject)

    subject.model = "kimi-k3"
    await run(subject)

    assert [r.model for r in fake.requests] == [MODEL, "kimi-k3"]
    assert subject.model == "kimi-k3"


# Cost (spec hito 7, §1.5, §1.6 and §4.4).

CHECKED = date(2026, 10, 27)


def priced(model: str, input: str, output: str) -> ModelInfo:
    return ModelInfo(
        provider=PROVIDER,
        model=model,
        prices=Prices(input=Decimal(input), output=Decimal(output), checked=CHECKED),
    )


async def test_the_turn_starts_with_its_text() -> None:
    fake = FakeModelClient([reply("Hola")])

    events = await run(agent(fake), "Arregla el test")

    assert events[0] == TurnStarted(text="Arregla el test")


async def test_each_call_has_its_cost() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=100_000)
    fake = FakeModelClient([reply("Hola", usage=usage)])
    catalog = MemoryCatalog([priced(FAKE_MODEL, "0.15", "0.50")])

    events = await run(agent(fake, catalog=catalog))

    assert (
        ModelCallFinished(usage=usage, model=FAKE_MODEL, cost=Decimal("0.2")) in events
    )
    assert events[-1] == TurnFinished(
        reason="end_turn", usage=usage, tool_calls=0, steps=1, cost=Decimal("0.2")
    )


async def test_without_prices_there_is_no_cost() -> None:
    fake = FakeModelClient([reply("Hola", usage=Usage(input_tokens=10))])
    catalog = MemoryCatalog([ModelInfo(provider=PROVIDER, model=FAKE_MODEL)])

    events = await run(agent(fake, catalog=catalog))

    finished = [e for e in events if isinstance(e, ModelCallFinished)]
    assert finished[0].cost is None
    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert turn.cost is None


async def test_the_turn_cost_is_the_sum_of_its_calls() -> None:
    fake = FakeModelClient(
        [
            tool_calls(call("c1"), usage=Usage(input_tokens=1_000_000)),
            reply("Hecho", usage=Usage(input_tokens=2_000_000)),
        ]
    )
    catalog = MemoryCatalog([priced(FAKE_MODEL, "0.15", "0.50")])

    events = await run(agent(fake, catalog=catalog))

    costs = [e.cost for e in events if isinstance(e, ModelCallFinished)]
    assert costs == [Decimal("0.15"), Decimal("0.3")]
    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert turn.cost == Decimal("0.45")


async def test_one_call_without_price_leaves_the_turn_without_cost() -> None:
    # The second answer comes from a model the catalog does not know.
    fake = FakeModelClient(
        [
            tool_calls(call("c1"), usage=Usage(input_tokens=1_000_000)),
            reply("Hecho", usage=Usage(input_tokens=10), model="otro"),
        ]
    )
    catalog = MemoryCatalog([priced(FAKE_MODEL, "0.15", "0.50")])

    events = await run(agent(fake, catalog=catalog))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert turn.cost is None


async def test_the_cost_is_that_of_the_model_that_answered() -> None:
    fake = FakeModelClient(
        [reply("Hola", usage=Usage(input_tokens=1_000_000), model="kimi-k3")]
    )
    catalog = MemoryCatalog(
        [priced(MODEL, "0.15", "0.50"), priced("kimi-k3", "3.00", "15.00")]
    )

    events = await run(agent(fake, catalog=catalog))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert turn.cost == Decimal(3)


async def test_an_answering_model_unknown_falls_back_to_the_one_asked() -> None:
    # A provider may name the model its own way ("glm-5.3-flash-0926").
    fake = FakeModelClient(
        [reply("Hola", usage=Usage(input_tokens=1_000_000), model="glm-5.3-0926")]
    )
    catalog = MemoryCatalog([priced(MODEL, "0.15", "0.50")])

    events = await run(agent(fake, catalog=catalog))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert turn.cost == Decimal("0.15")


async def test_the_catalog_is_asked_for_this_provider() -> None:
    fake = FakeModelClient([reply("Hola", usage=Usage(input_tokens=1_000_000))])
    other = ModelInfo(
        provider="opencode-zen",
        model=FAKE_MODEL,
        prices=Prices(input=Decimal(1), output=Decimal(1), checked=CHECKED),
    )

    events = await run(agent(fake, catalog=MemoryCatalog([other])))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert turn.cost is None


async def test_a_known_model_without_prices_falls_back_to_the_one_asked() -> None:
    # The user's catalog knows the answering name, but not its price.
    fake = FakeModelClient(
        [reply("Hola", usage=Usage(input_tokens=1_000_000), model="glm-0926")]
    )
    catalog = MemoryCatalog(
        [
            ModelInfo(provider=PROVIDER, model="glm-0926"),
            priced(MODEL, "0.15", "0.50"),
        ]
    )

    events = await run(agent(fake, catalog=catalog))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert turn.cost == Decimal("0.15")


async def test_a_denied_turn_has_its_cost() -> None:
    fake = FakeModelClient(
        [tool_calls(call("c1"), usage=Usage(input_tokens=1_000_000))]
    )
    gate = FakeApproval(["deny"])
    echo = FakeTool(permission="effect", requests=[ask()])
    catalog = MemoryCatalog([priced(FAKE_MODEL, "0.15", "0.50")])

    events = await run(agent(fake, echo, gate=gate, catalog=catalog))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert (turn.reason, turn.cost) == ("denied", Decimal("0.15"))


async def test_a_turn_at_the_step_limit_has_its_cost() -> None:
    fake = FakeModelClient(
        [tool_calls(call("c1"), usage=Usage(input_tokens=1_000_000))] * 2
    )
    catalog = MemoryCatalog([priced(FAKE_MODEL, "0.15", "0.50")])

    events = await run(agent(fake, max_steps=2, catalog=catalog))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert (turn.reason, turn.cost) == ("max_steps", Decimal("0.3"))


def always_calls(usage: Usage, steps: int = 5) -> FakeModelClient:
    """A model that asks for a tool at every step, spending `usage`."""
    return FakeModelClient(
        [tool_calls(call(f"c{i}"), usage=usage) for i in range(steps)]
    )


async def test_the_token_limit_stops_before_the_call_that_would_pass_it() -> None:
    # Spec hito 8, §1.1: 600 + 600 reach 1000, so no third call; what ran
    # stays in the history.
    echo = FakeTool()
    fake = always_calls(Usage(input_tokens=500, output_tokens=100))
    subject = agent(fake, echo, limits=TurnLimits(max_tokens=1000))

    events = await run(subject)

    assert events[-1] == TurnFinished(
        reason="max_tokens",
        usage=Usage(input_tokens=1000, output_tokens=200),
        tool_calls=2,
        steps=2,
        cost=None,
    )
    assert len(fake.requests) == 2
    assert len(echo.calls) == 2
    assert [m.role for m in subject.messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]


async def test_the_cost_limit_stops_before_the_call_that_would_pass_it() -> None:
    # 0.15 per call: after two, 0.30 reaches 0.20.
    fake = always_calls(Usage(input_tokens=1_000_000))
    catalog = MemoryCatalog([priced(FAKE_MODEL, "0.15", "0.50")])
    limits = TurnLimits(max_cost=Decimal("0.20"))

    events = await run(agent(fake, catalog=catalog, limits=limits))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert (turn.reason, turn.steps, turn.cost) == ("max_cost", 2, Decimal("0.30"))


async def test_a_cost_limit_without_a_known_cost_stops_the_turn() -> None:
    # Decision 7: a limit of money that cannot be checked is not a limit.
    fake = always_calls(Usage(input_tokens=10))
    limits = TurnLimits(max_cost=Decimal(5))

    events = await run(agent(fake, limits=limits))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert (turn.reason, turn.steps, turn.cost) == ("max_cost", 1, None)
    assert len(fake.requests) == 1


async def test_a_turn_within_its_limits_ends_as_always() -> None:
    fake = FakeModelClient(
        [
            tool_calls(call("c1"), usage=Usage(input_tokens=1_000_000)),
            reply("Hecho", usage=Usage(input_tokens=1_000_000)),
        ]
    )
    catalog = MemoryCatalog([priced(FAKE_MODEL, "0.15", "0.50")])
    limits = TurnLimits(max_cost=Decimal(1), max_tokens=10_000_000)

    events = await run(agent(fake, catalog=catalog, limits=limits))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert (turn.reason, turn.steps) == ("end_turn", 2)


# The time limit of the turn (spec hito 8, §1.1): the loop stops waiting and
# ends the turn, keeping what ran, as Ctrl+C does.

LIMIT = TurnLimits(timeout=0.05)


async def test_the_time_limit_while_the_model_answers_keeps_nothing_new() -> None:
    subject = agent(FakeModelClient([[TextDelta(text="Ya est"), HANG]]), limits=LIMIT)

    events = await run(subject)

    assert events[-1] == TurnFinished(
        reason="timeout", usage=Usage(), tool_calls=0, steps=1, cost=Decimal(0)
    )
    # Nothing ran: the user writes again, as after Ctrl+C. The half answer
    # is not kept: its mark would say the user cut it.
    assert subject.messages == ()


async def test_the_time_limit_while_a_tool_runs_keeps_the_turn() -> None:
    echo = FakeTool(gate=asyncio.Event())
    subject = agent(FakeModelClient([tool_calls(call("c1"))]), echo, limits=LIMIT)

    events = await run(subject)

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert (turn.reason, turn.tool_calls, turn.steps) == ("timeout", 0, 1)
    *_, results = subject.messages
    assert results.blocks == [
        ToolResultBlock(
            call_id="c1", content="error: stopped by the time limit", is_error=True
        )
    ]


async def test_the_time_limit_while_asking_after_a_run_keeps_the_turn() -> None:
    fake = FakeModelClient([tool_calls(call("c1")), tool_calls(call("c2"), call("c3"))])
    # The first call is approved once, the second waits forever.
    effect = FakeTool(permission="effect", requests=[ask(), ask()])
    gate = OnceThenHang()

    subject = agent(fake, effect, gate=gate, limits=LIMIT)
    events = await run(subject)

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert (turn.reason, turn.tool_calls, turn.steps) == ("timeout", 1, 2)
    assert len(gate.requests) == 2
    *_, results = subject.messages
    assert [b.content for b in results.blocks] == [  # type: ignore[union-attr]
        "error: stopped by the time limit",
        "error: not run",
    ]


class OnceThenHang(HangingApproval):
    """Approves the first request; then never answers."""

    async def decide(self, request: ApprovalRequest) -> Decision:
        if not self.requests:
            self.requests.append(request)
            return "once"
        return await super().decide(request)


async def test_the_time_limit_is_for_the_whole_turn() -> None:
    # Three calls of 0.03 s each: no single wait passes 0.05, the turn does.
    class SlowTool(FakeTool):
        async def run(self, params: EchoParams) -> str:
            await asyncio.sleep(0.03)
            return await super().run(params)

    slow = SlowTool()
    fake = FakeModelClient([tool_calls(call(f"c{i}")) for i in range(3)])

    events = await run(agent(fake, slow, limits=LIMIT))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    # The first ran; the second was cut while it ran.
    assert (turn.reason, turn.tool_calls) == ("timeout", 1)
    assert len(fake.requests) == 2


async def test_a_timeout_of_the_tool_itself_is_not_the_turns() -> None:
    # A TimeoutError that the limit did not cause is the tool's failure.
    echo = FakeTool(results=[TimeoutError("slow server")])
    fake = FakeModelClient([tool_calls(call("c1")), reply("Vaya.")])

    events = await run(agent(fake, echo, limits=TurnLimits(timeout=10)))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert turn.reason == "end_turn"


async def test_the_cost_the_provider_gives_wins_over_the_catalog() -> None:
    # Spec hito 7, §1.5: exact also with prices by the hour or by tier.
    answer = reply("Hola", usage=Usage(input_tokens=1_000_000)).model_copy(
        update={"cost": Decimal("0.075")}
    )
    catalog = MemoryCatalog([priced(FAKE_MODEL, "0.15", "0.50")])

    events = await run(agent(FakeModelClient([answer]), catalog=catalog))

    finished_call = next(e for e in events if isinstance(e, ModelCallFinished))
    assert finished_call.cost == Decimal("0.075")


async def test_the_cost_the_provider_gives_needs_no_catalog() -> None:
    answer = reply("Hola").model_copy(update={"cost": Decimal("0.001")})

    events = await run(agent(FakeModelClient([answer])))

    turn = events[-1]
    assert isinstance(turn, TurnFinished)
    assert turn.cost == Decimal("0.001")


# Retries (spec hito 8, §1.14). The waits are recorded, never slept.
RETRY = RetryPolicy(random=lambda: 0.0)


class Waits:
    """A `sleep` that records how long the loop asked to wait."""

    def __init__(self) -> None:
        self.asked: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.asked.append(seconds)


def retries(events: list[AgentEvent]) -> list[ModelRetry]:
    return [event for event in events if isinstance(event, ModelRetry)]


@pytest.mark.parametrize(
    "error",
    [ModelRateLimitError("HTTP 429"), ModelUnavailableError("HTTP 503")],
)
async def test_a_call_that_may_pass_is_made_again(error: ModelError) -> None:
    fake = FakeModelClient([error, error, reply("Hola.")])
    waits = Waits()

    events = await run(agent(fake, retry=RETRY, sleep=waits))

    assert retries(events) == [
        ModelRetry(model=MODEL, attempt=1, max_retries=3, delay=1.0, error=str(error)),
        ModelRetry(model=MODEL, attempt=2, max_retries=3, delay=2.0, error=str(error)),
    ]
    assert waits.asked == [1.0, 2.0]
    assert len(fake.requests) == 3
    finished = events[-1]
    assert isinstance(finished, TurnFinished)
    assert (finished.reason, finished.steps) == ("end_turn", 1)


async def test_the_retry_is_told_before_its_wait() -> None:
    seen: list[str] = []

    async def sleep(seconds: float) -> None:
        seen.append("wait")

    subject = agent(
        FakeModelClient([ModelUnavailableError("down"), reply("Hola.")]),
        retry=RETRY,
        sleep=sleep,
    )
    async for event in subject.run("Hola"):
        seen.append(event.type)

    assert seen[:3] == ["turn_started", "model_retry", "wait"]


async def test_the_provider_says_how_long_to_wait() -> None:
    fake = FakeModelClient(
        [ModelRateLimitError("HTTP 429", retry_after=7.0), reply("Hola.")]
    )
    waits = Waits()

    await run(agent(fake, retry=RETRY, sleep=waits))

    assert waits.asked == [7.0]


async def test_when_the_retries_run_out_the_error_goes_up() -> None:
    error = ModelUnavailableError("down")
    fake = FakeModelClient([error] * 4)
    seen: list[AgentEvent] = []
    subject = agent(fake, retry=RETRY, sleep=Waits())

    async def consume() -> None:
        async for event in subject.run("Hola"):
            seen.append(event)

    with pytest.raises(ModelUnavailableError):
        await consume()

    assert [event.attempt for event in retries(seen)] == [1, 2, 3]
    assert len(fake.requests) == 4
    assert subject.messages == ()


@pytest.mark.parametrize(
    "error",
    [
        ModelAuthError("HTTP 401"),
        ModelRequestError("HTTP 400"),
        ModelResponseError("bad chunk"),
    ],
)
async def test_what_repeating_does_not_fix_is_not_retried(error: ModelError) -> None:
    fake = FakeModelClient([error])
    waits = Waits()

    with pytest.raises(type(error)):
        await run(agent(fake, retry=RETRY, sleep=waits))

    assert (len(fake.requests), waits.asked) == (1, [])


async def test_an_answer_that_began_is_not_made_again() -> None:
    # Its text was already shown (spec hito 3, §1.9).
    fake = FakeModelClient([[TextDelta(text="Ho"), ModelUnavailableError("cut")]])

    with pytest.raises(ModelUnavailableError):
        await run(agent(fake, retry=RETRY, sleep=Waits()))

    assert len(fake.requests) == 1


async def test_a_retry_in_a_later_step_keeps_the_turn_so_far() -> None:
    echo = FakeTool()
    fake = FakeModelClient(
        [tool_calls(call("c1")), ModelUnavailableError("down"), reply("Hecho.")]
    )
    subject = agent(fake, echo, retry=RETRY, sleep=Waits())

    events = await run(subject)

    finished = events[-1]
    assert isinstance(finished, TurnFinished)
    assert (finished.reason, finished.steps, finished.tool_calls) == ("end_turn", 2, 1)
    # The repeated call sends the same history.
    assert fake.requests[1] == fake.requests[2]


async def test_the_time_limit_cuts_the_wait() -> None:
    subject = agent(
        FakeModelClient([ModelUnavailableError("down")]),
        limits=TurnLimits(timeout=0.05),
        retry=RetryPolicy(base_delay=60.0),
    )

    events = await run(subject)

    finished = events[-1]
    assert isinstance(finished, TurnFinished)
    assert finished.reason == "timeout"
    assert subject.messages == ()


async def test_ctrl_c_cuts_the_wait() -> None:
    subject = agent(
        FakeModelClient([ModelUnavailableError("down")]),
        retry=RetryPolicy(base_delay=60.0),
    )
    seen: list[AgentEvent] = []

    async def consume() -> None:
        async for event in subject.run("Hola"):
            seen.append(event)

    task = asyncio.ensure_future(consume())
    await until(lambda: bool(retries(seen)))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert subject.messages == ()


# The fallback model (spec hito 8, §1.14).
FALLBACK = "glm-5.3"


async def test_when_the_retries_run_out_the_fallback_answers() -> None:
    down = ModelUnavailableError("HTTP 503")
    fake = FakeModelClient([down] * 4 + [reply("Hola.", model=FALLBACK)])

    events = await run(agent(fake, retry=RETRY, sleep=Waits(), fallback=FALLBACK))

    switches = [event for event in events if isinstance(event, ModelFallback)]
    assert switches == [ModelFallback(model=MODEL, fallback=FALLBACK, error="HTTP 503")]
    assert [request.model for request in fake.requests] == [MODEL] * 4 + [FALLBACK]
    finished = events[-1]
    assert isinstance(finished, TurnFinished)
    assert finished.reason == "end_turn"


async def test_the_fallback_answers_the_rest_of_the_turn_and_not_the_next() -> None:
    echo = FakeTool()
    down = ModelRateLimitError("HTTP 429")
    fake = FakeModelClient(
        [down, tool_calls(call("c1")), reply("Hecho."), reply("Otra.")]
    )
    subject = agent(fake, echo, retry=NO_RETRIES, fallback=FALLBACK)

    await run(subject)
    await run(subject, "Otra vez")

    assert [request.model for request in fake.requests] == [
        MODEL,
        FALLBACK,
        FALLBACK,
        MODEL,
    ]
    assert subject.model == MODEL


async def test_the_fallback_has_its_own_retries() -> None:
    down = ModelUnavailableError("down")
    fake = FakeModelClient([down] * 8)
    seen: list[AgentEvent] = []
    subject = agent(fake, retry=RETRY, sleep=Waits(), fallback=FALLBACK)

    async def consume() -> None:
        async for event in subject.run("Hola"):
            seen.append(event)

    with pytest.raises(ModelUnavailableError):
        await consume()

    assert [(e.model, e.attempt) for e in retries(seen)] == [
        (MODEL, 1),
        (MODEL, 2),
        (MODEL, 3),
        (FALLBACK, 1),
        (FALLBACK, 2),
        (FALLBACK, 3),
    ]
    assert len(fake.requests) == 8


async def test_what_repeating_does_not_fix_does_not_fall_back() -> None:
    fake = FakeModelClient([ModelAuthError("HTTP 401")])

    with pytest.raises(ModelAuthError):
        await run(agent(fake, retry=NO_RETRIES, fallback=FALLBACK))

    assert len(fake.requests) == 1


async def test_a_fallback_that_is_the_model_in_use_is_not_one() -> None:
    fake = FakeModelClient([ModelUnavailableError("down")])

    with pytest.raises(ModelUnavailableError):
        await run(agent(fake, retry=NO_RETRIES, fallback=MODEL))

    assert len(fake.requests) == 1


async def test_the_fallback_is_priced_as_itself() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=0)
    # The provider names the model its own way: the price is the fallback's.
    fake = FakeModelClient(
        [ModelUnavailableError("down"), reply("Hola.", usage=usage, model="other")]
    )
    catalog = MemoryCatalog([priced(MODEL, "1", "1"), priced(FALLBACK, "2", "8")])
    subject = agent(fake, retry=NO_RETRIES, fallback=FALLBACK, catalog=catalog)

    events = await run(subject)

    finished = events[-1]
    assert isinstance(finished, TurnFinished)
    assert finished.cost == Decimal("2")
