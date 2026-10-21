"""What a model sends while it answers, piece by piece (DESIGN §5).

Hito 3 implements only `TextDelta` and `MessageEnd` (spec hito 3, §1.4).
"""

from typing import Literal

from pydantic import BaseModel

from mharness.domain.model import StopReason, Usage


class TextDelta(BaseModel, frozen=True):
    """A piece of the answer's text, as it arrives."""

    # Names the event in traces (hito 7); nothing parses events from JSON yet.
    type: Literal["text_delta"] = "text_delta"
    text: str


class MessageEnd(BaseModel, frozen=True):
    """The answer is complete. Sent once, after the last delta."""

    type: Literal["message_end"] = "message_end"
    stop_reason: StopReason
    usage: Usage
    # The model that answered, as the provider names it.
    model: str


type ModelEvent = TextDelta | MessageEnd
