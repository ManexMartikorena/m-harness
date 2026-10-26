import pytest
from pydantic import ValidationError

from mharness.domain.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock


def test_text_joins_the_blocks() -> None:
    message = Message(
        role="assistant",
        blocks=[TextBlock(text="Hola, Ane."), TextBlock(text="¿En qué te ayudo?")],
    )

    assert message.text == "Hola, Ane.\n¿En qué te ayudo?"


def test_text_of_a_message_without_blocks_is_empty() -> None:
    assert Message(role="assistant", blocks=[]).text == ""


def test_message_is_immutable() -> None:
    message = Message(role="user", blocks=[TextBlock(text="Hola")])

    with pytest.raises(ValidationError):
        message.role = "assistant"  # type: ignore[misc]


def test_text_block_is_immutable() -> None:
    block = TextBlock(text="Hola")

    with pytest.raises(ValidationError):
        block.text = "Adiós"  # type: ignore[misc]


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Message(role="system", blocks=[])  # type: ignore[arg-type]


def test_block_carries_its_type() -> None:
    assert TextBlock(text="Hola").model_dump() == {"type": "text", "text": "Hola"}


# Tool calls and results (spec hito 4, §1.2).

CALL = ToolCallBlock(id="call_1", name="read_file", arguments='{"path": "notas.txt"}')
RESULT = ToolResultBlock(call_id="call_1", content="     1\tComprar pan")


def test_tool_blocks_are_immutable() -> None:
    with pytest.raises(ValidationError):
        CALL.name = "grep"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        RESULT.is_error = True  # type: ignore[misc]


def test_tool_result_is_not_an_error_by_default() -> None:
    assert RESULT.is_error is False


def test_arguments_keep_invalid_json_as_written() -> None:
    # Fixes decision 1.2: the model's attempt stays in the history as is.
    call = ToolCallBlock(id="call_2", name="read_file", arguments='{"path": ')

    assert call.arguments == '{"path": '


def test_text_ignores_tool_blocks() -> None:
    message = Message(role="assistant", blocks=[TextBlock(text="Voy a leerlo."), CALL])

    assert message.text == "Voy a leerlo."


def test_message_validates_each_block_by_its_type() -> None:
    message = Message(role="assistant", blocks=[TextBlock(text="Mira:"), CALL])
    results = Message(role="tool", blocks=[RESULT])

    assert Message.model_validate_json(message.model_dump_json()) == message
    assert Message.model_validate_json(results.model_dump_json()) == results
    assert isinstance(
        Message.model_validate(
            {"role": "tool", "blocks": [RESULT.model_dump()]}
        ).blocks[0],
        ToolResultBlock,
    )


def test_unknown_block_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Message.model_validate(
            {"role": "user", "blocks": [{"type": "image", "data": "x"}]}
        )


def test_a_message_is_not_interrupted_unless_said() -> None:
    # A Ctrl+C in the middle marks it (spec hito 6, §1.7).
    whole = Message(role="assistant", blocks=[TextBlock(text="Hola.")])
    cut = Message(role="assistant", blocks=[TextBlock(text="Ho")], interrupted=True)

    assert whole.interrupted is False
    assert Message.model_validate_json(cut.model_dump_json()) == cut
    assert Message.model_validate_json(whole.model_dump_json()).interrupted is False
