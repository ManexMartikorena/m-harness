"""The titles of the sessions in a conversation (spec hito 10, §1.12, and
§4, test 11), with sessions and traces in memory."""

import asyncio
from decimal import Decimal

import pytest

from mharness.application.sessions import Conversation
from mharness.application.titles import Titler
from mharness.domain.errors import ModelUnavailableError
from mharness.domain.model import ModelRequest, ModelResponse, Usage
from mharness.domain.session import MessageEntry, SessionError, TitleEntry, UsageEntry
from mharness.domain.trace import TitleWritten
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import FakeModelClient, reply
from tests.fakes.sessions import MemorySessionStore
from tests.unit.test_sessions import FIRST, World, entries, turn

TEMPLATE = "Title: {{message}}"
PAID = Usage(input_tokens=80, output_tokens=6)


def titled(text: str, cost: str | None = "0.0001") -> ModelResponse:
    response = reply(text, usage=PAID)
    return response.model_copy(update={"cost": None if cost is None else Decimal(cost)})


def titler(small: FakeModelClient, failures: list[str] | None = None) -> Titler:
    return Titler(
        small,
        model="glm-5.3-flash",
        template=TEMPLATE,
        catalog=MemoryCatalog(),
        provider="opencode-go",
        failed=(failures.append if failures is not None else lambda kind: None),
    )


async def conversation_with(
    store: MemorySessionStore, small: FakeModelClient, *answers: str
) -> Conversation:
    fake = FakeModelClient([reply(answer) for answer in answers])
    world = World(store, fake, titler=titler(small))
    return await world.sessions.start()


async def test_the_first_turn_names_the_session() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled('"Arreglar el IVA reducido."')])
    conversation = await conversation_with(store, small, "Hecho.")

    await turn(conversation, "Arregla el IVA reducido de la tienda, por favor")
    await conversation.titled()

    # The small model read the first message as data, in its template.
    [asked] = small.requests
    assert asked.model == "glm-5.3-flash"
    assert asked.messages[0].text == (
        "Title: Arregla el IVA reducido de la tienda, por favor"
    )
    assert entries(store)[-2:] == [
        TitleEntry(title="Arreglar el IVA reducido"),
        UsageEntry(usage=PAID, cost=Decimal("0.0001")),
    ]
    # Its cost is the session's.
    assert conversation.cost == Decimal("0.0001")
    [summary] = await store.summaries()
    assert summary.title == "Arreglar el IVA reducido"
    await conversation.close()


async def test_its_call_is_in_the_trace_outside_the_turns() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled("Mirar la tienda")])
    fake = FakeModelClient([reply("Hecho.")])
    world = World(store, fake, titler=titler(small))
    conversation = await world.sessions.start()

    await turn(conversation, "Mira la tienda")
    await conversation.titled()
    await conversation.close()

    records = await world.traces.read(FIRST)
    assert records[-1].event == TitleWritten(
        model="glm-5.3-flash", usage=PAID, cost=Decimal("0.0001")
    )
    report = await world.sessions.trace(FIRST, current=None)
    assert len(report.summary.turns) == 1
    assert report.summary.model_calls == 2
    assert report.summary.cost == Decimal("0.0001")


async def test_only_the_first_turn_names_it() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled("Uno")])
    conversation = await conversation_with(store, small, "A.", "B.")

    await turn(conversation, "uno")
    await conversation.titled()
    await turn(conversation, "dos")
    await conversation.titled()

    assert len(small.requests) == 1
    await conversation.close()


async def test_a_resumed_session_keeps_its_title_and_is_not_named_again() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled("Primera")])
    first = await conversation_with(store, small, "A.")
    await turn(first, "uno")
    await first.titled()
    await first.close()

    again = FakeModelClient([reply("B.")])
    world = World(store, again, titler=titler(small), tokens=("b01c",))
    resumed = await world.sessions.resume(FIRST, current=await world.sessions.start())
    await turn(resumed.conversation, "dos")
    await resumed.conversation.titled()

    assert resumed.conversation.title == TitleEntry(title="Primera")
    assert len(small.requests) == 1
    await resumed.conversation.close()


async def test_a_failed_title_keeps_the_first_line_and_is_only_logged() -> None:
    store = MemorySessionStore()
    failures: list[str] = []
    small = FakeModelClient([ModelUnavailableError("the provider is down")])
    fake = FakeModelClient([reply("Hecho.")])
    world = World(store, fake, titler=titler(small, failures))
    conversation = await world.sessions.start()

    await turn(conversation, "Arregla el IVA\ny más cosas")
    await conversation.titled()

    assert failures == ["ModelUnavailableError"]
    [summary] = await store.summaries()
    assert summary.title == "Arregla el IVA"
    assert not any(
        isinstance(e, TitleEntry | UsageEntry) and e == e
        for e in entries(store)
        if isinstance(e, TitleEntry)
    )
    await conversation.close()


async def test_nothing_usable_is_still_paid() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled('""\n  ** **  ')])
    conversation = await conversation_with(store, small, "Hecho.")

    await turn(conversation, "Hola")
    await conversation.titled()

    assert not any(isinstance(entry, TitleEntry) for entry in entries(store))
    assert entries(store)[-1] == UsageEntry(usage=PAID, cost=Decimal("0.0001"))
    await conversation.close()


class NeverAnswers(FakeModelClient):
    """A small model that never answers."""

    def __init__(self) -> None:
        super().__init__([])
        self.asked = asyncio.Event()

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.asked.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


async def test_leaving_never_waits_for_the_title() -> None:
    store = MemorySessionStore()
    small = NeverAnswers()
    conversation = await conversation_with(store, small, "Hecho.")
    await turn(conversation, "Hola")
    await small.asked.wait()

    # The title never comes: leaving drops it, at once.
    await asyncio.wait_for(conversation.close(), 1)

    assert not any(isinstance(entry, TitleEntry) for entry in entries(store))


async def test_a_title_by_hand_wins() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled("Del modelo")])
    conversation = await conversation_with(store, small, "Hecho.")

    # The escape goes: the text after it is plain text.
    assert await conversation.rename("  Mi tarea\x1b[2J  ") == "Mi tarea [2J"
    await turn(conversation, "Hola")
    await conversation.titled()

    # Named by hand before the first turn: the small model is not asked.
    assert small.requests == []
    [summary] = await store.summaries()
    assert summary.title == "Mi tarea [2J"
    await conversation.close()


async def test_a_title_by_hand_after_the_models_replaces_it() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled("Del modelo")])
    conversation = await conversation_with(store, small, "Hecho.")
    await turn(conversation, "Hola")
    await conversation.titled()

    await conversation.rename("Otra cosa")

    [summary] = await store.summaries()
    assert summary.title == "Otra cosa"
    await conversation.close()


async def test_an_empty_title_by_hand_is_an_error() -> None:
    conversation = await conversation_with(
        MemorySessionStore(), FakeModelClient([]), "Hecho."
    )

    with pytest.raises(SessionError, match="needs some text"):
        await conversation.rename("  \n ")
    await conversation.close()


async def test_without_a_titler_there_are_no_titles() -> None:
    # `-p` and the evals (spec hito 10, §1.12).
    store = MemorySessionStore()
    conversation = await World(
        store, FakeModelClient([reply("Hecho.")])
    ).sessions.start()

    await turn(conversation, "Hola")
    await conversation.titled()

    assert not any(isinstance(entry, TitleEntry) for entry in entries(store))
    await conversation.close()


class AnswersWhenAllowed(FakeModelClient):
    """A small model that answers once the test lets it."""

    def __init__(self, response: ModelResponse) -> None:
        super().__init__([])
        self.asked = asyncio.Event()
        self.allowed = asyncio.Event()
        self._response = response

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.asked.set()
        await self.allowed.wait()
        return self._response


async def test_a_title_that_comes_during_the_next_turn_loses_nothing() -> None:
    # One save at a time: the title's and the turn's never cross.
    store = MemorySessionStore()
    small = AnswersWhenAllowed(titled("Dos turnos"))
    conversation = await conversation_with(store, small, "A.", "B.")
    await turn(conversation, "uno")
    await small.asked.wait()

    async def second() -> None:
        await turn(conversation, "dos")

    running = asyncio.create_task(second())
    small.allowed.set()
    await running
    await conversation.titled()
    await conversation.close()

    saved = entries(store)
    assert TitleEntry(title="Dos turnos") in saved
    texts = [e.message.text for e in saved if isinstance(e, MessageEntry)]
    assert texts == ["uno", "A.", "dos", "B."]
    # The session reads back whole.
    session = await store.read(FIRST)
    assert session.title == TitleEntry(title="Dos turnos")
