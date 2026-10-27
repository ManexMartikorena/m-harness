"""`JsonlTraceSink` over `tmp_path` (spec hito 7, §1.7 and §4.5)."""

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mharness.adapters.tracing import JsonlTraceSink
from mharness.domain.agent_events import ToolFinished, TurnStarted
from mharness.domain.messages import ToolCallBlock, ToolResultBlock
from mharness.domain.trace import TraceError, TraceExists, TraceRecord, TurnFailed
from mharness.ports.tracing import TraceSink

SESSION = "20261027-091502-3fa2"
AT = datetime(2026, 10, 27, 9, 15, 4, tzinfo=UTC)


def record(text: str = "Hola", session: str = SESSION) -> TraceRecord:
    return TraceRecord(at=AT, session=session, event=TurnStarted(text=text))


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return tmp_path / "traces"


def file_of(folder: Path) -> Path:
    return folder / f"{SESSION}.jsonl"


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def exists(path: Path) -> bool:
    return path.exists()


def test_satisfies_the_port(folder: Path) -> None:
    # mypy checks this assignment against the Protocol.
    sink: TraceSink = JsonlTraceSink(folder)

    assert sink is not None


async def test_what_is_written_comes_back_in_order(folder: Path) -> None:
    sink = JsonlTraceSink(folder)
    log = await sink.open(SESSION)
    await log.write(record("Uno"))
    await log.write(record("Dos"))
    await log.sync()
    await log.close()

    assert await sink.read(SESSION) == [record("Uno"), record("Dos")]


async def test_one_line_per_record(folder: Path) -> None:
    sink = JsonlTraceSink(folder)
    log = await sink.open(SESSION)
    await log.write(record())
    await log.close()

    lines = file_of(folder).read_text(encoding="utf-8").splitlines()

    assert [json.loads(line) for line in lines] == [
        {
            "at": "2026-10-27T09:15:04Z",
            "session": SESSION,
            "event": {"type": "turn_started", "text": "Hola"},
        }
    ]


async def test_opening_again_appends(folder: Path) -> None:
    # A resumed session goes on in the same trace.
    sink = JsonlTraceSink(folder)
    for text in ("Uno", "Dos"):
        log = await sink.open(SESSION)
        await log.write(record(text))
        await log.close()

    assert await sink.read(SESSION) == [record("Uno"), record("Dos")]


async def test_only_the_user_can_read_them(folder: Path) -> None:
    previous = os.umask(0)
    try:
        log = await JsonlTraceSink(folder).open(SESSION)
        await log.close()
    finally:
        os.umask(previous)

    assert mode(folder) == 0o700
    assert mode(file_of(folder)) == 0o600


async def test_text_that_is_not_utf8_is_kept_escaped(folder: Path) -> None:
    # A file name with Latin-1 bytes reaches Python as surrogates.
    name = b"caf\xe9.txt".decode("utf-8", "surrogateescape")
    finished = ToolFinished(
        call=ToolCallBlock(id="c1", name="read_file", arguments="{}"),
        result=ToolResultBlock(call_id="c1", content=name),
        summary="1 line",
        duration=0.1,
    )
    sink = JsonlTraceSink(folder)
    log = await sink.open(SESSION)
    await log.write(TraceRecord(at=AT, session=SESSION, event=finished))
    await log.close()

    [back] = await sink.read(SESSION)

    assert isinstance(back.event, ToolFinished)
    assert back.event.result.content == name


async def test_broken_lines_are_skipped(folder: Path) -> None:
    sink = JsonlTraceSink(folder)
    log = await sink.open(SESSION)
    await log.write(record("Uno"))
    await log.close()
    with open(file_of(folder), "ab") as file:  # noqa: ASYNC230
        file.write(b"{no es json\n")
        file.write(b'{"at": "ayer", "session": "x", "event": {}}\n')
        file.write(b"\xff\xfe\n")
        file.write(record("Dos").model_dump_json().encode() + b"\n")
        # A last line cut by a crash.
        file.write(record("Tres").model_dump_json().encode()[:20])

    assert await sink.read(SESSION) == [record("Uno"), record("Dos")]


async def test_without_a_trace_there_are_no_records(folder: Path) -> None:
    assert await JsonlTraceSink(folder).read(SESSION) == []


async def test_an_unreadable_trace_is_an_error(folder: Path) -> None:
    file_of(folder).mkdir(parents=True)

    with pytest.raises(TraceError, match=f"cannot read the trace of {SESSION}"):
        await JsonlTraceSink(folder).read(SESSION)


@pytest.mark.parametrize("bad", ["../../etc/passwd", "", "20261027"])
async def test_an_id_of_another_form_never_reaches_the_disk(
    folder: Path, bad: str
) -> None:
    sink = JsonlTraceSink(folder)

    with pytest.raises(TraceError, match="no session"):
        await sink.open(bad)
    with pytest.raises(TraceError, match="no session"):
        await sink.read(bad)
    with pytest.raises(TraceError, match="no session"):
        await sink.delete(bad)
    assert not exists(folder)


async def test_a_folder_that_cannot_be_made_is_an_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")

    with pytest.raises(TraceError, match=f"cannot write the trace of {SESSION}"):
        await JsonlTraceSink(blocker / "traces").open(SESSION)


async def test_a_failed_write_leaves_no_half_line(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = JsonlTraceSink(folder)
    log = await sink.open(SESSION)
    await log.write(record("Uno"))
    real_write = os.write
    calls = 0

    def half_then_fail(fd: int, data: bytes | memoryview) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(fd, bytes(data)[:10])
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "write", half_then_fail)
    with pytest.raises(TraceError, match="No space left on device"):
        await log.write(record("Dos"))
    monkeypatch.undo()
    await log.write(record("Tres"))
    await log.close()

    assert await sink.read(SESSION) == [record("Uno"), record("Tres")]


async def test_a_failed_sync_is_an_error(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = await JsonlTraceSink(folder).open(SESSION)

    def fail(fd: int) -> None:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(TraceError, match="Input/output error"):
        await log.sync()
    monkeypatch.undo()
    await log.close()


async def test_a_closed_log_refuses_to_write(folder: Path) -> None:
    log = await JsonlTraceSink(folder).open(SESSION)
    await log.close()
    await log.close()

    with pytest.raises(TraceError, match="closed"):
        await log.write(record())


async def test_delete_removes_the_trace(folder: Path) -> None:
    sink = JsonlTraceSink(folder)
    log = await sink.open(SESSION)
    await log.write(record())
    await log.close()

    await sink.delete(SESSION)

    assert not exists(file_of(folder))


async def test_deleting_a_session_without_trace_is_fine(folder: Path) -> None:
    await JsonlTraceSink(folder).delete(SESSION)


async def test_a_trace_that_cannot_be_deleted_is_an_error(folder: Path) -> None:
    file_of(folder).mkdir(parents=True)

    with pytest.raises(TraceError, match=f"cannot delete the trace of {SESSION}"):
        await JsonlTraceSink(folder).delete(SESSION)


def test_location_names_the_file(folder: Path) -> None:
    assert JsonlTraceSink(folder).location(SESSION) == str(folder / f"{SESSION}.jsonl")


async def test_an_error_record_comes_back(folder: Path) -> None:
    failed = TraceRecord(
        at=AT, session=SESSION, event=TurnFailed(kind="ModelError", message="503")
    )
    sink = JsonlTraceSink(folder)
    log = await sink.open(SESSION)
    await log.write(failed)
    await log.close()

    assert await sink.read(SESSION) == [failed]


async def test_a_new_trace_is_created_only_if_free(folder: Path) -> None:
    # A new session reserves its id with its trace (spec hito 7, §12).
    sink = JsonlTraceSink(folder)
    log = await sink.open(SESSION, new=True)
    await log.write(record("Uno"))
    await log.close()

    with pytest.raises(TraceExists, match=f"trace of {SESSION} already exists"):
        await sink.open(SESSION, new=True)
    assert await sink.read(SESSION) == [record("Uno")]


async def test_reopening_after_a_cut_line_drops_it_first(folder: Path) -> None:
    # maha died half way through a line: the next record must not stick to
    # it, or both are lost and /trace merges two turns (audit of hito 7, 1).
    sink = JsonlTraceSink(folder)
    log = await sink.open(SESSION)
    await log.write(record("Uno"))
    await log.close()
    with open(file_of(folder), "ab") as file:  # noqa: ASYNC230
        file.write(record("Cortado").model_dump_json().encode()[:25])

    log = await sink.open(SESSION)
    await log.write(record("Dos"))
    await log.close()

    assert await sink.read(SESSION) == [record("Uno"), record("Dos")]


async def test_a_cut_line_left_by_a_failed_write_is_dropped_too(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The write failed half way and the file could not be cut back.
    sink = JsonlTraceSink(folder)
    log = await sink.open(SESSION)
    await log.write(record("Uno"))
    real_write = os.write

    def half_then_fail(fd: int, data: bytes | memoryview) -> int:
        real_write(fd, bytes(data)[:10])
        raise OSError(28, "No space left on device")

    def no_truncate(fd: int, size: int) -> None:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "write", half_then_fail)
    monkeypatch.setattr(os, "ftruncate", no_truncate)
    with pytest.raises(TraceError):
        await log.write(record("Perdido"))
    monkeypatch.undo()
    await log.write(record("Dos"))
    await log.close()

    assert await sink.read(SESSION) == [record("Uno"), record("Dos")]


async def test_closing_never_fails(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Everything was synced before: a failing close loses nothing, and must
    # not cut the turn that closes it (audit of hito 7).
    log = await JsonlTraceSink(folder).open(SESSION)
    real_close = os.close

    def failing(fd: int) -> None:
        real_close(fd)
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os, "close", failing)
    await log.close()
    monkeypatch.undo()

    with pytest.raises(TraceError, match="closed"):
        await log.write(record())
