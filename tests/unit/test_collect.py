from collections.abc import AsyncIterator
from decimal import Decimal

import pytest

from mharness.domain.errors import ModelResponseError
from mharness.domain.events import MessageEnd, ModelEvent, TextDelta, ToolCallDelta
from mharness.domain.messages import Message, TextBlock, ToolCallBlock
from mharness.domain.model import ModelResponse, Usage
from tests.fakes.model import collect

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


async def test_takes_stop_reason_usage_model_and_cost_from_the_end() -> None:
    end = MessageEnd(
        stop_reason="max_tokens",
        usage=Usage(input_tokens=5, output_tokens=7),
        model="glm-5.3-flash-0401",
        cost=Decimal("0.00006225"),
    )

    response = await collect(events(TextDelta(text="Hola"), end))

    assert response == ModelResponse(
        message=Message(role="assistant", blocks=[TextBlock(text="Hola")]),
        stop_reason="max_tokens",
        usage=Usage(input_tokens=5, output_tokens=7),
        model="glm-5.3-flash-0401",
        cost=Decimal("0.00006225"),
    )


async def test_a_provider_that_says_no_cost_leaves_it_unknown() -> None:
    response = await collect(events(TextDelta(text="Hola"), END))

    assert response.cost is None


async def test_without_text_the_message_has_no_blocks() -> None:
    response = await collect(events(END))

    assert response.message == Message(role="assistant", blocks=[])


async def test_without_message_end_fails() -> None:
    with pytest.raises(ModelResponseError):
        await collect(events(TextDelta(text="Hola")))


# Tool calls (spec hito 4, §1.3).

TOOL_END = MessageEnd(stop_reason="tool_use", usage=Usage(), model=MODEL)


async def test_joins_split_arguments_of_the_same_call() -> None:
    response = await collect(
        events(
            ToolCallDelta(index=0, id="call_1", name="read_file", arguments='{"pa'),
            ToolCallDelta(index=0, arguments='th": "notas'),
            ToolCallDelta(index=0, arguments='.txt"}'),
            TOOL_END,
        )
    )

    assert response.message.blocks == [
        ToolCallBlock(id="call_1", name="read_file", arguments='{"path": "notas.txt"}')
    ]
    assert response.stop_reason == "tool_use"


async def test_two_indexes_give_two_calls_in_order() -> None:
    response = await collect(
        events(
            ToolCallDelta(index=1, id="call_b", name="read_file", arguments="{}"),
            ToolCallDelta(index=0, id="call_a", name="list_dir", arguments="{}"),
            TOOL_END,
        )
    )

    assert [block.type for block in response.message.blocks] == [
        "tool_call",
        "tool_call",
    ]
    assert [b.id for b in response.message.blocks if isinstance(b, ToolCallBlock)] == [
        "call_a",
        "call_b",
    ]


async def test_text_and_calls_in_the_same_message() -> None:
    call = ToolCallDelta(index=0, id="call_1", name="read_file", arguments="{}")

    response = await collect(events(TextDelta(text="Voy a leerlo."), call, TOOL_END))

    assert response.message.blocks == [
        TextBlock(text="Voy a leerlo."),
        ToolCallBlock(id="call_1", name="read_file", arguments="{}"),
    ]


@pytest.mark.parametrize(
    "delta",
    [
        ToolCallDelta(index=0, name="read_file", arguments="{}"),
        ToolCallDelta(index=0, id="call_1", arguments="{}"),
    ],
)
async def test_a_call_without_id_or_name_fails(delta: ToolCallDelta) -> None:
    with pytest.raises(ModelResponseError, match="without its id or name"):
        await collect(events(delta, TOOL_END))
