"""What the loop tells the terminal and the traces (DESIGN §5).

Hito 4 implements these, hito 5 adds `ApprovalRequested`, and hito 7
`TurnStarted` and the cost (spec hito 7, §1.6). There is no `AgentError`:
errors are exceptions, and the trace records them from outside the loop.
"""

from typing import Literal

from pydantic import BaseModel

from mharness.domain.approval import ApprovalRequest, Decision
from mharness.domain.catalog import Usd
from mharness.domain.events import TextDelta
from mharness.domain.messages import ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage


class TurnStarted(BaseModel, frozen=True):
    """The first event of every turn: what the user wrote."""

    type: Literal["turn_started"] = "turn_started"
    text: str


class ToolCallProposed(BaseModel, frozen=True):
    """The model asked for a call; it has not run yet."""

    type: Literal["tool_call_proposed"] = "tool_call_proposed"
    call: ToolCallBlock


class ApprovalRequested(BaseModel, frozen=True):
    """The loop asks the user before running a call; the answer comes from
    the `ApprovalGate`."""

    type: Literal["approval_requested"] = "approval_requested"
    call: ToolCallBlock
    request: ApprovalRequest


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
    # What the user answered; None if nobody was asked.
    decision: Decision | None = None
    # Not run, because a previous call of the step was denied.
    skipped: bool = False


class ModelCallFinished(BaseModel, frozen=True):
    """One call to the model ended."""

    type: Literal["model_call_finished"] = "model_call_finished"
    usage: Usage
    model: str
    # None if the catalog has no prices for the model. No default: a
    # forgotten cost must not pass for "no price".
    cost: Usd | None


class TurnFinished(BaseModel, frozen=True):
    """The turn ended and was kept in the history."""

    type: Literal["turn_finished"] = "turn_finished"
    # `end_turn`: the model answered without calls. `max_steps`: the limit.
    # `denied`: the user denied a call.
    reason: Literal["end_turn", "max_steps", "denied"]
    # Summed over every call to the model in the turn.
    usage: Usage
    # Calls handled by the loop; not those skipped after a denial.
    tool_calls: int
    # Calls to the model in the turn.
    steps: int
    # Summed over its calls; None if one of them has no price.
    cost: Usd | None


type AgentEvent = (
    TurnStarted
    | TextDelta
    | ToolCallProposed
    | ApprovalRequested
    | ToolFinished
    | ModelCallFinished
    | TurnFinished
)
