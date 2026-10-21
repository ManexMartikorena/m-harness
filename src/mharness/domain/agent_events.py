"""What the loop tells the terminal, and later the traces (DESIGN §5).

Hito 4 implements these; `TurnStarted`, `ApprovalRequested`, `AgentError` and
the cost arrive with their hitos (spec hito 4, §1.7).
"""

from typing import Literal

from pydantic import BaseModel

from mharness.domain.events import TextDelta
from mharness.domain.messages import ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage


class ToolCallProposed(BaseModel, frozen=True):
    """The model asked for a call; it has not run yet."""

    type: Literal["tool_call_proposed"] = "tool_call_proposed"
    call: ToolCallBlock


class ToolFinished(BaseModel, frozen=True):
    """A call ran, or failed; its result goes back to the model."""

    type: Literal["tool_finished"] = "tool_finished"
    call: ToolCallBlock
    result: ToolResultBlock
    # A few words for the terminal: the tool's summary, or the error.
    summary: str
    duration: float  # seconds
    # Set when the tool crashed (a bug of ours): type and message.
    internal_error: str | None = None


class ModelCallFinished(BaseModel, frozen=True):
    """One call to the model ended."""

    type: Literal["model_call_finished"] = "model_call_finished"
    usage: Usage
    model: str


class TurnFinished(BaseModel, frozen=True):
    """The turn ended and was kept in the history."""

    type: Literal["turn_finished"] = "turn_finished"
    # `end_turn`: the model answered without calls. `max_steps`: the limit.
    reason: Literal["end_turn", "max_steps"]
    # Summed over every call to the model in the turn.
    usage: Usage
    tool_calls: int
    # Calls to the model in the turn.
    steps: int


type AgentEvent = (
    TextDelta | ToolCallProposed | ToolFinished | ModelCallFinished | TurnFinished
)
