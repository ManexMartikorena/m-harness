"""`daily()`: cost and tokens by day and model, from the traces (spec hito 8,
§1.15)."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from mharness.application.stats import DayModel, daily
from mharness.domain.agent_events import ModelCallFinished, TurnStarted
from mharness.domain.model import Usage
from mharness.domain.trace import TraceRecord
from tests.fakes.tracing import MemoryTraceSink

A = "20261028-091502-3fa2"
B = "20261029-101500-b01c"


def call(
    at: datetime, model: str, tokens: int, cost: str | None, session: str = A
) -> TraceRecord:
    usage = Usage(input_tokens=tokens, output_tokens=tokens // 10)
    return TraceRecord(
        at=at,
        session=session,
        event=ModelCallFinished(
            usage=usage, model=model, cost=None if cost is None else Decimal(cost)
        ),
    )


async def sink(*records: TraceRecord) -> MemoryTraceSink:
    traces = MemoryTraceSink()
    for record in records:
        log = await traces.open(record.session)
        await log.write(record)
    return traces


def at(day: int, hour: int = 10) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=UTC)


async def test_calls_add_up_by_day_and_model_over_every_trace() -> None:
    traces = await sink(
        TraceRecord(at=at(28), session=A, event=TurnStarted(text="Hola")),
        call(at(28), "glm-5.3-flash", 1000, "0.001"),
        call(at(28), "glm-5.3-flash", 2000, "0.002"),
        call(at(28), "kimi-k2.7-code", 500, "0.010"),
        call(at(29), "glm-5.3-flash", 3000, "0.003", session=B),
    )

    rows = await daily(traces, tz=UTC)

    assert rows == [
        DayModel(
            day=date(2026, 10, 28),
            model="glm-5.3-flash",
            calls=2,
            usage=Usage(input_tokens=3000, output_tokens=300),
            cost=Decimal("0.003"),
            uncosted=0,
        ),
        DayModel(
            day=date(2026, 10, 28),
            model="kimi-k2.7-code",
            calls=1,
            usage=Usage(input_tokens=500, output_tokens=50),
            cost=Decimal("0.010"),
            uncosted=0,
        ),
        DayModel(
            day=date(2026, 10, 29),
            model="glm-5.3-flash",
            calls=1,
            usage=Usage(input_tokens=3000, output_tokens=300),
            cost=Decimal("0.003"),
            uncosted=0,
        ),
    ]


async def test_calls_without_a_price_are_counted_apart() -> None:
    traces = await sink(
        call(at(28), "local", 100, None), call(at(28), "local", 100, "0.5")
    )

    (row,) = await daily(traces, tz=UTC)

    assert (row.calls, row.cost, row.uncosted) == (2, Decimal("0.5"), 1)


async def test_since_leaves_out_the_days_before() -> None:
    traces = await sink(
        call(at(27), "glm-5.3-flash", 100, "0.1"),
        call(at(29), "glm-5.3-flash", 100, "0.1", session=B),
    )

    rows = await daily(traces, since=date(2026, 10, 28), tz=UTC)

    assert [row.day for row in rows] == [date(2026, 10, 29)]


async def test_the_day_is_that_of_the_person_clock() -> None:
    # 23:00 in UTC is already the next day two hours east.
    traces = await sink(call(at(28, 23), "glm-5.3-flash", 100, "0.1"))

    (row,) = await daily(traces, tz=timezone(timedelta(hours=2)))

    assert row.day == date(2026, 10, 29)


async def test_without_traces_there_is_nothing() -> None:
    assert await daily(MemoryTraceSink(), tz=UTC) == []
