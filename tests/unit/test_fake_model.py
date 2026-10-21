import asyncio

import pytest

from mharness.domain.errors import ModelRateLimitError, ModelUnavailableError
from mharness.domain.events import MessageEnd, ModelEvent, TextDelta
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest, Usage
from mharness.ports.model import ModelClient
from tests.fakes.model import END, HANG, FakeModelClient, Gate, reply

REQUEST = ModelRequest(
    model="fake-model",
    messages=[Message(role="user", blocks=[TextBlock(text="Hola, soy Ane")])],
)


def test_fake_satisfies_the_port() -> None:
    # mypy checks this assignment against the Protocol.
    client: ModelClient = FakeModelClient([])

    assert client is not None


async def test_returns_the_script_in_order() -> None:
    fake = FakeModelClient([reply("Hola, Ane."), reply("Te llamas Ane.")])

    first = await fake.complete(REQUEST)
    second = await fake.complete(REQUEST)

    assert first.message.text == "Hola, Ane."
    assert second.message.text == "Te llamas Ane."


async def test_raises_the_scripted_error() -> None:
    fake = FakeModelClient([ModelRateLimitError("slow down")])

    with pytest.raises(ModelRateLimitError, match="slow down"):
        await fake.complete(REQUEST)


async def test_keeps_the_requests() -> None:
    fake = FakeModelClient([reply("Hola, Ane."), ModelRateLimitError("slow down")])

    await fake.complete(REQUEST)
    with pytest.raises(ModelRateLimitError):
        await fake.complete(REQUEST)

    assert fake.requests == [REQUEST, REQUEST]


async def test_fails_when_the_script_is_exhausted() -> None:
    fake = FakeModelClient([reply("Hola, Ane.")])
    await fake.complete(REQUEST)

    with pytest.raises(AssertionError, match="script exhausted at call 2"):
        await fake.complete(REQUEST)


# Streaming (spec hito 3, §3.2).


async def play(fake: FakeModelClient) -> list[ModelEvent]:
    return [event async for event in fake.stream(REQUEST)]


async def test_stream_emits_the_script_in_order() -> None:
    fake = FakeModelClient([[TextDelta(text="Uno"), TextDelta(text="Dos"), END]])

    assert await play(fake) == [TextDelta(text="Uno"), TextDelta(text="Dos"), END]


async def test_stream_raises_the_error_after_the_previous_events() -> None:
    fake = FakeModelClient([[TextDelta(text="Hol"), ModelUnavailableError("cut")]])
    stream = fake.stream(REQUEST)

    assert await anext(stream) == TextDelta(text="Hol")
    with pytest.raises(ModelUnavailableError, match="cut"):
        await anext(stream)


async def test_stream_raises_a_scripted_error_step() -> None:
    fake = FakeModelClient([ModelRateLimitError("slow down")])

    with pytest.raises(ModelRateLimitError):
        await play(fake)


async def test_gate_waits_until_released() -> None:
    gate = Gate()
    fake = FakeModelClient([[TextDelta(text="Uno"), gate, TextDelta(text="Dos"), END]])
    stream = fake.stream(REQUEST)

    assert await anext(stream) == TextDelta(text="Uno")
    second = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0)
    assert not second.done()

    gate.release()
    assert await second == TextDelta(text="Dos")
    await stream.aclose()


async def test_hang_waits_until_cancelled() -> None:
    fake = FakeModelClient([[TextDelta(text="Esperando"), HANG]])

    task = asyncio.ensure_future(play(fake))
    await asyncio.sleep(0.01)
    assert not task.done()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_stream_plays_a_whole_response_as_events() -> None:
    usage = Usage(input_tokens=3, output_tokens=4)
    fake = FakeModelClient([reply("Hola, Ane.", stop_reason="max_tokens", usage=usage)])

    assert await play(fake) == [
        TextDelta(text="Hola,"),
        TextDelta(text=" Ane."),
        MessageEnd(stop_reason="max_tokens", usage=usage, model="fake-model"),
    ]


async def test_complete_collects_a_scripted_stream() -> None:
    fake = FakeModelClient([[TextDelta(text="Hola, "), TextDelta(text="Ane."), END]])

    response = await fake.complete(REQUEST)

    assert response.message.text == "Hola, Ane."


async def test_stream_keeps_the_requests_and_fails_when_exhausted() -> None:
    fake = FakeModelClient([[END]])
    await play(fake)

    with pytest.raises(AssertionError, match="script exhausted at call 2"):
        await play(fake)
    assert fake.requests == [REQUEST, REQUEST]
