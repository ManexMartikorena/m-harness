from collections.abc import AsyncIterator

import pytest

from mharness.application.collect import collect
from mharness.domain.errors import ModelResponseError
from mharness.domain.events import MessageEnd, ModelEvent, TextDelta
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelResponse, Usage

MODEL = "glm-5.3-flash"
END = MessageEnd(
    stop_reason="end_turn",
    usage=Usage(input_tokens=18, output_tokens=31),
    model=MODEL,
)


async def events(*items: ModelEvent) -> AsyncIterator[ModelEvent]:
    for item in items:
        yield item


async def test_joins_the_deltas_in_one_block() -> None:
    response = await collect(
        events(TextDelta(text="Hola, "), TextDelta(text="Ane."), END)
    )

    assert response.message == Message(
        role="assistant", blocks=[TextBlock(text="Hola, Ane.")]
    )


async def test_takes_stop_reason_usage_and_model_from_the_end() -> None:
    end = MessageEnd(
        stop_reason="max_tokens",
        usage=Usage(input_tokens=5, output_tokens=7),
        model="glm-5.3-flash-0401",
    )

    response = await collect(events(TextDelta(text="Hola"), end))

    assert response == ModelResponse(
        message=Message(role="assistant", blocks=[TextBlock(text="Hola")]),
        stop_reason="max_tokens",
        usage=Usage(input_tokens=5, output_tokens=7),
        model="glm-5.3-flash-0401",
    )


async def test_without_text_the_message_has_no_blocks() -> None:
    response = await collect(events(END))

    assert response.message == Message(role="assistant", blocks=[])


async def test_without_message_end_fails() -> None:
    with pytest.raises(ModelResponseError):
        await collect(events(TextDelta(text="Hola")))
