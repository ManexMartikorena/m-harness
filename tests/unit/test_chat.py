import pytest

from mharness.application.chat import Chat
from mharness.domain.errors import ModelUnavailableError
from mharness.domain.messages import Message, TextBlock
from tests.fakes.model import FakeModelClient, reply

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
