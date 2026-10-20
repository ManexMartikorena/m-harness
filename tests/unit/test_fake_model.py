import pytest

from mharness.domain.errors import ModelRateLimitError
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest
from mharness.ports.model import ModelClient
from tests.fakes.model import FakeModelClient, reply

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
