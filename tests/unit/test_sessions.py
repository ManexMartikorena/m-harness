"""`Sessions` and `Conversation`: each turn saved, sessions resumed (spec hito
6, §1.6, §1.8, §1.9 and §4.5), with `MemorySessionStore`."""

import asyncio
from collections.abc import Sequence
from contextlib import aclosing
from datetime import UTC, datetime

import pytest

from mharness.application.agent import Agent
from mharness.application.sessions import Conversation, Sessions
from mharness.application.tools import ToolRegistry
from mharness.domain.agent_events import AgentEvent
from mharness.domain.approval import ApprovalRequest
from mharness.domain.events import TextDelta
from mharness.domain.messages import Message, TextBlock, ToolCallBlock
from mharness.domain.model import Usage
from mharness.domain.session import (
    MessageEntry,
    ModelEntry,
    SessionEntry,
    SessionError,
    SessionHeader,
    SessionInUse,
    SessionNotFound,
    UsageEntry,
)
from tests.fakes.approval import FakeApproval
from tests.fakes.model import HANG, FakeModelClient, reply, tool_calls
from tests.fakes.sessions import MemoryLog, MemorySessionStore
from tests.fakes.tools import FakeTool
from tests.unit.test_agent import until

CWD = "/home/ana/proyecto"
NOW = datetime(2026, 10, 26, 9, 15, 2, tzinfo=UTC)
FIRST = "20261026-091502-3fa2"


def user(text: str) -> Message:
    return Message(role="user", blocks=[TextBlock(text=text)])


def said(text: str) -> Message:
    return Message(role="assistant", blocks=[TextBlock(text=text)])


class World:
    """One maha: a store shared with other maha, and how it builds agents."""

    def __init__(
        self,
        store: MemorySessionStore,
        fake: FakeModelClient,
        *,
        cwd: str = CWD,
        provider: str = "opencode-go",
        model: str = "glm-5.3-flash",
        tools: Sequence[FakeTool] = (),
        gate: FakeApproval | None = None,
        tokens: Sequence[str] = ("3fa2", "b01c", "c0de"),
    ) -> None:
        self.gate = gate or FakeApproval()
        self.built: list[tuple[str, tuple[Message, ...]]] = []
        registry = ToolRegistry(list(tools) or [FakeTool()])
        left = list(tokens)

        def new_agent(model: str, history: Sequence[Message]) -> Agent:
            self.built.append((model, tuple(history)))
            return Agent(fake, registry, gate=self.gate, model=model, history=history)

        self.sessions = Sessions(
            store,
            new_agent,
            cwd=cwd,
            provider=provider,
            model=model,
            version="0.6.0",
            now=lambda: NOW,
            token=lambda: left.pop(0),
        )


async def turn(conversation: Conversation, text: str) -> list[AgentEvent]:
    async with aclosing(conversation.run(text)) as events:
        return [event async for event in events]


def entries(store: MemorySessionStore, session_id: str = FIRST) -> list[SessionEntry]:
    return store.sessions[session_id].entries


# Each turn is saved (spec hito 6, §1.6).


async def test_without_turns_no_session_is_created() -> None:
    store = MemorySessionStore()
    conversation = await World(store, FakeModelClient([])).sessions.start()

    await conversation.close()

    assert conversation.id is None
    assert store.sessions == {}


async def test_the_first_turn_creates_the_session_with_its_header() -> None:
    store = MemorySessionStore()
    usage = Usage(input_tokens=742, output_tokens=31)
    conversation = await World(
        store, FakeModelClient([reply("Hola, Ana.", usage=usage)])
    ).sessions.start()

    await turn(conversation, "Hola, soy Ana")

    assert conversation.id == FIRST
    assert store.sessions[FIRST].header == SessionHeader(
        id=FIRST,
        created_at=NOW,
        cwd=CWD,
        provider="opencode-go",
        model="glm-5.3-flash",
        maha="0.6.0",
    )
    assert entries(store) == [
        MessageEntry(message=user("Hola, soy Ana")),
        MessageEntry(message=said("Hola, Ana.")),
        UsageEntry(usage=usage),
    ]
    # Locked while this maha has it.
    assert FIRST in store.locked
    await conversation.close()
    assert FIRST not in store.locked


async def test_each_turn_adds_its_messages_and_tokens() -> None:
    store = MemorySessionStore()
    fake = FakeModelClient([reply("Uno."), reply("Dos.")])
    conversation = await World(store, fake).sessions.start()

    await turn(conversation, "A")
    await turn(conversation, "B")

    assert [type(e).__name__ for e in entries(store)] == [
        *["MessageEntry"] * 2,
        "UsageEntry",
        *["MessageEntry"] * 2,
        "UsageEntry",
    ]


async def test_a_turn_cut_by_ctrl_c_is_saved_without_tokens() -> None:
    store = MemorySessionStore()
    fake = FakeModelClient([[TextDelta(text="Medio"), HANG]])
    conversation = await World(store, fake).sessions.start()
    seen: list[AgentEvent] = []

    async def consume() -> None:
        async for event in conversation.run("Cuéntame"):
            seen.append(event)

    task = asyncio.ensure_future(consume())
    await until(lambda: TextDelta(text="Medio") in seen)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    cut = Message(role="assistant", blocks=[TextBlock(text="Medio")], interrupted=True)
    assert entries(store) == [
        MessageEntry(message=user("Cuéntame")),
        MessageEntry(message=cut),
    ]


class BrokenLog(MemoryLog):
    """A disk that fails the first time it is written."""

    failures = 1

    async def append(self, entries: Sequence[SessionEntry]) -> None:
        if BrokenLog.failures:
            BrokenLog.failures -= 1
            raise SessionError("cannot save session: No space left on device")
        await super().append(entries)


async def test_a_failed_save_does_not_cut_the_turn_and_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tests.fakes.sessions.MemoryLog", BrokenLog)
    monkeypatch.setattr(BrokenLog, "failures", 1)
    store = MemorySessionStore()
    fake = FakeModelClient([reply("Uno."), reply("Dos.")])
    conversation = await World(store, fake).sessions.start()

    events = await turn(conversation, "A")

    assert type(events[-1]).__name__ == "TurnFinished"
    assert conversation.unsaved == "cannot save session: No space left on device"
    await turn(conversation, "B")
    assert conversation.unsaved is None
    # Nothing of the first turn is lost.
    assert [e.message.text for e in entries(store) if isinstance(e, MessageEntry)] == [
        "A",
        "Uno.",
        "B",
        "Dos.",
    ]


async def test_switching_the_model_is_saved() -> None:
    store = MemorySessionStore()
    fake = FakeModelClient([reply("Uno."), reply("Dos.")])
    conversation = await World(store, fake).sessions.start()
    await turn(conversation, "A")

    await conversation.switch_model("kimi-k3")
    await turn(conversation, "B")

    assert conversation.model == "kimi-k3"
    assert entries(store)[3] == ModelEntry(model="kimi-k3")
    assert fake.requests[1].model == "kimi-k3"


async def test_switching_the_model_before_any_turn_goes_in_the_header() -> None:
    store = MemorySessionStore()
    conversation = await World(store, FakeModelClient([reply("Uno.")])).sessions.start()

    await conversation.switch_model("kimi-k3")
    await turn(conversation, "A")

    assert store.sessions[FIRST].header.model == "kimi-k3"
    assert not any(isinstance(e, ModelEntry) for e in entries(store))


# Resuming (spec hito 6, §1.8 and §1.9).


async def saved(
    store: MemorySessionStore, *, cwd: str = CWD, text: str = "Hola"
) -> str:
    fake = FakeModelClient([reply("Hola, Ana.")])
    tokens = [f"{len(store.sessions):04x}"]
    conversation = await World(store, fake, cwd=cwd, tokens=tokens).sessions.start()
    await turn(conversation, text)
    await conversation.close()
    assert conversation.id is not None
    return conversation.id


async def test_resume_gives_the_history_and_the_model_of_the_session() -> None:
    store = MemorySessionStore()
    session_id = await saved(store)
    world = World(store, FakeModelClient([reply("Ana.")]), model="otro")
    current = await world.sessions.start()

    resumed = await world.sessions.resume(session_id, current=current)

    assert resumed.conversation.id == session_id
    assert resumed.conversation.model == "glm-5.3-flash"
    assert resumed.messages == 2
    assert (resumed.other_cwd, resumed.fallback_from, resumed.interrupted) == (
        None,
        None,
        False,
    )
    await turn(resumed.conversation, "¿Cómo me llamo?")
    assert world.built[-1] == ("glm-5.3-flash", (user("Hola"), said("Hola, Ana.")))
    # The new turn goes to the same file.
    assert (
        len([e for e in entries(store, session_id) if isinstance(e, MessageEntry)]) == 4
    )


async def test_resume_from_another_provider_uses_the_configured_model() -> None:
    store = MemorySessionStore()
    session_id = await saved(store)
    world = World(store, FakeModelClient([]), provider="local", model="llama")
    current = await world.sessions.start()

    resumed = await world.sessions.resume(session_id, current=current)

    assert resumed.conversation.model == "llama"
    assert resumed.fallback_from == "glm-5.3-flash"


async def test_resume_from_another_directory_says_where_it_was() -> None:
    store = MemorySessionStore()
    session_id = await saved(store, cwd="/home/ana/web")
    world = World(store, FakeModelClient([]))
    current = await world.sessions.start()

    resumed = await world.sessions.resume(session_id, current=current)

    assert resumed.other_cwd == "/home/ana/web"


async def test_resume_says_if_the_last_answer_was_cut() -> None:
    store = MemorySessionStore()
    cut = Message(role="assistant", blocks=[TextBlock(text="Me")], interrupted=True)
    log = await store.create(
        SessionHeader(
            id=FIRST,
            created_at=NOW,
            cwd=CWD,
            provider="opencode-go",
            model="m",
            maha="0.6.0",
        )
    )
    await log.append([MessageEntry(message=user("Hola")), MessageEntry(message=cut)])
    await log.close()
    world = World(store, FakeModelClient([]))

    resumed = await world.sessions.resume(FIRST, current=await world.sessions.start())

    assert resumed.interrupted is True


async def test_resume_without_an_id_takes_the_last_of_this_directory() -> None:
    store = MemorySessionStore()
    here = await saved(store, text="aquí")
    await saved(store, cwd="/home/ana/web", text="en web")
    world = World(store, FakeModelClient([]))

    resumed = await world.sessions.resume(None, current=await world.sessions.start())

    assert resumed.conversation.id == here


async def test_resume_without_an_id_and_nothing_here_is_not_found() -> None:
    store = MemorySessionStore()
    await saved(store, cwd="/home/ana/web")
    world = World(store, FakeModelClient([]))

    with pytest.raises(SessionNotFound, match=r"^no session in this directory$"):
        await world.sessions.resume(None, current=await world.sessions.start())


async def test_resuming_the_current_session_is_refused() -> None:
    store = MemorySessionStore()
    world = World(store, FakeModelClient([reply("Uno.")]))
    current = await world.sessions.start()
    await turn(current, "A")

    with pytest.raises(SessionError, match=r"^this is the current session$"):
        await world.sessions.resume(current.id, current=current)


async def test_a_session_open_in_another_maha_is_not_resumed() -> None:
    store = MemorySessionStore()
    other = await World(store, FakeModelClient([reply("Uno.")])).sessions.start()
    await turn(other, "A")
    world = World(store, FakeModelClient([]), tokens=["9999"])

    with pytest.raises(SessionInUse):
        await world.sessions.resume(FIRST, current=await world.sessions.start())


async def test_resuming_closes_the_conversation_it_leaves() -> None:
    store = MemorySessionStore()
    session_id = await saved(store)
    world = World(store, FakeModelClient([reply("Uno.")]), tokens=["7777"])
    current = await world.sessions.start()
    await turn(current, "A")

    await world.sessions.resume(session_id, current=current)

    assert "20261026-091502-7777" not in store.locked


async def test_approvals_do_not_come_back_with_the_session() -> None:
    # A "always this session" of yesterday is autonomy nobody gave today
    # (spec hito 6, §1.9).
    store = MemorySessionStore()
    request = ApprovalRequest(tool="echo", title="echo", detail="", scope="echo")
    calls = [
        ToolCallBlock(id=f"c{n}", name="echo", arguments='{"text": "x"}')
        for n in (1, 2)
    ]
    first = World(
        store,
        FakeModelClient([tool_calls(calls[0]), reply("Hecho.")]),
        tools=[FakeTool(permission="effect", requests=[request])],
        gate=FakeApproval(["session"]),
    )
    conversation = await first.sessions.start()
    await turn(conversation, "Uno")
    await conversation.close()

    gate = FakeApproval(["once"])
    second = World(
        store,
        FakeModelClient([tool_calls(calls[1]), reply("Hecho.")]),
        tools=[FakeTool(permission="effect", requests=[request])],
        gate=gate,
        tokens=["5555"],
    )
    resumed = await second.sessions.resume(FIRST, current=await second.sessions.start())
    await turn(resumed.conversation, "Otra vez")

    assert gate.requests == [request]


# The list and deleting (spec hito 6, §1.8).


async def test_summaries_are_all_newest_first_marking_this_directory() -> None:
    store = MemorySessionStore()
    older = await saved(store, cwd="/home/ana/web")
    newer = await saved(store)
    world = World(store, FakeModelClient([]))

    found = await world.sessions.summaries()

    assert [s.id for s in found] == [newer, older]
    assert [world.sessions.here(s) for s in found] == [True, False]


async def test_the_current_session_is_not_deleted() -> None:
    store = MemorySessionStore()
    world = World(store, FakeModelClient([reply("Uno.")]))
    current = await world.sessions.start()
    await turn(current, "A")
    assert current.id is not None

    with pytest.raises(SessionError, match=r"^this is the current session$"):
        await world.sessions.delete(current.id, current=current)


async def test_another_session_is_deleted() -> None:
    store = MemorySessionStore()
    session_id = await saved(store)
    world = World(store, FakeModelClient([]))

    await world.sessions.delete(session_id, current=await world.sessions.start())

    assert store.sessions == {}


async def test_closing_saves_what_is_pending_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tests.fakes.sessions.MemoryLog", BrokenLog)
    monkeypatch.setattr(BrokenLog, "failures", 1)
    store = MemorySessionStore()
    conversation = await World(store, FakeModelClient([reply("Uno.")])).sessions.start()
    await turn(conversation, "A")
    assert conversation.unsaved is not None

    await conversation.close()

    assert conversation.unsaved is None
    assert len(entries(store)) == 3


async def test_a_failure_after_opening_lets_the_session_go() -> None:
    store = MemorySessionStore()
    session_id = await saved(store)
    world = World(store, FakeModelClient([]))
    current = await world.sessions.start()

    def broken(model: str, history: Sequence[Message]) -> Agent:
        raise RuntimeError("no agent")

    sessions = Sessions(
        store, broken, cwd=CWD, provider="opencode-go", model="m", version="0.6.0"
    )
    with pytest.raises(RuntimeError):
        await sessions.resume(session_id, current=current)

    assert session_id not in store.locked
