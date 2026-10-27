"""Commands in the terminal: what is a command and what goes to the model
(spec hito 6, §1.8 and §4.7.1)."""

import asyncio
import io
import signal
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mharness.adapters.cli.commands import COMMANDS, Command, parse_command
from mharness.adapters.cli.conversation import converse
from mharness.application.agent import Agent
from mharness.application.sessions import Sessions
from mharness.application.tools import ToolRegistry
from mharness.domain.catalog import ModelInfo
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelResponse
from mharness.domain.session import (
    MessageEntry,
    SessionError,
    SessionHeader,
    SessionSummary,
)
from tests.fakes.approval import FakeApproval
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import FakeModelClient, reply
from tests.fakes.sessions import MemoryLog, MemorySessionStore
from tests.fakes.terminal import ScriptedInput
from tests.fakes.tracing import MemoryTraceSink


@pytest.mark.parametrize(
    ("line", "command"),
    [
        ("/sessions", Command("sessions", None)),
        ("/resume", Command("resume", None)),
        ("/resume 20261025-174233-b01c", Command("resume", "20261025-174233-b01c")),
        ("/delete   20261025-174233-b01c  ", Command("delete", "20261025-174233-b01c")),
        ("/model kimi-k3", Command("model", "kimi-k3")),
        ("/help", Command("help", None)),
        ("/exit", Command("exit", None)),
        # Unknown, but a command: it never goes to the model.
        ("/sesions", Command("sesions", None)),
        # "/" and lowercase letters alone is a command, also "/tmp".
        ("/tmp", Command("tmp", None)),
    ],
)
def test_commands(line: str, command: Command) -> None:
    assert parse_command(line) == command


@pytest.mark.parametrize(
    "line",
    [
        "Hola",
        "/etc/hosts no existe",
        " /help",
        "/Help",
        "/ ",
        "/resume2",
        "¿qué hace /help?",
    ],
)
def test_text_that_goes_to_the_model(line: str) -> None:
    # A path with more than one part, or anything else, is text.
    assert parse_command(line) is None


def test_the_known_commands() -> None:
    assert set(COMMANDS) == {"sessions", "resume", "delete", "model", "help", "exit"}


# The commands in the conversation (spec hito 6, §1.8 and §4.7.2-3), with
# sessions in memory.

HOME = Path("/home/ana")

# Every model these tests use, known without prices: no catalog notes and
# no "$" (spec hito 7, §1.10).
KNOWN = MemoryCatalog(
    [
        ModelInfo(provider=provider, model=model)
        for provider in ("opencode-go", "p")
        for model in ("glm-5.3-flash", "m", "kimi-k3")
    ]
)

CWD = "/home/ana/proyecto"
NOW = datetime(2026, 10, 26, 9, 15, 2, tzinfo=UTC)


class Maha:
    """One maha over a store that other maha share."""

    def __init__(
        self,
        store: MemorySessionStore,
        replies: list[ModelResponse],
        *,
        cwd: str = CWD,
        tokens: tuple[str, ...] = ("3fa2", "b01c", "c0de", "d00d"),
    ) -> None:
        self.fake = FakeModelClient(list(replies))
        self.traces = MemoryTraceSink()
        left = list(tokens)
        self.sessions = Sessions(
            store,
            lambda model, history: Agent(
                self.fake,
                ToolRegistry(),
                gate=FakeApproval(),
                model=model,
                catalog=MemoryCatalog(),
                provider="opencode-go",
                history=history,
            ),
            cwd=cwd,
            provider="opencode-go",
            model="glm-5.3-flash",
            version="0.6.0",
            traces=self.traces,
            now=lambda: NOW,
            token=lambda: left.pop(0),
        )
        self.discarded = 0

    def discard(self) -> bool:
        self.discarded += 1
        return False

    async def run(self, *lines: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = await converse(
            self.sessions,
            provider="opencode-go",
            catalog=KNOWN,
            read_line=ScriptedInput(*lines),
            discard=self.discard,
            out=out,
            err=err,
            home=HOME,
        )
        return code, out.getvalue(), err.getvalue()


def local(moment: datetime) -> str:
    return f"{moment.astimezone():%Y-%m-%d %H:%M}"


async def test_help_lists_the_commands() -> None:
    _, out, _ = await Maha(MemorySessionStore(), []).run("/help", "/exit")

    for line in COMMANDS.values():
        assert f"  {line}\n" in out


async def test_an_unknown_command_does_not_go_to_the_model() -> None:
    maha = Maha(MemorySessionStore(), [])

    _, out, _ = await maha.run("/sesions", "/exit")

    assert "  unknown command: /sesions (see /help)\n" in out
    assert maha.fake.requests == []


async def test_sessions_without_any() -> None:
    _, out, _ = await Maha(MemorySessionStore(), []).run("/sessions", "/exit")

    assert "  (no sessions)\n" in out


async def test_sessions_lists_every_directory_marking_this_one() -> None:
    store = MemorySessionStore()
    await Maha(store, [reply("Hola.")], cwd="/home/ana/web").run(
        "explícame el router", "/exit"
    )
    await Maha(store, [reply("Vale.")], tokens=("b01c",)).run(
        "arregla el test\ny más", "/exit"
    )
    newer, older = await Maha(store, []).sessions.summaries()

    _, out, _ = await Maha(store, [], tokens=("9999",)).run("/sessions", "/exit")

    assert (
        f"  * 20261026-091502-b01c  {local(newer.updated_at)}  2 messages  "
        "~/proyecto  arregla el test\n"
    ) in out
    assert (
        f"    20261026-091502-3fa2  {local(older.updated_at)}  2 messages  "
        "~/web  explícame el router\n"
    ) in out
    assert out.index("b01c") < out.index("3fa2")


async def test_resume_continues_a_session_with_its_history() -> None:
    store = MemorySessionStore()
    await Maha(store, [reply("Hola, Ana.")]).run("Me llamo Ana", "/exit")
    maha = Maha(store, [reply("Ana.")], tokens=("9999",))

    _, out, _ = await maha.run("/resume", "¿Cómo me llamo?", "/exit")

    assert "  [resumed 20261026-091502-3fa2 · 2 messages · glm-5.3-flash]\n" in out
    assert [m.text for m in maha.fake.requests[0].messages] == [
        "Me llamo Ana",
        "Hola, Ana.",
        "¿Cómo me llamo?",
    ]


async def test_resume_from_another_directory_says_the_tools_stay_here() -> None:
    store = MemorySessionStore()
    await Maha(store, [reply("Hola.")], cwd="/home/ana/web").run("Hola", "/exit")

    _, out, _ = await Maha(store, [], tokens=("9999",)).run(
        "/resume 20261026-091502-3fa2", "/exit"
    )

    assert "  [this session was in ~/web; tools work in ~/proyecto]\n" in out


async def test_resume_says_if_the_last_answer_was_cut() -> None:
    store = MemorySessionStore()
    log = await store.create(
        SessionHeader(
            id="20261026-091502-3fa2",
            created_at=NOW,
            cwd=CWD,
            provider="opencode-go",
            model="glm-5.3-flash",
            maha="0.6.0",
        )
    )
    cut = Message(role="assistant", blocks=[TextBlock(text="Me")], interrupted=True)
    await log.append(
        [
            MessageEntry(message=Message(role="user", blocks=[TextBlock(text="Hola")])),
            MessageEntry(message=cut),
        ]
    )
    await log.close()

    _, out, _ = await Maha(store, []).run("/resume", "/exit")

    assert "  [the last answer was interrupted]\n" in out


async def test_resume_errors_are_shown_and_the_conversation_goes_on() -> None:
    store = MemorySessionStore()
    maha = Maha(store, [reply("Sigo.")])

    _, out, err = await maha.run(
        "/resume", "/resume 20261026-091502-0000", "Hola", "/exit"
    )

    assert err == (
        "error: no other session in this directory (see /sessions)\n"
        "error: no session 20261026-091502-0000\n"
    )
    assert "Sigo." in out


async def test_delete_asks_first_and_n_keeps_it() -> None:
    store = MemorySessionStore()
    await Maha(store, [reply("Hola.")]).run("Hola", "/exit")
    maha = Maha(store, [], tokens=("9999",))

    _, out, _ = await maha.run("/delete 20261026-091502-3fa2", "n", "/exit")

    assert "  Delete session 20261026-091502-3fa2? [y/N]: " in out
    assert "  [not deleted]\n" in out
    assert "20261026-091502-3fa2" in store.sessions
    # What was typed before the question does not answer it (A2).
    assert maha.discarded == 1


async def test_delete_with_y_deletes_it() -> None:
    store = MemorySessionStore()
    await Maha(store, [reply("Hola.")]).run("Hola", "/exit")

    _, out, _ = await Maha(store, [], tokens=("9999",)).run(
        "/delete 20261026-091502-3fa2", "y", "/exit"
    )

    assert "  [deleted 20261026-091502-3fa2]\n" in out
    assert store.sessions == {}


async def test_delete_needs_an_id_and_never_takes_the_current() -> None:
    store = MemorySessionStore()
    maha = Maha(store, [reply("Hola.")])

    _, out, err = await maha.run(
        "/delete", "Hola", "/delete 20261026-091502-3fa2", "/exit"
    )

    assert "  usage: /delete ID\n" in out
    assert err == "error: this is the current session\n"


async def test_model_shows_and_changes_the_model() -> None:
    store = MemorySessionStore()
    maha = Maha(store, [reply("Hola.")])

    _, out, _ = await maha.run("/model", "/model kimi-k3", "Hola", "/exit")

    assert out.count("  [model: glm-5.3-flash]\n") == 1
    assert out.count("  [model: kimi-k3]\n") == 1
    assert maha.fake.requests[0].model == "kimi-k3"


async def test_titles_from_the_disk_are_escaped() -> None:
    store = MemorySessionStore()
    await Maha(store, [reply("Hola.")]).run("borra\x1b[2J todo", "/exit")

    _, out, _ = await Maha(store, [], tokens=("9999",)).run("/sessions", "/exit")

    assert "\x1b" not in out
    assert "borra\\x1b[2J todo" in out


class BrokenStore(MemorySessionStore):
    async def create(self, header: SessionHeader) -> MemoryLog:
        raise SessionError("cannot save session: No space left on device")


async def test_a_session_not_saved_is_a_warning() -> None:
    maha = Maha(BrokenStore(), [reply("Hola.")])

    code, out, err = await maha.run("Hola", "/exit")

    assert code == 0
    assert "Hola." in out
    assert (
        "warning: session not saved: cannot save session: No space left on device\n"
        in err
    )


# From the final audit of hito 6.


class LosingStore(MemorySessionStore):
    """A store whose disk fills up after the session is created."""

    async def create(self, header: SessionHeader) -> MemoryLog:
        log = await super().create(header)

        async def full(entries: object) -> None:
            raise SessionError("cannot save session: No space left on device")

        log.append = full  # type: ignore[method-assign]
        return log


async def test_resume_warns_of_what_the_session_left_could_not_save() -> None:
    # A session to go to, saved while the disk still worked.
    good = MemorySessionStore()
    await Maha(good, [reply("Antes.")]).run("antes", "/exit")
    store = LosingStore()
    store.sessions.update(good.sessions)
    maha = Maha(store, [reply("Ahora.")], tokens=("7777",))

    _, _, err = await maha.run("ahora", "/resume 20261026-091502-3fa2", "/exit")

    assert (
        "warning: session 20261026-091502-7777 was not saved, its last turns are lost: "
        "cannot save session: No space left on device\n"
    ) in err


async def test_an_unexpected_error_in_a_command_is_shown_and_maha_goes_on() -> None:
    class Broken(MemorySessionStore):
        async def summaries(self) -> list[SessionSummary]:
            raise RecursionError("maximum recursion depth exceeded")

    maha = Maha(Broken(), [reply("Sigo.")])

    code, out, err = await maha.run("/sessions", "Hola", "/exit")

    assert code == 0
    assert "error: internal: RecursionError: maximum recursion depth exceeded\n" in err
    assert "Sigo." in out


async def test_end_of_input_at_the_delete_question_keeps_the_session() -> None:
    store = MemorySessionStore()
    await Maha(store, [reply("Hola.")]).run("Hola", "/exit")

    code, out, _ = await Maha(store, [], tokens=("9999",)).run(
        "/delete 20261026-091502-3fa2"
    )

    assert code == 0
    assert "  [not deleted]\n" in out
    assert "20261026-091502-3fa2" in store.sessions


async def test_ctrl_c_at_the_delete_question_ends_maha_and_keeps_the_session() -> None:
    store = MemorySessionStore()
    await Maha(store, [reply("Hola.")]).run("Hola", "/exit")
    maha = Maha(store, [], tokens=("9999",))
    lines = iter(["/delete 20261026-091502-3fa2"])

    async def read() -> str:
        line = next(lines, None)
        if line is not None:
            return line
        signal.raise_signal(signal.SIGINT)
        await asyncio.Event().wait()
        raise AssertionError("not cancelled")

    code = await converse(
        maha.sessions,
        provider="opencode-go",
        catalog=KNOWN,
        read_line=read,
        discard=maha.discard,
        out=io.StringIO(),
        err=io.StringIO(),
        home=HOME,
    )

    assert code == 130
    assert "20261026-091502-3fa2" in store.sessions


async def test_leaving_a_conversation_never_saved_says_so() -> None:
    good = MemorySessionStore()
    await Maha(good, [reply("Antes.")]).run("antes", "/exit")

    class Full(MemorySessionStore):
        async def create(self, header: SessionHeader) -> MemoryLog:
            raise SessionError("cannot save session: No space left on device")

    store = Full()
    store.sessions.update(good.sessions)

    # Another token, another id.
    _, _, err = await Maha(store, [reply("Ahora.")], tokens=("b01c",)).run(
        "ahora", "/resume 20261026-091502-3fa2", "/exit"
    )

    assert (
        "warning: the conversation was not saved, its last turns are lost: "
        "cannot save session: No space left on device\n"
    ) in err
