"""What the core sends to a model and what it gets back (DESIGN §5)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from mharness.domain.messages import Message
from mharness.domain.money import Usd

# Why the model stopped. Each adapter maps its provider's reasons to these.
type StopReason = Literal[
    "end_turn", "max_tokens", "tool_use", "content_filter", "other"
]


class ToolSpec(BaseModel, frozen=True):
    """A tool as the model sees it (spec hito 4, §1.5)."""

    name: str
    description: str
    # JSON Schema of the parameters, generated from the tool's Pydantic model.
    input_schema: dict[str, Any]


class ModelRequest(BaseModel, frozen=True):
    """One call to the model: the whole conversation, every time."""

    model: str
    # Not a message: each adapter places it where its API expects it.
    system: str | None = None
    messages: list[Message]
    # The tools the model may ask to call; none means plain conversation.
    tools: list[ToolSpec] = []


class Usage(BaseModel, frozen=True):
    """Tokens used by one call, as the provider reports them."""

    # Every prompt token, the cached ones included (as OpenAI counts them).
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    # Already inside output_tokens: they are billed as output.
    reasoning_tokens: int = Field(default=0, ge=0)

    def __add__(self, more: Usage) -> Usage:
        """The tokens of both calls, field by field."""
        return Usage(
            input_tokens=self.input_tokens + more.input_tokens,
            output_tokens=self.output_tokens + more.output_tokens,
            cache_read_tokens=self.cache_read_tokens + more.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + more.cache_write_tokens,
            reasoning_tokens=self.reasoning_tokens + more.reasoning_tokens,
        )


class ModelResponse(BaseModel, frozen=True):
    """The model's answer to one request."""

    message: Message
    stop_reason: StopReason
    usage: Usage
    # The model that answered, as the provider names it.
    model: str
    # What the call cost, as the provider says; None if it does not say
    # (spec hito 7, §1.5).
    cost: Usd | None = None
