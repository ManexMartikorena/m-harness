"""The `maha` subcommands over sessions and traces (spec hito 8, §1.15)."""

import asyncio
import io
import json
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
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
from mharness.adapters.storage import JsonlSessionStore
from mharness.adapters.tracing import JsonlTraceSink
from mharness.application.agent import Agent
from mharness.application.sessions import Sessions
from mharness.domain.messages import (
    Message,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from mharness.domain.model import Usage
from mharness.domain.session import (
    MessageEntry,
    Session,
    SessionEntry,
    SessionHeader,
    UsageEntry,
)
from tests.adapters.test_print_mode import Terminal
from tests.fakes.model import FakeModelClient, reply
from tests.fakes.sessions import MemorySessionStore
from tests.unit.test_sessions import FIRST, NOW, World, exported, turn

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


@pytest.mark.parametrize("terminal", [True, False])
async def test_export_in_json_escapes_what_a_terminal_would_obey(
    terminal: bool,
) -> None:
    # Audit after hito 9, S5: JSON escapes only U+0000-001F; DEL, the C1
    # controls and the bidi ones went out raw. Escaped they are valid JSON
    # and come back the same, to a file too.
    world = await with_a_session("a\x7fb\x9b2Jc\u202ed\u2066e\x85f")
    out = Terminal() if terminal else io.StringIO()

    await export_session(
        world.sessions, FIRST, output_format="json", out=out, err=io.StringIO()
    )

    text = out.getvalue()
    for raw in ("\x7f", "\x9b", "\u202e", "\u2066", "\x85"):
        assert raw not in text
    assert "a\\u007fb\\u009b2Jc\\u202ed\\u2066e\\u0085f" in text
    exported = Session.model_validate_json(text)
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


@pytest.mark.parametrize("amount", ["1E+50", "1E-50"])
async def test_import_of_an_absurd_cost_fails(tmp_path: Path, amount: str) -> None:
    # Audit after hito 9, S4: never written out digit by digit.
    world = await with_a_session("Hola.")
    out = io.StringIO()
    await export_session(
        world.sessions, FIRST, output_format="json", out=out, err=io.StringIO()
    )
    data = json.loads(out.getvalue()) | {"cost": amount}
    file = tmp_path / "s.json"
    await asyncio.to_thread(file.write_text, json.dumps(data), "utf-8")
    err = io.StringIO()

    code = await import_session(world.sessions, file, out=io.StringIO(), err=err)

    assert code == 1
    assert "is not a session of maha export: cost: " in err.getvalue()
    assert [s.id for s in await world.sessions.summaries()] == [FIRST]


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


async def test_stats_with_more_days_than_the_calendar_has_is_every_day() -> None:
    # Audit of hito 8: --days 1000000 crashed with an OverflowError.
    world = await with_a_session("Hola.")
    out, err = io.StringIO(), io.StringIO()

    code = await show_stats(
        world.traces, days=10**9, today=NOW.astimezone().date(), out=out, err=err
    )

    assert (code, err.getvalue()) == (0, "")
    assert "fake-model" in out.getvalue()


async def test_trace_without_a_trace_names_no_file() -> None:
    # Audit of hito 8: an imported session has no trace.
    world = World(MemorySessionStore(), FakeModelClient([]), tokens=["9abc"])
    new = await world.sessions.import_session(await exported("Hola."))
    out, err = io.StringIO(), io.StringIO()

    assert await show_trace(world.sessions, new, out=out, err=err, home=HOME) == 0

    assert (out.getvalue(), err.getvalue()) == ("(no trace for this session)\n", "")


# Export and import over the real store (audit after hito 9, S8).


def no_agent(model: str, history: Sequence[Message]) -> Agent:
    raise AssertionError("export and import build no agent")


async def test_export_and_import_keep_every_field_over_the_real_store(
    tmp_path: Path,
) -> None:
    store = JsonlSessionStore(tmp_path / "sessions")
    sessions = Sessions(
        store,
        no_agent,
        cwd="/home/ana/web",
        provider="local",
        model="llama",
        version="0.9.0",
        traces=JsonlTraceSink(tmp_path / "traces"),
        now=lambda: NOW,
        token=iter(["b01c"]).__next__,
    )
    header = SessionHeader(
        id=FIRST,
        created_at=NOW - timedelta(days=1),
        cwd="/home/ana/proyecto",
        provider="anthropic",
        model="claude-x",
        maha="0.9.0",
    )
    thought = Message(
        role="assistant",
        blocks=[
            ReasoningBlock(text="Miro el fichero.", signature="c2lnbmF0dXJh"),
            ReasoningBlock(redacted="b3BhY28="),
            ToolCallBlock(id="toolu_1", name="read_file", arguments='{"path": "a"}'),
        ],
    )
    entries: list[SessionEntry] = [
        MessageEntry(message=Message(role="user", blocks=[TextBlock(text="Lee a")])),
        MessageEntry(message=thought),
        MessageEntry(
            message=Message(
                role="tool",
                blocks=[ToolResultBlock(call_id="toolu_1", content="hola")],
            )
        ),
        MessageEntry(
            message=Message(
                role="assistant",
                blocks=[ReasoningBlock(signature="Zmlu"), TextBlock(text="Dice hola.")],
            )
        ),
        UsageEntry(
            usage=Usage(
                input_tokens=1200,
                output_tokens=80,
                cache_read_tokens=300,
                cache_write_tokens=500,
                cache_write_1h_tokens=200,
                reasoning_tokens=40,
            ),
            cost=Decimal("0.000123456789"),
        ),
        UsageEntry(usage=Usage(input_tokens=10, output_tokens=2)),
        UsageEntry(usage=Usage(), turns=2),
    ]
    log = await store.create(header)
    await log.append(entries)
    await log.close()
    out = io.StringIO()
    assert (
        await export_session(
            sessions, FIRST, output_format="json", out=out, err=io.StringIO()
        )
        == 0
    )
    file = tmp_path / "s.json"
    await asyncio.to_thread(file.write_text, out.getvalue(), "utf-8")

    assert (
        await import_session(sessions, file, out=io.StringIO(), err=io.StringIO()) == 0
    )

    original = await store.read(FIRST)
    new = await store.read("20261026-091502-b01c")
    assert new.messages == original.messages
    assert new.messages[1].blocks[:2] == thought.blocks[:2]
    assert new.usage == original.usage
    assert new.usage.cache_write_1h_tokens == 200
    assert (new.cost, new.uncosted_turns) == (Decimal("0.000123456789"), 3)
    assert (new.cost, new.uncosted_turns) == (original.cost, original.uncosted_turns)
    assert (new.model, new.header.provider) == ("claude-x", "anthropic")
    # What is the new session's own: its id, when and where it was made.
    assert (new.header.cwd, new.header.created_at) == ("/home/ana/web", NOW)
