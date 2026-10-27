"""`Sessions` and `Conversation`: each turn saved, sessions resumed (spec hito
6, §1.6, §1.8, §1.9 and §4.5), with `MemorySessionStore`."""

import asyncio
from collections.abc import Sequence
from contextlib import aclosing
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from mharness.application.agent import Agent
from mharness.application.sessions import Conversation, Sessions
from mharness.application.tools import ToolRegistry
from mharness.domain.agent_events import AgentEvent, TurnFinished, TurnStarted
from mharness.domain.approval import ApprovalRequest
from mharness.domain.catalog import ModelInfo, Prices
from mharness.domain.errors import ModelUnavailableError
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
from mharness.domain.trace import TraceError, TraceRecord, TurnFailed
from tests.fakes.approval import FakeApproval
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import HANG, FakeModelClient, reply, tool_calls
from tests.fakes.sessions import MemoryLog, MemorySessionStore
from tests.fakes.tools import EchoParams, FakeTool
from tests.fakes.tracing import MemoryTraceSink
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
        catalog: MemoryCatalog | None = None,
        traces: MemoryTraceSink | None = None,
        secrets: Sequence[str] = (),
    ) -> None:
        self.gate = gate or FakeApproval()
        self.traces = traces or MemoryTraceSink()
        self.built: list[tuple[str, tuple[Message, ...]]] = []
        registry = ToolRegistry(list(tools) or [FakeTool()])
        left = list(tokens)

        def new_agent(model: str, history: Sequence[Message]) -> Agent:
            self.built.append((model, tuple(history)))
            return Agent(
                fake,
                registry,
                gate=self.gate,
                model=model,
                catalog=catalog or MemoryCatalog(),
                provider="opencode-go",
                history=history,
            )

        self.sessions = Sessions(
            store,
            new_agent,
            cwd=cwd,
            provider=provider,
            model=model,
            version="0.6.0",
            traces=self.traces,
            masked=secrets,
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

    # It has an id from the start (spec hito 7, §1.7), but nothing on disk.
    assert not conversation.exists
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


async def test_switching_the_model_before_any_turn_is_saved_in_order() -> None:
    # The header keeps the model the conversation started with; the change
    # goes before the first turn (final audit of hito 6, 4).
    store = MemorySessionStore()
    conversation = await World(store, FakeModelClient([reply("Uno.")])).sessions.start()

    await conversation.switch_model("kimi-k3")
    assert store.sessions == {}
    await turn(conversation, "A")

    assert store.sessions[FIRST].header.model == "glm-5.3-flash"
    assert entries(store)[0] == ModelEntry(model="kimi-k3")


def kinds(store: MemorySessionStore) -> list[str]:
    return [
        e.message.text if isinstance(e, MessageEntry) else type(e).__name__
        for e in entries(store)
    ]


async def test_a_model_change_that_fails_to_save_is_tried_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tests.fakes.sessions.MemoryLog", BrokenLog)
    store = MemorySessionStore()
    fake = FakeModelClient([reply("Uno."), reply("Dos.")])
    conversation = await World(store, fake).sessions.start()
    monkeypatch.setattr(BrokenLog, "failures", 0)
    await turn(conversation, "A")

    monkeypatch.setattr(BrokenLog, "failures", 1)
    await conversation.switch_model("kimi-k3")
    assert conversation.unsaved is not None
    await turn(conversation, "B")

    assert kinds(store) == [
        "A",
        "Uno.",
        "UsageEntry",
        "ModelEntry",
        "B",
        "Dos.",
        "UsageEntry",
    ]


async def test_a_model_change_after_an_unsaved_turn_stays_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tests.fakes.sessions.MemoryLog", BrokenLog)
    store = MemorySessionStore()
    fake = FakeModelClient([reply("Uno."), reply("Dos."), reply("Tres.")])
    conversation = await World(store, fake).sessions.start()
    monkeypatch.setattr(BrokenLog, "failures", 0)
    await turn(conversation, "A")
    monkeypatch.setattr(BrokenLog, "failures", 1)
    await turn(conversation, "B")

    await conversation.switch_model("kimi-k3")
    await turn(conversation, "C")

    assert kinds(store) == [
        "A",
        "Uno.",
        "UsageEntry",
        "B",
        "Dos.",
        "UsageEntry",
        "ModelEntry",
        "C",
        "Tres.",
        "UsageEntry",
    ]


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

    with pytest.raises(SessionNotFound, match=r"^no other session in this directory$"):
        await world.sessions.resume(None, current=await world.sessions.start())


async def test_resume_without_an_id_skips_the_current_session() -> None:
    # After a turn, the current one is the newest here (final audit of
    # hito 6, 3).
    store = MemorySessionStore()
    before = await saved(store, text="antes")
    world = World(store, FakeModelClient([reply("Uno.")]), tokens=["7777"])
    current = await world.sessions.start()
    await turn(current, "ahora")

    resumed = await world.sessions.resume(None, current=current)

    assert resumed.conversation.id == before


async def test_resume_without_an_id_skips_a_session_open_elsewhere() -> None:
    store = MemorySessionStore()
    before = await saved(store, text="antes")
    other = await World(
        store, FakeModelClient([reply("Uno.")]), tokens=["8888"]
    ).sessions.start()
    await turn(other, "en otro maha")
    world = World(store, FakeModelClient([]), tokens=["9999"])

    resumed = await world.sessions.resume(None, current=await world.sessions.start())

    assert resumed.conversation.id == before


async def test_resume_without_an_id_and_only_the_current_is_not_found() -> None:
    store = MemorySessionStore()
    world = World(store, FakeModelClient([reply("Uno.")]))
    current = await world.sessions.start()
    await turn(current, "A")

    with pytest.raises(SessionNotFound, match=r"^no other session in this directory$"):
        await world.sessions.resume(None, current=current)


async def test_resume_tells_what_the_session_it_leaves_could_not_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Lost in silence otherwise (final audit of hito 6, 5).
    store = MemorySessionStore()
    target = await saved(store)
    monkeypatch.setattr("tests.fakes.sessions.MemoryLog", BrokenLog)
    monkeypatch.setattr(BrokenLog, "failures", 2)
    world = World(store, FakeModelClient([reply("Uno.")]), tokens=["7777"])
    current = await world.sessions.start()
    await turn(current, "A")

    resumed = await world.sessions.resume(target, current=current)

    assert resumed.left_unsaved == "cannot save session: No space left on device"


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
        store,
        broken,
        cwd=CWD,
        provider="opencode-go",
        model="m",
        version="0.6.0",
        traces=MemoryTraceSink(),
    )
    with pytest.raises(RuntimeError):
        await sessions.resume(session_id, current=current)

    assert session_id not in store.locked


# The cost of the session (spec hito 7, §1.5 and §4.5.6).

# Every answer of the fake comes from FAKE_MODEL: 1 USD per million tokens.
PRICED = MemoryCatalog(
    [
        ModelInfo(
            provider="opencode-go",
            model="fake-model",
            prices=Prices(
                input=Decimal(1), output=Decimal(1), checked=date(2026, 10, 27)
            ),
        )
    ]
)
MILLION = Usage(input_tokens=1_000_000)


async def test_each_turn_saves_its_cost() -> None:
    store = MemorySessionStore()
    fake = FakeModelClient([reply("Hola", usage=MILLION)])
    conversation = await World(store, fake, catalog=PRICED).sessions.start()

    await turn(conversation, "Hola")

    assert entries(store)[-1] == UsageEntry(usage=MILLION, cost=Decimal(1))


async def test_a_turn_without_price_saves_its_tokens_without_cost() -> None:
    store = MemorySessionStore()
    fake = FakeModelClient([reply("Hola", usage=MILLION)])
    conversation = await World(store, fake).sessions.start()

    await turn(conversation, "Hola")

    assert entries(store)[-1] == UsageEntry(usage=MILLION)
    assert conversation.uncosted_turns == 1


async def test_a_turn_that_fails_keeps_the_tokens_already_spent() -> None:
    # The first call was billed even if the second one fails (found
    # 2026-10-27: before, only a finished turn saved its tokens).
    store = MemorySessionStore()
    fake = FakeModelClient(
        [
            tool_calls(
                ToolCallBlock(id="c1", name="echo", arguments='{"text": "x"}'),
                usage=MILLION,
            ),
            ModelUnavailableError("down"),
        ]
    )
    conversation = await World(store, fake, catalog=PRICED).sessions.start()

    with pytest.raises(ModelUnavailableError):
        await turn(conversation, "Hola")

    assert entries(store)[-1] == UsageEntry(usage=MILLION, cost=Decimal(1))
    assert conversation.cost == Decimal(1)


async def test_the_conversation_adds_up_the_cost_of_its_turns() -> None:
    store = MemorySessionStore()
    fake = FakeModelClient([reply("Uno", usage=MILLION), reply("Dos", usage=MILLION)])
    conversation = await World(store, fake, catalog=PRICED).sessions.start()

    await turn(conversation, "A")
    await turn(conversation, "B")

    assert conversation.cost == Decimal(2)
    assert conversation.uncosted_turns == 0


async def test_a_resumed_session_goes_on_from_its_saved_cost() -> None:
    store = MemorySessionStore()
    fake = FakeModelClient([reply("Uno", usage=MILLION), reply("Dos", usage=MILLION)])
    world = World(store, fake, catalog=PRICED)
    first = await world.sessions.start()
    await turn(first, "A")
    await first.close()
    other = await world.sessions.start()

    resumed = await world.sessions.resume(FIRST, current=other)
    assert resumed.conversation.cost == Decimal(1)
    await turn(resumed.conversation, "B")

    assert resumed.conversation.cost == Decimal(2)


# Traces (spec hito 7, §1.7, §1.8 and §4.5).

SECRET = "sk-inventada-0000000000000000"


def echo_call(text: str = "x") -> ToolCallBlock:
    return ToolCallBlock(id="c1", name="echo", arguments=f'{{"text": "{text}"}}')


async def test_the_id_is_there_before_the_first_turn() -> None:
    conversation = await World(
        MemorySessionStore(), FakeModelClient([])
    ).sessions.start()

    assert conversation.id == FIRST


async def test_each_event_but_the_text_is_traced_with_its_session() -> None:
    world = World(
        MemorySessionStore(),
        FakeModelClient([tool_calls(echo_call()), reply("Hecho.")]),
    )
    conversation = await world.sessions.start()

    await turn(conversation, "Hola")

    assert world.traces.events(FIRST) == [
        "turn_started",
        "model_call_finished",
        "tool_call_proposed",
        "tool_finished",
        "model_call_finished",
        "turn_finished",
    ]
    records = await world.traces.read(FIRST)
    assert {(r.session, r.at) for r in records} == {(FIRST, NOW)}
    # Once per turn: what the next turn needs is on the disk.
    assert world.traces.synced == 1


async def test_the_session_and_its_trace_have_the_same_id() -> None:
    store = MemorySessionStore()
    world = World(store, FakeModelClient([reply("Hola")]))
    conversation = await world.sessions.start()

    await turn(conversation, "Hola")

    assert list(store.sessions) == list(world.traces.traces) == [FIRST]


async def test_a_failed_call_to_the_model_is_traced_as_an_error() -> None:
    world = World(MemorySessionStore(), FakeModelClient([ModelUnavailableError("503")]))
    conversation = await world.sessions.start()

    with pytest.raises(ModelUnavailableError):
        await turn(conversation, "Hola")

    records = await world.traces.read(FIRST)
    assert records[-1].event == TurnFailed(kind="ModelUnavailableError", message="503")


async def test_ctrl_c_is_traced_as_interrupted() -> None:
    world = World(MemorySessionStore(), FakeModelClient([[TextDelta(text="Me"), HANG]]))
    conversation = await world.sessions.start()
    seen: list[AgentEvent] = []

    async def consume() -> None:
        async for event in conversation.run("Cuéntame"):
            seen.append(event)

    task = asyncio.ensure_future(consume())
    await until(lambda: TextDelta(text="Me") in seen)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert world.traces.events(FIRST) == ["turn_started", "interrupted"]


async def test_secrets_are_masked_in_the_trace_but_not_in_the_session() -> None:
    store = MemorySessionStore()
    world = World(
        store,
        FakeModelClient([tool_calls(echo_call(SECRET)), reply("Hecho.")]),
        secrets=[SECRET],
    )
    conversation = await world.sessions.start()

    await turn(conversation, f"Usa {SECRET}")

    trace = "\n".join(world.traces.traces[FIRST])
    assert SECRET not in trace
    assert "[redacted]" in trace
    saved = "".join(entry.model_dump_json() for entry in entries(store))
    assert SECRET in saved


async def test_a_trace_that_fails_does_not_cut_the_turn_and_warns_once() -> None:
    store = MemorySessionStore()
    traces = MemoryTraceSink()
    traces.failures = 3
    world = World(store, FakeModelClient([reply("Uno"), reply("Dos")]), traces=traces)
    conversation = await world.sessions.start()

    await turn(conversation, "A")
    warning = conversation.trace_warning()
    await turn(conversation, "B")

    assert warning is not None
    assert "No space left on device" in warning
    assert conversation.trace_warning() is None
    # The session is saved whole.
    assert [type(e).__name__ for e in entries(store)].count("UsageEntry") == 2


async def test_a_resumed_session_goes_on_in_its_trace() -> None:
    store = MemorySessionStore()
    traces = MemoryTraceSink()
    fake = FakeModelClient([reply("Uno"), reply("Dos")])
    world = World(store, fake, traces=traces, tokens=["3fa2", "b01c", "c0de"])
    first = await world.sessions.start()
    await turn(first, "A")
    await first.close()
    other = await world.sessions.start()

    resumed = await world.sessions.resume(FIRST, current=other)
    await turn(resumed.conversation, "B")

    assert traces.events(FIRST).count("turn_started") == 2


async def test_delete_removes_the_session_and_its_trace() -> None:
    store = MemorySessionStore()
    traces = MemoryTraceSink()
    world = World(store, FakeModelClient([reply("Uno")]), traces=traces)
    first = await world.sessions.start()
    await turn(first, "A")
    await first.close()
    current = await world.sessions.start()

    await world.sessions.delete(FIRST, current=current)

    assert FIRST not in store.sessions
    assert FIRST not in traces.traces


class StuckTraces(MemoryTraceSink):
    async def delete(self, session: str) -> None:
        raise TraceError(f"cannot delete the trace of {session}: Permission denied")


async def test_a_trace_that_cannot_be_deleted_is_said() -> None:
    store = MemorySessionStore()
    world = World(store, FakeModelClient([reply("Uno")]), traces=StuckTraces())
    first = await world.sessions.start()
    await turn(first, "A")
    await first.close()
    current = await world.sessions.start()

    with pytest.raises(SessionError, match="deleted, but not its trace"):
        await world.sessions.delete(FIRST, current=current)
    assert FIRST not in store.sessions


async def test_an_id_whose_trace_exists_is_not_taken() -> None:
    # Another maha started in the same second with the same token.
    traces = MemoryTraceSink()
    await traces.open(FIRST, new=True)
    store = MemorySessionStore()
    world = World(store, FakeModelClient([reply("Uno")]), traces=traces)
    conversation = await world.sessions.start()

    await turn(conversation, "A")

    second = "20261026-091502-b01c"
    assert conversation.id == second
    assert list(store.sessions) == [second]
    assert traces.events(FIRST) == []
    assert traces.events(second)[0] == "turn_started"


async def test_an_id_whose_session_has_no_trace_is_not_taken() -> None:
    # A session without trace (of hito 6) already has the id: checked when
    # the id is reserved, before anything is written (audit of hito 7, 2).
    store = MemorySessionStore()
    old = World(store, FakeModelClient([reply("Viejo")]))
    first = await old.sessions.start()
    await turn(first, "A")
    await first.close()
    traces = MemoryTraceSink()
    world = World(store, FakeModelClient([reply("Nuevo")]), traces=traces)
    conversation = await world.sessions.start()

    await turn(conversation, "B")

    second = "20261026-091502-b01c"
    assert conversation.id == second
    assert entries(store, second)[0] == MessageEntry(message=user("B"))
    # Not created and moved later: never created.
    assert traces.created == [second]
    records = await traces.read(second)
    assert records[0].event.type == "turn_started"
    assert {r.session for r in records} == {second}


async def test_a_secret_that_breaks_a_record_does_not_cut_the_turn() -> None:
    # "tool_call" is also the `type` of a block: masked, the record is no
    # longer valid. The record is lost, never the turn.
    store = MemorySessionStore()
    world = World(
        store,
        FakeModelClient([tool_calls(echo_call()), reply("Hecho.")]),
        secrets=["tool_call"],
    )
    conversation = await world.sessions.start()

    await turn(conversation, "Hola")

    assert entries(store)[-1] == UsageEntry(usage=Usage())
    warning = conversation.trace_warning()
    assert warning is not None
    assert "cannot trace" in warning


# /trace (spec hito 7, §1.9 and §4.6.2).


async def test_trace_without_id_is_that_of_the_current_session() -> None:
    world = World(MemorySessionStore(), FakeModelClient([reply("Uno"), reply("Dos")]))
    conversation = await world.sessions.start()
    await turn(conversation, "A")
    await turn(conversation, "B")

    report = await world.sessions.trace(None, current=conversation)

    assert report.summary.session == FIRST
    assert len(report.summary.turns) == 2
    assert report.location == f"/traces/{FIRST}.jsonl"


async def test_trace_of_another_session_needs_no_lock() -> None:
    store = MemorySessionStore()
    traces = MemoryTraceSink()
    world = World(store, FakeModelClient([reply("Uno")]), traces=traces)
    first = await world.sessions.start()
    await turn(first, "A")
    # Still open in this maha: /trace only reads.
    other = World(store, FakeModelClient([]), traces=traces, tokens=["b01c"])
    current = await other.sessions.start()

    report = await other.sessions.trace(FIRST, current=current)

    assert len(report.summary.turns) == 1


async def test_trace_before_the_first_turn_has_no_turns() -> None:
    # Not even if another session has the id the new one will try first.
    traces = MemoryTraceSink()
    await traces.open(FIRST, new=True)
    traces.traces[FIRST].append(
        TraceRecord(
            at=NOW, session=FIRST, event=TurnStarted(text="Ajena")
        ).model_dump_json()
    )
    world = World(MemorySessionStore(), FakeModelClient([]), traces=traces)
    conversation = await world.sessions.start()

    report = await world.sessions.trace(None, current=conversation)

    assert report.summary.turns == []


async def test_trace_of_an_id_of_another_form_is_an_error() -> None:
    world = World(MemorySessionStore(), FakeModelClient([]))
    conversation = await world.sessions.start()

    with pytest.raises(TraceError, match="no session"):
        await world.sessions.trace("../../etc/passwd", current=conversation)


async def test_a_turn_closed_by_its_reader_is_traced_as_interrupted() -> None:
    # The terminal closes the turn (Ctrl+C while it was printing).
    world = World(MemorySessionStore(), FakeModelClient([reply("Hola, Ana")]))
    conversation = await world.sessions.start()

    async with aclosing(conversation.run("Hola")) as events:
        async for event in events:
            if isinstance(event, TextDelta):
                break

    assert world.traces.events(FIRST) == ["turn_started", "interrupted"]


async def test_nothing_is_traced_after_the_turn_finished() -> None:
    # The terminal failed printing the end of a turn that went well: the
    # trace keeps it as it ended (audit of hito 7, 3).
    world = World(MemorySessionStore(), FakeModelClient([reply("Hola")]))
    conversation = await world.sessions.start()

    async def print_turn() -> None:
        async with aclosing(conversation.run("Hola")) as events:
            async for event in events:
                if isinstance(event, TurnFinished):
                    raise RuntimeError("the terminal broke")

    with pytest.raises(RuntimeError, match="terminal"):
        await print_turn()

    assert world.traces.events(FIRST)[-1] == "turn_finished"


class CtrlC(FakeTool):
    async def run(self, params: EchoParams) -> str:
        raise KeyboardInterrupt


async def test_keyboard_interrupt_is_traced_as_interrupted() -> None:
    world = World(
        MemorySessionStore(),
        FakeModelClient([tool_calls(echo_call()), reply("No llega")]),
        tools=[CtrlC()],
    )
    conversation = await world.sessions.start()

    with pytest.raises(KeyboardInterrupt):
        await turn(conversation, "Hola")

    assert world.traces.events(FIRST)[-1] == "interrupted"


class Liar(MemorySessionStore):
    """Says no id is taken: the clash shows only when creating."""

    async def exists(self, session_id: str) -> bool:
        return False


async def test_a_failed_move_never_leaves_the_trace_under_another_id() -> None:
    store = Liar()
    old = World(store, FakeModelClient([reply("Viejo")]))
    first = await old.sessions.start()
    await turn(first, "A")
    await first.close()
    traces = MemoryTraceSink()
    world = World(store, FakeModelClient([reply("Nuevo")]), traces=traces)
    conversation = await world.sessions.start()
    traces.read_failures = 1

    await turn(conversation, "B")

    # The trace of FIRST is not left with this conversation's turn.
    assert FIRST not in traces.traces
    assert conversation.id == "20261026-091502-b01c"
    assert conversation.trace_warning() is not None


async def test_a_trace_that_opens_late_still_starts_with_its_turn() -> None:
    # It failed on TurnStarted and opened on the next event (audit of
    # hito 7, 11): /trace must not hide the turn.
    traces = MemoryTraceSink()
    traces.open_failures = 1
    world = World(MemorySessionStore(), FakeModelClient([reply("Hola")]), traces=traces)
    conversation = await world.sessions.start()

    await turn(conversation, "Hola")

    assert traces.events(FIRST) == [
        "turn_started",
        "model_call_finished",
        "turn_finished",
    ]
    records = await traces.read(FIRST)
    assert records[0].event == TurnStarted(text="Hola")
    assert conversation.trace_warning() is not None


async def test_a_failed_sync_is_told() -> None:
    traces = MemoryTraceSink()
    traces.sync_failures = 1
    world = World(MemorySessionStore(), FakeModelClient([reply("Hola")]), traces=traces)
    conversation = await world.sessions.start()

    await turn(conversation, "Hola")

    warning = conversation.trace_warning()
    assert warning is not None
    assert "Input/output error" in warning


async def test_without_a_free_id_for_the_trace_the_turn_goes_on() -> None:
    traces = MemoryTraceSink()
    tokens = ["3fa2", "b01c", "c0de", "d00d", "e1e1", "f0f0"]
    for token in tokens[:5]:
        await traces.open(f"20261026-091502-{token}", new=True)
    store = MemorySessionStore()
    world = World(store, FakeModelClient([reply("Hola")]), traces=traces, tokens=tokens)
    conversation = await world.sessions.start()

    await turn(conversation, "Hola")

    warning = conversation.trace_warning()
    assert warning is not None
    assert "no free id" in warning
    assert [type(e).__name__ for e in entries(store, conversation.id)][-1] == (
        "UsageEntry"
    )
