"""Archiving in the loop (spec hito 11, §1.10, and §4, tests 9, 10 and 11).

With a budget of 10,000 and no known window, the ceiling is 5,000 tokens
and the tail 1,500: each step below, a call and its result of 4,000
characters each, is some 2,000 tokens.
"""

import asyncio
import json

import pytest

from mharness.application.agent import Agent
from mharness.application.context import Archivist
from mharness.application.tools import ToolRegistry
from mharness.domain.agent_events import (
    AgentEvent,
    ContextArchived,
    ContextArchiving,
    ModelCallFinished,
    TurnFinished,
)
from mharness.domain.context import ContextPolicy
from mharness.domain.errors import ContextOverflowError
from mharness.domain.limits import TurnLimits
from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.session import check_history
from tests.fakes.approval import FakeApproval
from tests.fakes.archive import MemoryArchive
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import HANG, FakeModelClient, reply, tool_calls
from tests.fakes.retry import NO_RETRIES
from tests.fakes.tools import FakeTool
from tests.unit.test_agent import until

MODEL = "glm-5.3-flash"
BUDGET = 10_000
BIG = "palabra " * 500
NOTES = json.dumps({"summary": "msg-1 a msg-5: leyó", "index": "index one"})
ARCHIVIST_USAGE = Usage(input_tokens=3_000, output_tokens=200)


def big_call(id: str) -> ToolCallBlock:
    return ToolCallBlock(id=id, name="echo", arguments=json.dumps({"text": BIG}))


def user(text: str) -> Message:
    return Message(role="user", blocks=[TextBlock(text=text)])


def old_step(id: str) -> list[Message]:
    return [
        Message(role="assistant", blocks=[big_call(id)]),
        Message(role="tool", blocks=[ToolResultBlock(call_id=id, content=BIG)]),
    ]


HISTORY = [user("lee los ficheros"), *old_step("h1"), *old_step("h2")]


def archivist(fake: FakeModelClient) -> Archivist:
    return Archivist(
        fake,
        model="small",
        template="{{instructions}}{{previous}}|{{conversation}}",
        catalog=MemoryCatalog(),
        provider="opencode-go",
    )


def agent(
    fake: FakeModelClient,
    *,
    notes: FakeModelClient | None = None,
    history: list[Message] | None = None,
    budget: int = BUDGET,
    archive: MemoryArchive | None = None,
    catalog: MemoryCatalog | None = None,
) -> Agent:
    subject = Agent(
        fake,
        ToolRegistry([FakeTool()]),
        gate=FakeApproval(),
        model=MODEL,
        catalog=catalog or MemoryCatalog(),
        provider="opencode-go",
        history=history or [],
        retry=NO_RETRIES,
        context_budget=budget,
        archivist=archivist(notes) if notes is not None else None,
    )
    subject.archive = archive if archive is not None else MemoryArchive()
    return subject


async def run(subject: Agent, text: str = "Hola") -> list[AgentEvent]:
    return [event async for event in subject.run(text)]


def four_steps() -> FakeModelClient:
    return FakeModelClient(
        [tool_calls(big_call(f"c{n}")) for n in range(1, 5)] + [reply("Hecho.")]
    )


def is_index(message: Message) -> bool:
    return message.role == "user" and message.text.startswith("<context-archive>")


async def test_the_policy_of_these_tests() -> None:
    policy = ContextPolicy(budget=BUDGET)
    assert (policy.ceiling, policy.tail) == (5_000, 1_500)


async def test_it_archives_in_the_middle_of_a_turn() -> None:
    fake = four_steps()
    archive = MemoryArchive()
    subject = agent(fake, notes=FakeModelClient([reply(NOTES)]), archive=archive)

    events = await run(subject)

    archiving = [e for e in events if isinstance(e, ContextArchiving)]
    [archived] = [e for e in events if isinstance(e, ContextArchived)]
    assert len(archiving) == 1
    assert archived.before > 5_000
    assert archived.after < archived.before
    assert (archived.steps, archived.notes, archived.problem) == (3, True, None)
    # The fourth call starts with the index, and then the last step whole.
    fourth = fake.requests[3].messages
    assert is_index(fourth[0])
    assert "index one" in fourth[0].text
    assert '- "Hola"' in fourth[0].text
    assert fourth[1:] == list(subject.messages[5:7])
    # The conversation keeps everything; the window, the index and the rest.
    assert len(subject.messages) == 10
    assert subject.archived == 5
    assert subject.working[0] == fourth[0]
    assert list(subject.working[1:]) == list(subject.messages[5:])
    assert sorted(archive.items) == [
        "msg-1",
        "msg-2",
        "msg-3",
        "msg-4",
        "msg-5",
        "sum-5",
    ]
    assert events[-1] == TurnFinished(
        reason="end_turn",
        usage=Usage(),
        tool_calls=4,
        steps=5,
        cost=None,
    )


async def test_every_call_is_a_history_the_api_takes() -> None:
    fake = four_steps()
    subject = agent(fake)

    await run(subject)

    for request in fake.requests:
        check_history(request.messages)


async def test_without_an_archivist_the_code_writes_the_index_alone() -> None:
    fake = four_steps()
    subject = agent(fake)

    events = await run(subject)

    [archived] = [e for e in events if isinstance(e, ContextArchived)]
    assert archived.notes is False
    assert "Index: none was written" in fake.requests[3].messages[0].text


async def test_the_archivist_costs_in_the_turn_but_is_no_step() -> None:
    fake = four_steps()
    notes = FakeModelClient([reply(NOTES, usage=ARCHIVIST_USAGE)])
    subject = agent(fake, notes=notes)

    events = await run(subject)

    paid = [e for e in events if isinstance(e, ModelCallFinished) and e.archivist]
    assert [(e.model, e.usage) for e in paid] == [("small", ARCHIVIST_USAGE)]
    finished = events[-1]
    assert isinstance(finished, TurnFinished)
    assert (finished.usage, finished.steps) == (ARCHIVIST_USAGE, 5)
    [asked] = notes.requests
    assert asked.tools == []


async def test_the_next_archive_takes_the_index_before_it() -> None:
    fake = FakeModelClient(
        [tool_calls(big_call(f"c{n}")) for n in range(1, 7)] + [reply("Hecho.")]
    )
    second = json.dumps({"summary": "más", "index": "index two"})
    notes = FakeModelClient([reply(NOTES), reply(second)])
    subject = agent(fake, notes=notes)

    events = await run(subject)

    assert len([e for e in events if isinstance(e, ContextArchived)]) == 2
    assert "index one|" in notes.requests[1].messages[0].text
    assert "index two" in subject.working[0].text
    for request in fake.requests:
        check_history(request.messages)


async def test_a_turn_that_fits_never_archives() -> None:
    fake = FakeModelClient([tool_calls(big_call("c1")), reply("Hecho.")])
    subject = agent(fake)

    events = await run(subject)

    assert not [e for e in events if isinstance(e, ContextArchiving)]
    assert subject.archived == 0
    assert list(subject.working) == list(subject.messages)


async def test_a_broken_archive_archives_anyway_and_says_so() -> None:
    fake = four_steps()
    subject = agent(fake, archive=MemoryArchive(broken=True))

    events = await run(subject)

    [archived] = [e for e in events if isinstance(e, ContextArchived)]
    assert archived.problem is not None
    assert archived.problem.startswith("archive: ")
    assert subject.archived == 5


async def test_ctrl_c_while_archiving_leaves_the_conversation_as_it_was() -> None:
    fake = four_steps()
    notes = FakeModelClient([[HANG]])
    subject = agent(fake, notes=notes)

    task = asyncio.ensure_future(run(subject))
    await until(lambda: bool(notes.requests))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert subject.archived == 0
    assert list(subject.working) == list(subject.messages)
    # The three steps that ran are kept, and the next turn goes on from them.
    assert len(subject.messages) == 7
    check_history(list(subject.messages))


# The provider says it does not fit (§1.10, test 10).


async def test_a_context_overflow_archives_and_calls_once_more() -> None:
    fake = FakeModelClient([ContextOverflowError("HTTP 400: too long"), reply("Ok.")])
    subject = agent(fake, history=HISTORY, budget=100_000)

    events = await run(subject)

    assert len(fake.requests) == 2
    retried = fake.requests[1].messages
    assert is_index(retried[0])
    assert retried[1:] == [user("Hola")]
    assert isinstance(events[-1], TurnFinished)
    assert (events[-1].reason, events[-1].steps) == ("end_turn", 1)


async def test_a_second_context_overflow_ends_the_turn() -> None:
    fake = FakeModelClient(
        [ContextOverflowError("HTTP 400"), ContextOverflowError("HTTP 400")]
    )
    subject = agent(fake, history=HISTORY, budget=100_000)

    events = await run(subject)

    assert len(fake.requests) == 2
    assert isinstance(events[-1], TurnFinished)
    assert events[-1].reason == "context_full"
    # Nothing ran: the turn is not kept, as after any failed call.
    assert list(subject.messages) == HISTORY


async def test_a_context_overflow_with_nothing_to_archive_ends_at_once() -> None:
    fake = FakeModelClient([ContextOverflowError("HTTP 400")])
    subject = agent(fake, budget=100_000)

    events = await run(subject)

    assert len(fake.requests) == 1
    assert isinstance(events[-1], TurnFinished)
    assert events[-1].reason == "context_full"


async def test_an_answer_stopped_by_the_window_is_dropped_and_asked_again() -> None:
    fake = FakeModelClient(
        [reply("Empiezo a", stop_reason="context_full"), reply("Hecho.")]
    )
    subject = agent(fake, history=HISTORY, budget=100_000)

    events = await run(subject)

    assert len(fake.requests) == 2
    assert subject.messages[-1].text == "Hecho."
    assert "Empiezo a" not in [m.text for m in subject.messages]
    assert isinstance(events[-1], TurnFinished)
    assert events[-1].reason == "end_turn"


async def test_a_prompt_cut_in_silence_is_archived_and_asked_again() -> None:
    # The first call is counted at 5,000; the second adds some 2,000 tokens
    # (a call and its result), and the provider still counts 5,000: it cut
    # the prompt (spec hito 11, decision 14).
    counted = Usage(input_tokens=5_000, output_tokens=10)
    fake = FakeModelClient(
        [
            tool_calls(big_call("c1"), usage=counted),
            reply("Respuesta de un prompt cortado", usage=counted),
            reply("Hecho.", usage=Usage(input_tokens=3_000, output_tokens=5)),
        ]
    )
    subject = agent(fake, history=HISTORY, budget=100_000)

    events = await run(subject)

    assert len(fake.requests) == 3
    assert is_index(fake.requests[2].messages[0])
    assert subject.messages[-1].text == "Hecho."
    # The dropped answer was paid.
    paid = [e for e in events if isinstance(e, ModelCallFinished)]
    assert len(paid) == 3


async def test_a_count_that_grows_is_no_cut() -> None:
    fake = FakeModelClient(
        [
            tool_calls(big_call("c1"), usage=Usage(input_tokens=5_000)),
            reply("Hecho.", usage=Usage(input_tokens=7_100)),
        ]
    )
    subject = agent(fake, history=HISTORY, budget=100_000)

    await run(subject)

    assert len(fake.requests) == 2
    assert subject.archived == 0


async def test_a_count_by_another_model_is_no_cut() -> None:
    # Another model counts with its own tokenizer: after /model, its first
    # count is not compared with the last model's.
    counted = Usage(input_tokens=5_000)
    fake = FakeModelClient([reply("Uno.", usage=counted), reply("Dos.", usage=counted)])
    subject = agent(fake, history=HISTORY, budget=100_000)
    await run(subject)
    subject.model = "other"

    await run(subject, "otra vez " * 600)

    assert len(fake.requests) == 2
    assert subject.archived == 0


async def test_the_same_model_with_the_same_count_was_cut() -> None:
    counted = Usage(input_tokens=5_000)
    fake = FakeModelClient(
        [reply("Uno.", usage=counted), reply("Dos.", usage=counted), reply("Tres.")]
    )
    subject = agent(fake, history=HISTORY, budget=100_000)
    await run(subject)

    await run(subject, "otra vez " * 600)

    assert len(fake.requests) == 3
    assert subject.archived > 0


# /compact (§1.11).


async def test_compact_archives_all_but_the_tail_with_the_instructions() -> None:
    notes = FakeModelClient([reply(NOTES)])
    history = [*HISTORY, user("y ahora"), *old_step("h3")]
    subject = agent(FakeModelClient([]), notes=notes, history=history)

    events = [e async for e in subject.compact("céntrate en el IVA")]

    [archived] = [e for e in events if isinstance(e, ContextArchived)]
    assert archived.manual
    assert subject.archived == 6
    assert "céntrate en el IVA" in notes.requests[0].messages[0].text


async def test_compact_with_nothing_to_archive_does_nothing() -> None:
    subject = agent(FakeModelClient([]), history=[user("hola")])

    assert [e async for e in subject.compact()] == []
    assert subject.archived == 0


async def test_the_archivist_counts_in_the_limits_of_the_turn() -> None:
    fake = four_steps()
    notes = FakeModelClient([reply(NOTES, usage=Usage(input_tokens=50_000))])
    subject = agent(fake, notes=notes)
    subject.limits = TurnLimits(max_tokens=40_000)

    events = await run(subject)

    assert isinstance(events[-1], TurnFinished)
    assert (events[-1].reason, events[-1].steps) == ("max_tokens", 4)
