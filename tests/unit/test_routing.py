"""`ModelRouter`: each request to the client of its model's format (spec
hito 9, §1.2)."""

import pytest

from mharness.application.routing import ModelRouter
from mharness.domain.errors import ModelRequestError
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest
from tests.fakes.model import FakeModelClient, collect, reply

FORMATS = {"glm": "openai-chat", "claude": "anthropic", "gpt": "openai-responses"}


def request(model: str) -> ModelRequest:
    hola = Message(role="user", blocks=[TextBlock(text="Hola")])
    return ModelRequest(model=model, messages=[hola])


def router(**clients: FakeModelClient) -> ModelRouter:
    return ModelRouter(
        {api.replace("_", "-"): client for api, client in clients.items()},
        lambda model: FORMATS.get(model, "openai-chat"),
    )


async def test_each_request_goes_to_the_client_of_its_format() -> None:
    openai, anthropic = (
        FakeModelClient([reply("De GLM")]),
        FakeModelClient([reply("De Claude")]),
    )
    subject = router(openai_chat=openai, anthropic=anthropic)

    first = await collect(subject.stream(request("glm")))
    second = await subject.complete(request("claude"))

    assert (first.message.text, second.message.text) == ("De GLM", "De Claude")
    assert [r.model for r in openai.requests] == ["glm"]
    assert [r.model for r in anthropic.requests] == ["claude"]


async def test_a_format_maha_does_not_speak_calls_nobody() -> None:
    openai = FakeModelClient([])
    subject = router(openai_chat=openai)

    with pytest.raises(
        ModelRequestError,
        match="gpt uses the openai-responses API, which maha does not speak yet",
    ):
        await subject.complete(request("gpt"))
    with pytest.raises(ModelRequestError, match="does not speak yet"):
        await collect(subject.stream(request("gpt")))

    assert openai.requests == []


async def test_a_format_the_provider_does_not_serve_says_so() -> None:
    subject = router(openai_chat=FakeModelClient([]))

    with pytest.raises(
        ModelRequestError,
        match="claude uses the anthropic API, which this provider does not serve",
    ):
        await subject.complete(request("claude"))
