"""Commands in the terminal: what is a command and what goes to the model
(spec hito 6, §1.8 and §4.7.1)."""

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mharness.adapters.cli.commands import COMMANDS, Command, parse_command
from mharness.adapters.cli.conversation import converse
from mharness.application.agent import Agent
from mharness.application.sessions import Sessions
from mharness.application.tools import ToolRegistry
from mharness.domain.messages import Message, TextBlock
from mharness.domain.model import ModelResponse
from mharness.domain.session import MessageEntry, SessionError, SessionHeader
from tests.fakes.approval import FakeApproval
from tests.fakes.model import FakeModelClient, reply
from tests.fakes.sessions import MemoryLog, MemorySessionStore
from tests.fakes.terminal import ScriptedInput


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
        left = list(tokens)
        self.sessions = Sessions(
            store,
            lambda model, history: Agent(
                self.fake,
                ToolRegistry(),
                gate=FakeApproval(),
                model=model,
                history=history,
            ),
            cwd=cwd,
            provider="opencode-go",
            model="glm-5.3-flash",
            version="0.6.0",
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
        "error: no session in this directory (see /sessions)\n"
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
