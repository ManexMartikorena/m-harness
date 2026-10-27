"""`MemoryTraceSink` follows the port (spec hito 7, §1.7)."""

from datetime import UTC, datetime

import pytest

from mharness.domain.agent_events import TurnStarted
from mharness.domain.trace import TraceError, TraceExists, TraceRecord
from mharness.ports.tracing import TraceSink
from tests.fakes.tracing import MemoryTraceSink

SESSION = "20261027-091502-3fa2"
RECORD = TraceRecord(
    at=datetime(2026, 10, 27, tzinfo=UTC),
    session=SESSION,
    event=TurnStarted(text="Hola"),
)


async def test_gives_back_what_was_written() -> None:
    sink: TraceSink = MemoryTraceSink()
    log = await sink.open(SESSION)
    await log.write(RECORD)

    assert await sink.read(SESSION) == [RECORD]


async def test_writes_fail_when_asked() -> None:
    sink = MemoryTraceSink()
    sink.failures = 1
    log = await sink.open(SESSION)

    with pytest.raises(TraceError):
        await log.write(RECORD)
    await log.write(RECORD)

    assert sink.events(SESSION) == ["turn_started"]


async def test_checks_ids_and_closed_logs() -> None:
    sink = MemoryTraceSink()

    with pytest.raises(TraceError, match="no session"):
        await sink.open("../x")
    log = await sink.open(SESSION)
    await log.close()
    with pytest.raises(TraceError, match="closed"):
        await log.write(RECORD)


async def test_delete_forgets_the_trace() -> None:
    sink = MemoryTraceSink()
    log = await sink.open(SESSION)
    await log.write(RECORD)

    await sink.delete(SESSION)

    assert await sink.read(SESSION) == []


async def test_a_new_trace_needs_a_free_id() -> None:
    sink = MemoryTraceSink()
    await sink.open(SESSION, new=True)

    with pytest.raises(TraceExists):
        await sink.open(SESSION, new=True)


async def test_every_operation_can_fail() -> None:
    sink = MemoryTraceSink()
    sink.open_failures = sink.sync_failures = sink.read_failures = 1

    with pytest.raises(TraceError):
        await sink.open(SESSION)
    log = await sink.open(SESSION)
    with pytest.raises(TraceError):
        await log.sync()
    with pytest.raises(TraceError):
        await sink.read(SESSION)
    await log.sync()
    assert await sink.read(SESSION) == []


async def test_broken_lines_are_skipped_as_by_the_real_one() -> None:
    sink = MemoryTraceSink()
    log = await sink.open(SESSION)
    await log.write(RECORD)
    sink.traces[SESSION].append('{"no es": "un registro"}')

    assert await sink.read(SESSION) == [RECORD]


async def test_writing_after_a_delete_goes_nowhere() -> None:
    sink = MemoryTraceSink()
    log = await sink.open(SESSION)
    await sink.delete(SESSION)

    await log.write(RECORD)

    assert SESSION not in sink.traces
