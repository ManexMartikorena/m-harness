import pytest
from pydantic import ValidationError

from mharness.domain.messages import Message, TextBlock


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
