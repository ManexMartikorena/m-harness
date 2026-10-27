"""The summary that /trace shows of a session's trace (spec hito 7, §1.9).

One row per turn: when it started, calls to the model, tools, tokens, cost,
how long it took and how it ended; and the total. For the detail, the file
itself (or Langfuse, hito 20).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from mharness.application.agent import NOT_RUN_DENIED
from mharness.domain.agent_events import (
    ModelCallFinished,
    ToolFinished,
    TurnFinished,
    TurnStarted,
)
from mharness.domain.model import Usage
from mharness.domain.trace import TraceRecord, TurnFailed, TurnInterrupted

# How a turn ended: as `TurnFinished` says, by an exception, or not at all
# (maha died, or the trace failed).
type Ending = Literal[
    "end_turn", "max_steps", "denied", "error", "interrupted", "unfinished"
]

# The result of a call skipped after a denial: it never ran.
_SKIPPED = f"error: {NOT_RUN_DENIED}"


@dataclass(frozen=True)
class TurnSummary:
    number: int
    started_at: datetime
    model_calls: int
    # Calls handled: run, failed or denied; not those skipped after a denial.
    tools: int
    failed_tools: int
    denied_tools: int
    usage: Usage
    # None if a call had no price.
    cost: Decimal | None
    # From its start to its last record.
    seconds: float
    ended: Ending


@dataclass(frozen=True)
class TraceSummary:
    session: str
    # The models that answered, in the order they first did.
    models: list[str]
    turns: list[TurnSummary] = field(default_factory=list)

    @property
    def usage(self) -> Usage:
        return sum((turn.usage for turn in self.turns), Usage())

    @property
    def cost(self) -> Decimal:
        """The turns with a cost; `uncosted_turns` says how many had none."""
        return sum((t.cost for t in self.turns if t.cost is not None), Decimal(0))

    @property
    def uncosted_turns(self) -> int:
        return sum(1 for turn in self.turns if turn.cost is None)

    @property
    def model_calls(self) -> int:
        return sum(turn.model_calls for turn in self.turns)

    @property
    def tools(self) -> int:
        return sum(turn.tools for turn in self.turns)


def summarize(session: str, records: Sequence[TraceRecord]) -> TraceSummary:
    """The summary of `records`, in the order of the file. Records before
    the first `TurnStarted` belong to no turn and are left out."""
    models: list[str] = []
    turns: list[TurnSummary] = []
    current: _Turn | None = None
    for record in records:
        event = record.event
        if isinstance(event, TurnStarted):
            if current is not None:
                turns.append(current.summary())
            current = _Turn(len(turns) + 1, record.at)
            continue
        if current is None:
            continue
        current.last_at = record.at
        match event:
            case ModelCallFinished():
                current.model_calls += 1
                current.usage += event.usage
                if current.cost is not None:
                    current.cost = (
                        None if event.cost is None else current.cost + event.cost
                    )
                if event.model not in models:
                    models.append(event.model)
            case ToolFinished():
                if event.result.content == _SKIPPED:
                    continue
                current.tools += 1
                if event.decision == "deny":
                    current.denied_tools += 1
                elif event.result.is_error:
                    current.failed_tools += 1
            case TurnFinished():
                current.ended = event.reason
            case TurnFailed():
                current.ended = "error"
            case TurnInterrupted():
                current.ended = "interrupted"
            case _:
                pass
    if current is not None:
        turns.append(current.summary())
    return TraceSummary(session=session, models=models, turns=turns)


@dataclass
class _Turn:
    number: int
    started_at: datetime
    last_at: datetime | None = None
    model_calls: int = 0
    tools: int = 0
    failed_tools: int = 0
    denied_tools: int = 0
    usage: Usage = field(default_factory=Usage)
    cost: Decimal | None = field(default_factory=Decimal)
    ended: Ending = "unfinished"

    def summary(self) -> TurnSummary:
        last = self.last_at or self.started_at
        return TurnSummary(
            number=self.number,
            started_at=self.started_at,
            model_calls=self.model_calls,
            tools=self.tools,
            failed_tools=self.failed_tools,
            denied_tools=self.denied_tools,
            usage=self.usage,
            cost=self.cost,
            seconds=(last - self.started_at).total_seconds(),
            ended=self.ended,
        )
