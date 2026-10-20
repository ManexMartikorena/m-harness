"""What the core sends to a model and what it gets back (DESIGN §5)."""

from typing import Literal

from pydantic import BaseModel

from mharness.domain.messages import Message

# Why the model stopped. Each adapter maps its provider's reasons to these.
type StopReason = Literal[
    "end_turn", "max_tokens", "tool_use", "content_filter", "other"
]


class ModelRequest(BaseModel, frozen=True):
    """One call to the model: the whole conversation, every time."""

    model: str
    # Not a message: each adapter places it where its API expects it.
    system: str | None = None
    messages: list[Message]


class Usage(BaseModel, frozen=True):
    """Tokens used by one call, as the provider reports them."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class ModelResponse(BaseModel, frozen=True):
    """The model's answer to one request."""

    message: Message
    stop_reason: StopReason
    usage: Usage
    # The model that answered, as the provider names it.
    model: str
