"""The summary of /trace from the records (spec hito 7, §1.9 and §4.6.1)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from mharness.application.agent import NOT_RUN_DENIED
from mharness.application.traces import TraceSummary, TurnSummary, summarize
from mharness.domain.agent_events import (
    ModelCallFinished,
    ToolCallProposed,
    ToolFinished,
    TurnFinished,
    TurnStarted,
)
from mharness.domain.approval import Decision
from mharness.domain.messages import ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.trace import TraceEvent, TraceRecord, TurnFailed, TurnInterrupted

SESSION = "20261027-091502-3fa2"
START = datetime(2026, 10, 27, 9, 15, 4, tzinfo=UTC)
CALL = ToolCallBlock(id="c1", name="read_file", arguments="{}")


def at(seconds: float, event: TraceEvent) -> TraceRecord:
    return TraceRecord(
        at=START + timedelta(seconds=seconds), session=SESSION, event=event
    )


def model(
    input: int, output: int, cost: str | None, name: str = "glm"
) -> ModelCallFinished:
    return ModelCallFinished(
        usage=Usage(input_tokens=input, output_tokens=output),
        model=name,
        cost=None if cost is None else Decimal(cost),
    )


def tool(
    content: str = "ok", *, error: bool = False, decision: Decision | None = None
) -> ToolFinished:
    return ToolFinished(
        call=CALL,
        result=ToolResultBlock(call_id="c1", content=content, is_error=error),
        summary=content,
        duration=0.1,
        decision=decision,
    )


def finished(reason: str = "end_turn") -> TurnFinished:
    return TurnFinished(
        reason=reason,  # type: ignore[arg-type]
        usage=Usage(),
        tool_calls=0,
        steps=1,
        cost=None,
    )


def test_one_row_per_turn_and_the_total() -> None:
    records = [
        at(0, TurnStarted(text="Arregla el test")),
        at(2, model(2000, 100, "0.0004")),
        at(2, ToolCallProposed(call=CALL)),
        at(2.5, tool()),
        at(6.2, model(2111, 186, "0.0004")),
        at(6.2, finished()),
        at(96, TurnStarted(text="Gracias")),
        at(97.9, model(4398, 41, "0.0007", name="kimi-k3")),
        at(97.9, finished()),
    ]

    summary = summarize(SESSION, records)

    assert summary == TraceSummary(
        session=SESSION,
        models=["glm", "kimi-k3"],
        turns=[
            TurnSummary(
                number=1,
                started_at=START,
                model_calls=2,
                tools=1,
                failed_tools=0,
                denied_tools=0,
                usage=Usage(input_tokens=4111, output_tokens=286),
                cost=Decimal("0.0008"),
                seconds=6.2,
                ended="end_turn",
            ),
            TurnSummary(
                number=2,
                started_at=START + timedelta(seconds=96),
                model_calls=1,
                tools=0,
                failed_tools=0,
                denied_tools=0,
                usage=Usage(input_tokens=4398, output_tokens=41),
                cost=Decimal("0.0007"),
                seconds=1.9,
                ended="end_turn",
            ),
        ],
    )
    assert summary.usage == Usage(input_tokens=8509, output_tokens=327)
    assert summary.cost == Decimal("0.0015")
    assert summary.uncosted_turns == 0
    assert (summary.model_calls, summary.tools) == (3, 1)


def test_denied_failed_and_skipped_tools() -> None:
    records = [
        at(0, TurnStarted(text="Haz cosas")),
        at(1, model(10, 1, "0")),
        at(1, tool("error: no such file", error=True)),
        at(1, tool("error: the user denied this call", error=True, decision="deny")),
        # After a denial the rest do not run: not counted as tools.
        at(1, tool(f"error: {NOT_RUN_DENIED}", error=True)),
        at(1, finished("denied")),
    ]

    [turn] = summarize(SESSION, records).turns

    assert (turn.tools, turn.failed_tools, turn.denied_tools) == (2, 1, 1)
    assert turn.ended == "denied"


def test_a_turn_without_price_has_no_cost_and_is_counted() -> None:
    records = [
        at(0, TurnStarted(text="A")),
        at(1, model(10, 1, "0.0001")),
        at(2, model(10, 1, None)),
        at(2, finished()),
        at(3, TurnStarted(text="B")),
        at(4, model(10, 1, "0.0002")),
        at(4, finished()),
    ]

    summary = summarize(SESSION, records)

    assert [turn.cost for turn in summary.turns] == [None, Decimal("0.0002")]
    assert summary.cost == Decimal("0.0002")
    assert summary.uncosted_turns == 1


def test_how_a_turn_ended_badly() -> None:
    records = [
        at(0, TurnStarted(text="A")),
        at(1, TurnFailed(kind="ModelUnavailableError", message="503")),
        at(2, TurnStarted(text="B")),
        at(3, model(10, 1, "0.0001")),
        at(4, TurnInterrupted()),
        # The last one never finished: maha died.
        at(5, TurnStarted(text="C")),
        at(6, model(10, 1, "0.0001")),
    ]

    turns = summarize(SESSION, records).turns

    assert [turn.ended for turn in turns] == ["error", "interrupted", "unfinished"]
    # A turn with no call to the model costs nothing, and has its price.
    assert turns[0].cost == Decimal(0)
    assert turns[0].model_calls == 0


def test_records_before_the_first_turn_are_ignored() -> None:
    summary = summarize(SESSION, [at(0, model(10, 1, "0.1"))])

    assert summary.turns == []
    assert summary.cost == Decimal(0)


def test_without_records_there_are_no_turns() -> None:
    summary = summarize(SESSION, [])

    assert (summary.turns, summary.models, summary.usage) == ([], [], Usage())
