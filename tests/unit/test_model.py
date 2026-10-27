import pytest
from pydantic import ValidationError

from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest, ModelResponse, ToolSpec, Usage


def test_usage_defaults_to_zero() -> None:
    assert Usage() == Usage(
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
    )


def test_request_without_system_is_valid() -> None:
    request = ModelRequest(
        model="glm-5.3-flash",
        messages=[Message(role="user", blocks=[TextBlock(text="Hola")])],
    )

    assert request.system is None


def test_response_rejects_an_unknown_stop_reason() -> None:
    with pytest.raises(ValidationError):
        ModelResponse(
            message=Message(role="assistant", blocks=[]),
            stop_reason="tired",  # type: ignore[arg-type]
            usage=Usage(),
            model="glm-5.3-flash",
        )


def test_request_is_immutable() -> None:
    request = ModelRequest(model="glm-5.3-flash", messages=[])

    with pytest.raises(ValidationError):
        request.model = "kimi-k3"  # type: ignore[misc]


def test_request_has_no_tools_by_default() -> None:
    assert ModelRequest(model="glm-5.3-flash", messages=[]).tools == []


def test_request_carries_the_tool_specs() -> None:
    spec = ToolSpec(
        name="read_file",
        description="Read a text file.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
    )

    request = ModelRequest(model="glm-5.3-flash", messages=[], tools=[spec])

    assert request.tools == [spec]
    with pytest.raises(ValidationError):
        spec.name = "grep"  # type: ignore[misc]


def test_usage_adds_field_by_field() -> None:
    first = Usage(
        input_tokens=700, output_tokens=30, cache_read_tokens=1, reasoning_tokens=20
    )
    second = Usage(
        input_tokens=800, output_tokens=5, cache_write_tokens=2, reasoning_tokens=3
    )

    assert first + second == Usage(
        input_tokens=1500,
        output_tokens=35,
        cache_read_tokens=1,
        cache_write_tokens=2,
        reasoning_tokens=23,
    )
