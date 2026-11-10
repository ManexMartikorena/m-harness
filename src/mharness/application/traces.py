"""The summary that /trace shows of a session's trace (spec hito 7, §1.9).

One row per turn: when it started, calls to the model, tools, tokens, cost,
how long it took and how it ended; and the total. For the detail, the file
itself (or Langfuse, hito 22).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from mharness.domain.agent_events import (
    ModelCallFinished,
    ToolFinished,
    TurnFinished,
    TurnStarted,
)
from mharness.domain.model import Usage
from mharness.domain.trace import (
    TitleWritten,
    TraceRecord,
    TurnFailed,
    TurnInterrupted,
)

# How a turn ended: as `TurnFinished` says, by an exception, or not at all
# (maha died, or the trace failed).
type Ending = Literal[
    "end_turn",
    "max_steps",
    "max_cost",
    "max_tokens",
    "timeout",
    "denied",
    "max_output",
    "refused",
    "context_full",
    "error",
    "interrupted",
    "unfinished",
]


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
    # Of its calls with a price; None if none had one.
    cost: Decimal | None
    # From its start to its last record.
    seconds: float
    ended: Ending
    # Its calls without a price: then `cost` is a lower bound (audit after
    # hito 10, S3).
    unpriced: int = 0


@dataclass(frozen=True)
class TraceSummary:
    session: str
    # The models that answered, in the order they first did.
    models: list[str]
    turns: list[TurnSummary] = field(default_factory=list)
    # The calls that wrote the session's title, outside the turns (spec
    # hito 10, §1.12).
    titles: list[TitleWritten] = field(default_factory=list)

    @property
    def usage(self) -> Usage:
        usages = [turn.usage for turn in self.turns]
        return sum([*usages, *(title.usage for title in self.titles)], Usage())

    @property
    def cost(self) -> Decimal:
        """The turns and titles with a cost; `uncosted_turns` says how many
        had none."""
        return sum((cost for cost in self._costs() if cost is not None), Decimal(0))

    @property
    def priced(self) -> bool:
        """Whether some call had a price."""
        return any(cost is not None for cost in self._costs())

    @property
    def uncosted_turns(self) -> int:
        return sum(1 for cost in self._costs() if cost is None)

    @property
    def model_calls(self) -> int:
        return sum(turn.model_calls for turn in self.turns) + len(self.titles)

    def _costs(self) -> list[Decimal | None]:
        """A cost per turn and title; None for each that had a call without
        a price, besides what it had with one (audit after hito 10, S3)."""
        costs: list[Decimal | None] = []
        for turn in self.turns:
            if turn.cost is not None:
                costs.append(turn.cost)
            if turn.unpriced:
                costs.append(None)
        return costs + [title.cost for title in self.titles]

    @property
    def tools(self) -> int:
        return sum(turn.tools for turn in self.turns)


def summarize(session: str, records: Sequence[TraceRecord]) -> TraceSummary:
    """The summary of `records`, in the order of the file. Records before
    the first `TurnStarted` belong to no turn and are left out."""
    models: list[str] = []
    turns: list[TurnSummary] = []
    titles: list[TitleWritten] = []
    current: _Turn | None = None
    for record in records:
        event = record.event
        if isinstance(event, TitleWritten):
            # Written while the next turn may already run: of no turn.
            titles.append(event)
            if event.model not in models:
                models.append(event.model)
            continue
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
                # By call, as maha stats: a call without a price does not
                # hide what the others cost (audit after hito 10, S3).
                if event.cost is None:
                    current.unpriced += 1
                else:
                    current.cost += event.cost
                if event.model not in models:
                    models.append(event.model)
            case ToolFinished():
                if event.skipped:
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
    return TraceSummary(session=session, models=models, turns=turns, titles=titles)


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
    # Of its calls with a price.
    cost: Decimal = field(default_factory=Decimal)
    unpriced: int = 0
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
            # Unknown only if every call it made had no price.
            cost=None
            if self.unpriced and self.unpriced == self.model_calls
            else self.cost,
            seconds=(last - self.started_at).total_seconds(),
            ended=self.ended,
            unpriced=self.unpriced,
        )
