import pytest
from pydantic import ValidationError

from mharness.domain.events import MessageEnd, TextDelta, ToolCallDelta
from mharness.domain.model import Usage


def test_text_delta_is_immutable() -> None:
    delta = TextDelta(text="Ho")

    with pytest.raises(ValidationError):
        delta.text = "la"  # type: ignore[misc]


def test_message_end_is_immutable() -> None:
    end = MessageEnd(stop_reason="end_turn", usage=Usage(), model="glm-5.3-flash")

    with pytest.raises(ValidationError):
        end.model = "kimi-k3"  # type: ignore[misc]


def test_type_takes_its_default() -> None:
    end = MessageEnd(stop_reason="end_turn", usage=Usage(), model="glm-5.3-flash")

    assert TextDelta(text="Ho").type == "text_delta"
    assert end.type == "message_end"


def test_message_end_rejects_an_unknown_stop_reason() -> None:
    with pytest.raises(ValidationError):
        MessageEnd(
            stop_reason="tired",  # type: ignore[arg-type]
            usage=Usage(),
            model="glm-5.3-flash",
        )


def test_tool_call_delta_defaults_and_is_immutable() -> None:
    delta = ToolCallDelta(index=0)

    assert (delta.type, delta.id, delta.name, delta.arguments) == (
        "tool_call_delta",
        None,
        None,
        "",
    )
    with pytest.raises(ValidationError):
        delta.arguments = "{}"  # type: ignore[misc]
