"""What a model sends while it answers, piece by piece (DESIGN §5).

Hito 3 adds `TextDelta` and `MessageEnd` (spec hito 3, §1.4); hito 4,
`ToolCallDelta` (spec hito 4, §1.3).
"""

from typing import Literal

from pydantic import BaseModel

from mharness.domain.model import StopReason, Usage


class TextDelta(BaseModel, frozen=True):
    """A piece of the answer's text, as it arrives."""

    # Names the event in traces (hito 7); nothing parses events from JSON yet.
    type: Literal["text_delta"] = "text_delta"
    text: str


class ToolCallDelta(BaseModel, frozen=True):
    """A piece of a tool call. The pieces of one call share its `index`.

    Some servers send a whole call at once; others split the arguments over
    many deltas. The accumulator joins them.
    """

    type: Literal["tool_call_delta"] = "tool_call_delta"
    index: int
    id: str | None = None
    name: str | None = None
    # A fragment of the JSON text, to append.
    arguments: str = ""


class MessageEnd(BaseModel, frozen=True):
    """The answer is complete. Sent once, after the last delta."""

    type: Literal["message_end"] = "message_end"
    stop_reason: StopReason
    usage: Usage
    # The model that answered, as the provider names it.
    model: str


type ModelEvent = TextDelta | ToolCallDelta | MessageEnd
