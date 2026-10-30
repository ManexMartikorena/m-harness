"""The `maha` subcommands over sessions and traces (spec hito 8, §1.15)."""

import io
from datetime import timedelta
from pathlib import Path

from mharness.adapters.cli.subcommands import (
    delete_session,
    list_sessions,
    show_stats,
    show_trace,
)
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
