import asyncio
from collections.abc import AsyncIterator
from contextlib import aclosing

import pytest

from mharness.application.chat import Chat
from mharness.domain.errors import ModelUnavailableError
from mharness.domain.events import MessageEnd, ModelEvent, TextDelta
from mharness.domain.messages import Message, TextBlock
from tests.fakes.model import END, HANG, FakeModelClient, Gate, reply

MODEL = "glm-5.3-flash"


def user(text: str) -> Message:
    return Message(role="user", blocks=[TextBlock(text=text)])


def assistant(text: str) -> Message:
    return Message(role="assistant", blocks=[TextBlock(text=text)])


async def test_second_call_resends_the_whole_history() -> None:
    # Fixes decision 1.4: the model remembers because the history travels.
    fake = FakeModelClient([reply("Hola, Ane."), reply("Te llamas Ane.")])
    chat = Chat(fake, model=MODEL)

    await chat.send("Hola, soy Ane")
    await chat.send("¿Cómo me llamo?")

    assert fake.requests[1].messages == [
        user("Hola, soy Ane"),
        assistant("Hola, Ane."),
        user("¿Cómo me llamo?"),
    ]


async def test_request_has_the_model_and_no_system() -> None:
    # Fixes decision 1.5: no system prompt in this hito.
    fake = FakeModelClient([reply("Hola, Ane.")])

    await Chat(fake, model=MODEL).send("Hola, soy Ane")

    assert fake.requests[0].model == MODEL
    assert fake.requests[0].system is None


async def test_send_returns_the_response_and_keeps_it() -> None:
    fake = FakeModelClient([reply("Hola, Ane.")])
    chat = Chat(fake, model=MODEL)

    response = await chat.send("Hola, soy Ane")

    assert response.message == assistant("Hola, Ane.")
    assert chat.messages == (user("Hola, soy Ane"), assistant("Hola, Ane."))


async def test_failed_call_leaves_the_conversation_as_it_was() -> None:
    fake = FakeModelClient(
        [reply("Hola, Ane."), ModelUnavailableError("down"), reply("Te llamas Ane.")]
    )
    chat = Chat(fake, model=MODEL)
    await chat.send("Hola, soy Ane")

    with pytest.raises(ModelUnavailableError):
        await chat.send("¿Cómo me llamo?")

    assert chat.messages == (user("Hola, soy Ane"), assistant("Hola, Ane."))

    # The retry does not carry the failed message twice.
    await chat.send("¿Cómo me llamo?")
    assert fake.requests[2].messages == [
        user("Hola, soy Ane"),
        assistant("Hola, Ane."),
        user("¿Cómo me llamo?"),
    ]


# Streaming (spec hito 3, §1.6).


async def test_stream_yields_the_events_as_they_arrive() -> None:
    gate = Gate()
    fake = FakeModelClient(
        [[TextDelta(text="Hola, "), gate, TextDelta(text="Ane."), END]]
    )
    stream = Chat(fake, model=MODEL).stream("Hola, soy Ane")

    assert await anext(stream) == TextDelta(text="Hola, ")
    gate.release()
    assert [event async for event in stream] == [TextDelta(text="Ane."), END]


async def test_stream_keeps_the_turn_and_resends_the_history() -> None:
    fake = FakeModelClient([reply("Hola, Ane."), reply("Te llamas Ane.")])
    chat = Chat(fake, model=MODEL)

    [_ async for _ in chat.stream("Hola, soy Ane")]
    [_ async for _ in chat.stream("¿Cómo me llamo?")]

    assert fake.requests[1].messages == [
        user("Hola, soy Ane"),
        assistant("Hola, Ane."),
        user("¿Cómo me llamo?"),
    ]
    assert fake.requests[1].model == MODEL


async def test_stream_error_leaves_the_conversation_as_it_was() -> None:
    fake = FakeModelClient([[TextDelta(text="Hol"), ModelUnavailableError("cut")]])
    chat = Chat(fake, model=MODEL)

    with pytest.raises(ModelUnavailableError):
        [_ async for _ in chat.stream("Hola, soy Ane")]

    assert chat.messages == ()


async def test_cancelled_stream_leaves_the_conversation_as_it_was() -> None:
    # Fixes decision 1.6.
    fake = FakeModelClient([[TextDelta(text="Esperando"), HANG]])
    chat = Chat(fake, model=MODEL)

    task = asyncio.ensure_future(_consume(chat.stream("Hola, soy Ane")))
    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert chat.messages == ()


async def test_turn_is_kept_when_the_caller_stops_at_the_end() -> None:
    # Fixes decision 1.6: kept before MessageEnd is handed over.
    fake = FakeModelClient([[TextDelta(text="Hola, Ane."), END]])
    chat = Chat(fake, model=MODEL)

    async with aclosing(chat.stream("Hola, soy Ane")) as stream:
        async for event in stream:
            if isinstance(event, MessageEnd):
                break

    assert chat.messages == (user("Hola, soy Ane"), assistant("Hola, Ane."))


async def _consume(stream: AsyncIterator[ModelEvent]) -> None:
    async for _ in stream:
        pass
