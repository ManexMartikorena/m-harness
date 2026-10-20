import pytest
from pydantic import ValidationError

from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelRequest, ModelResponse, Usage


def test_usage_defaults_to_zero() -> None:
    assert Usage() == Usage(
        input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0
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
