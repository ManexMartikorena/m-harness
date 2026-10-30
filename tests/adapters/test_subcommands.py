"""The `maha` subcommands over sessions and traces (spec hito 8, §1.15)."""

import asyncio
import io
from datetime import timedelta
from pathlib import Path

import pytest

from mharness.adapters.cli.subcommands import (
    delete_session,
    export_session,
    import_session,
    list_sessions,
    show_stats,
    show_trace,
)
from mharness.domain.session import Session
from tests.adapters.test_print_mode import Terminal
from tests.fakes.model import FakeModelClient, reply
from tests.fakes.sessions import MemorySessionStore
from tests.unit.test_sessions import FIRST, NOW, World, turn

HOME = Path("/home/ana")


async def with_a_session(*answers: str) -> World:
    """A maha whose first session has one turn per answer."""
    world = World(MemorySessionStore(), FakeModelClient([reply(a) for a in answers]))
    conversation = await world.sessions.start()
    for answer in answers:
        await turn(conversation, f"Pregunta para {answer}")
    await conversation.close()
    return world


async def test_sessions_lists_them_without_indent() -> None:
    world = await with_a_session("Hola.")
    out = io.StringIO()

    assert await list_sessions(world.sessions, out=out, home=HOME) == 0

    # When it was saved, as the person's clock shows it, in the middle.
    line = out.getvalue()
    assert line.startswith(f"* {FIRST}  ")
    assert line.endswith("  2 messages  ~/proyecto  Pregunta para Hola.\n")


async def test_sessions_without_any_says_so() -> None:
    world = World(MemorySessionStore(), FakeModelClient([]))
    out = io.StringIO()

    assert await list_sessions(world.sessions, out=out, home=HOME) == 0

    assert out.getvalue() == "(no sessions)\n"


async def test_delete_removes_the_session_and_its_trace() -> None:
    world = await with_a_session("Hola.")
    out, err = io.StringIO(), io.StringIO()

    code = await delete_session(world.sessions, FIRST, out=out, err=err)

    assert (code, out.getvalue(), err.getvalue()) == (0, f"deleted {FIRST}\n", "")
    assert await world.sessions.summaries() == []
    assert await world.traces.read(FIRST) == []


async def test_delete_of_a_session_that_does_not_exist_fails() -> None:
    world = World(MemorySessionStore(), FakeModelClient([]))
    out, err = io.StringIO(), io.StringIO()

    code = await delete_session(
        world.sessions, "20261026-091502-ffff", out=out, err=err
    )

    assert (code, out.getvalue()) == (1, "")
    assert err.getvalue().startswith("error: ")


async def test_trace_without_id_is_the_last_session_here() -> None:
    world = await with_a_session("Hola.")
    out, err = io.StringIO(), io.StringIO()

    code = await show_trace(world.sessions, None, out=out, err=err, home=HOME)

    lines = out.getvalue().splitlines()
    assert (code, err.getvalue()) == (0, "")
    assert lines[0].startswith(f"{FIRST} · fake-model · 1 turn · 1 model call")
    assert lines[-1] == f"[trace: /traces/{FIRST}.jsonl]"


async def test_trace_of_a_session_by_id() -> None:
    world = await with_a_session("Hola.")
    out, err = io.StringIO(), io.StringIO()

    assert await show_trace(world.sessions, FIRST, out=out, err=err, home=HOME) == 0

    assert out.getvalue().startswith(f"{FIRST} · ")


async def test_trace_without_sessions_here_fails() -> None:
    world = World(MemorySessionStore(), FakeModelClient([]))
    out, err = io.StringIO(), io.StringIO()

    code = await show_trace(world.sessions, None, out=out, err=err, home=HOME)

    assert (code, out.getvalue()) == (1, "")
    assert err.getvalue() == "error: no session in this directory\n"


async def test_stats_counts_back_from_today() -> None:
    world = await with_a_session("Hola.")
    out, err = io.StringIO(), io.StringIO()
    day = NOW.astimezone().date()

    await show_stats(world.traces, days=1, today=day, out=out, err=err)
    assert out.getvalue().splitlines()[1].startswith(f"{day:%Y-%m-%d}  fake-model")

    out = io.StringIO()
    await show_stats(
        world.traces, days=1, today=day + timedelta(days=1), out=out, err=err
    )
    assert out.getvalue() == "(no calls to a model today)\n"


async def test_export_writes_the_markdown() -> None:
    world = await with_a_session("Hola.")
    out, err = io.StringIO(), io.StringIO()

    code = await export_session(
        world.sessions, FIRST, output_format="md", out=out, err=err
    )

    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue().startswith("# Pregunta para Hola.\n")
    assert out.getvalue().endswith("## maha\n\nHola.\n")


async def test_export_in_json_is_the_session() -> None:
    world = await with_a_session("Hola.")
    out, err = io.StringIO(), io.StringIO()

    await export_session(world.sessions, FIRST, output_format="json", out=out, err=err)

    exported = Session.model_validate_json(out.getvalue())
    assert exported == await world.sessions.read(FIRST)


async def test_export_of_a_session_open_in_another_maha() -> None:
    world = World(MemorySessionStore(), FakeModelClient([reply("Hola.")]))
    conversation = await world.sessions.start()
    await turn(conversation, "Hola")
    out, err = io.StringIO(), io.StringIO()

    code = await export_session(
        world.sessions, FIRST, output_format="md", out=out, err=err
    )

    assert code == 0
    await conversation.close()


async def test_export_to_a_terminal_is_clean() -> None:
    world = await with_a_session("\x1b[2JHola.")
    out = Terminal()

    await export_session(
        world.sessions, FIRST, output_format="md", out=out, err=io.StringIO()
    )

    assert "\x1b" not in out.getvalue()
    assert "\\x1b[2JHola." in out.getvalue()


async def test_export_of_a_session_that_does_not_exist() -> None:
    world = World(MemorySessionStore(), FakeModelClient([]))
    out, err = io.StringIO(), io.StringIO()

    code = await export_session(
        world.sessions, FIRST, output_format="md", out=out, err=err
    )

    assert (code, out.getvalue()) == (1, "")
    assert err.getvalue() == f"error: no session {FIRST}\n"


async def test_import_takes_back_an_export(tmp_path: Path) -> None:
    world = await with_a_session("Hola.")
    out = io.StringIO()
    await export_session(
        world.sessions, FIRST, output_format="json", out=out, err=io.StringIO()
    )
    file = tmp_path / "s.json"
    await asyncio.to_thread(file.write_text, out.getvalue(), "utf-8")
    out, err = io.StringIO(), io.StringIO()

    code = await import_session(world.sessions, file, out=out, err=err)

    new = "20261026-091502-b01c"
    assert (code, err.getvalue()) == (0, "")
    assert out.getvalue() == f"imported as {new} · maha -r {new} resumes it\n"
    original = await world.sessions.read(FIRST)
    assert (await world.sessions.read(new)).messages == original.messages


@pytest.mark.parametrize(
    ("content", "says"),
    [
        (b"no es json", "is not a session of maha export: Invalid JSON"),
        (b'{"header": {}}', "is not a session of maha export: header.id: Field"),
        (b"\xff\xfe", "is not a session of maha export: "),
    ],
)
async def test_import_of_what_is_not_a_session_fails(
    tmp_path: Path, content: bytes, says: str
) -> None:
    world = World(MemorySessionStore(), FakeModelClient([]))
    file = tmp_path / "s.json"
    await asyncio.to_thread(file.write_bytes, content)
    err = io.StringIO()

    code = await import_session(world.sessions, file, out=io.StringIO(), err=err)

    assert code == 1
    assert says in err.getvalue()
    assert await world.sessions.summaries() == []


async def test_import_of_a_file_that_does_not_exist(tmp_path: Path) -> None:
    world = World(MemorySessionStore(), FakeModelClient([]))
    err = io.StringIO()

    code = await import_session(
        world.sessions, tmp_path / "no.json", out=io.StringIO(), err=err
    )

    assert code == 1
    assert err.getvalue() == (
        f"error: cannot read {tmp_path / 'no.json'}: No such file or directory\n"
    )
