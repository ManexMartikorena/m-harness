"""The titles of the sessions in a conversation (spec hito 10, §1.12, and
§4, test 11), with sessions and traces in memory."""

import asyncio
import contextlib
import errno
import io
import signal
from collections.abc import Coroutine
from decimal import Decimal
from pathlib import Path

import pytest

from mharness.adapters.cli.commands import Commands, parse_command
from mharness.adapters.cli.conversation import converse
from mharness.application.sessions import Conversation
from mharness.application.titles import Title, Titler
from mharness.domain.errors import ModelUnavailableError
from mharness.domain.model import ModelRequest, ModelResponse, Usage
from mharness.domain.session import (
    MessageEntry,
    SessionError,
    SessionHeader,
    TitleEntry,
    UsageEntry,
)
from mharness.domain.trace import TitleWritten
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import HANG, FakeModelClient, reply
from tests.fakes.sessions import MemoryLog, MemorySessionStore
from tests.fakes.terminal import ScriptedInput
from tests.unit.test_sessions import FIRST, BrokenLog, World, entries, turn

TEMPLATE = "Title: {{message}}"
PAID = Usage(input_tokens=80, output_tokens=6)


def titled(text: str, cost: str | None = "0.0001") -> ModelResponse:
    response = reply(text, usage=PAID)
    return response.model_copy(update={"cost": None if cost is None else Decimal(cost)})


def titler(small: FakeModelClient, failures: list[str] | None = None) -> Titler:
    return Titler(
        small,
        model="glm-5.3-flash",
        template=TEMPLATE,
        catalog=MemoryCatalog(),
        provider="opencode-go",
        failed=(failures.append if failures is not None else lambda kind: None),
    )


async def conversation_with(
    store: MemorySessionStore, small: FakeModelClient, *answers: str
) -> Conversation:
    fake = FakeModelClient([reply(answer) for answer in answers])
    world = World(store, fake, titler=titler(small))
    return await world.sessions.start()


async def test_the_first_turn_names_the_session() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled('"Arreglar el IVA reducido."')])
    conversation = await conversation_with(store, small, "Hecho.")

    await turn(conversation, "Arregla el IVA reducido de la tienda, por favor")
    await conversation.titled()

    # The small model read the first message as data, in its template.
    [asked] = small.requests
    assert asked.model == "glm-5.3-flash"
    assert asked.messages[0].text == (
        "Title: Arregla el IVA reducido de la tienda, por favor"
    )
    assert entries(store)[-2:] == [
        TitleEntry(title="Arreglar el IVA reducido"),
        UsageEntry(usage=PAID, cost=Decimal("0.0001")),
    ]
    # Its cost is the session's.
    assert conversation.cost == Decimal("0.0001")
    [summary] = await store.summaries()
    assert summary.title == "Arreglar el IVA reducido"
    await conversation.close()


async def test_its_call_is_in_the_trace_outside_the_turns() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled("Mirar la tienda")])
    fake = FakeModelClient([reply("Hecho.")])
    world = World(store, fake, titler=titler(small))
    conversation = await world.sessions.start()

    await turn(conversation, "Mira la tienda")
    await conversation.titled()
    await conversation.close()

    records = await world.traces.read(FIRST)
    assert records[-1].event == TitleWritten(
        model="glm-5.3-flash", usage=PAID, cost=Decimal("0.0001")
    )
    report = await world.sessions.trace(FIRST, current=None)
    assert len(report.summary.turns) == 1
    assert report.summary.model_calls == 2
    assert report.summary.cost == Decimal("0.0001")


async def test_only_the_first_turn_names_it() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled("Uno")])
    conversation = await conversation_with(store, small, "A.", "B.")

    await turn(conversation, "uno")
    await conversation.titled()
    await turn(conversation, "dos")
    await conversation.titled()

    assert len(small.requests) == 1
    await conversation.close()


async def test_a_resumed_session_keeps_its_title_and_is_not_named_again() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled("Primera")])
    first = await conversation_with(store, small, "A.")
    await turn(first, "uno")
    await first.titled()
    await first.close()

    again = FakeModelClient([reply("B.")])
    world = World(store, again, titler=titler(small), tokens=("b01c",))
    resumed = await world.sessions.resume(FIRST, current=await world.sessions.start())
    await turn(resumed.conversation, "dos")
    await resumed.conversation.titled()

    assert resumed.conversation.title == TitleEntry(title="Primera")
    assert len(small.requests) == 1
    await resumed.conversation.close()


async def test_a_failed_title_keeps_the_first_line_and_is_only_logged() -> None:
    store = MemorySessionStore()
    failures: list[str] = []
    small = FakeModelClient([ModelUnavailableError("the provider is down")])
    fake = FakeModelClient([reply("Hecho.")])
    world = World(store, fake, titler=titler(small, failures))
    conversation = await world.sessions.start()

    await turn(conversation, "Arregla el IVA\ny más cosas")
    await conversation.titled()

    assert failures == ["ModelUnavailableError"]
    [summary] = await store.summaries()
    assert summary.title == "Arregla el IVA"
    assert not any(
        isinstance(e, TitleEntry | UsageEntry) and e == e
        for e in entries(store)
        if isinstance(e, TitleEntry)
    )
    await conversation.close()


async def test_nothing_usable_is_still_paid() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled('""\n  ** **  ')])
    conversation = await conversation_with(store, small, "Hecho.")

    await turn(conversation, "Hola")
    await conversation.titled()

    assert not any(isinstance(entry, TitleEntry) for entry in entries(store))
    assert entries(store)[-1] == UsageEntry(usage=PAID, cost=Decimal("0.0001"))
    await conversation.close()


class NeverAnswers(FakeModelClient):
    """A small model that never answers."""

    def __init__(self) -> None:
        super().__init__([])
        self.asked = asyncio.Event()

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.asked.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


async def test_leaving_waits_for_the_title() -> None:
    # Decision of the maintainer (2026-11-10): always wait for it; before,
    # leaving dropped a title already paid.
    store = MemorySessionStore()
    small = AnswersWhenAllowed(titled("Hola"))
    conversation = await conversation_with(store, small, "Hecho.")
    await turn(conversation, "Hola")
    await small.asked.wait()

    closing = asyncio.create_task(conversation.close())
    await asyncio.sleep(0.01)
    assert not closing.done()
    small.allowed.set()
    await closing

    assert TitleEntry(title="Hola") in entries(store)


async def test_ctrl_c_while_leaving_skips_the_title_and_saves_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The turn's save fails, so its messages are still pending when leaving:
    # they are saved after the cut (second review of the audit after hito
    # 10: nothing was pending, and the test said nothing of "the rest").
    monkeypatch.setattr("tests.fakes.sessions.MemoryLog", BrokenLog)
    monkeypatch.setattr(BrokenLog, "failures", 1)
    store = MemorySessionStore()
    small = NeverAnswers()
    conversation = await conversation_with(store, small, "Hecho.")
    await turn(conversation, "Hola")
    await small.asked.wait()
    assert conversation.naming
    assert conversation.unsaved is not None

    closing = asyncio.create_task(conversation.close())
    await asyncio.sleep(0.01)
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing

    assert not any(isinstance(entry, TitleEntry) for entry in entries(store))
    saved = [e.message.text for e in entries(store) if isinstance(e, MessageEntry)]
    assert saved == ["Hola", "Hecho."]
    assert conversation.unsaved is None
    # The session was let go: another maha may resume it.
    assert FIRST not in store.locked


async def test_a_resumed_session_without_a_title_gets_one() -> None:
    store = MemorySessionStore()
    first = await conversation_with(store, FakeModelClient([]), "A.")
    await turn(first, "Arregla el IVA")
    await first.close()

    small = FakeModelClient([titled("Arreglar el IVA")])
    world = World(store, FakeModelClient([]), titler=titler(small), tokens=("b01c",))
    resumed = await world.sessions.resume(FIRST, current=await world.sessions.start())
    await resumed.conversation.titled()
    await resumed.conversation.close()

    assert small.requests[0].messages[0].text == "Title: Arregla el IVA"
    assert TitleEntry(title="Arreglar el IVA") in entries(store)


async def test_a_session_whose_first_turn_was_not_saved_is_named_later() -> None:
    # Audit after hito 10 (S5): it was named only on the first turn.
    store = MemorySessionStore()
    small = FakeModelClient([titled("Uno")])
    fake = FakeModelClient([reply("A."), reply("B.")])
    world = World(store, fake, titler=titler(small))
    conversation = await world.sessions.start()
    real = store.create

    async def full(header: SessionHeader) -> MemoryLog:
        raise SessionError("cannot save session: No space left on device")

    store.create = full  # type: ignore[method-assign]
    await turn(conversation, "uno")
    assert small.requests == []
    store.create = real  # type: ignore[method-assign]
    await turn(conversation, "dos")
    await conversation.titled()
    await conversation.close()

    assert small.requests[0].messages[0].text == "Title: uno"


async def test_a_title_that_breaks_never_stops_leaving() -> None:
    # Audit after hito 10 (S4): close() ended there, unsaved, still locked.
    class Broken(Titler):
        async def title(self, first: str) -> Title | None:
            raise RuntimeError("a bug")

    store = MemorySessionStore()
    fake = FakeModelClient([reply("Hecho.")])
    world = World(
        store,
        fake,
        titler=Broken(
            FakeModelClient([]),
            model="m",
            template=TEMPLATE,
            catalog=MemoryCatalog(),
            provider="opencode-go",
        ),
    )
    conversation = await world.sessions.start()
    await turn(conversation, "Hola")

    await conversation.close()

    assert FIRST not in store.locked


async def test_a_title_by_hand_wins() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled("Del modelo")])
    conversation = await conversation_with(store, small, "Hecho.")

    # The escape goes: the text after it is plain text.
    assert await conversation.rename("  Mi tarea\x1b[2J  ") == "Mi tarea [2J"
    await turn(conversation, "Hola")
    await conversation.titled()

    # Named by hand before the first turn: the small model is not asked.
    assert small.requests == []
    [summary] = await store.summaries()
    assert summary.title == "Mi tarea [2J"
    await conversation.close()


async def test_a_title_by_hand_after_the_models_replaces_it() -> None:
    store = MemorySessionStore()
    small = FakeModelClient([titled("Del modelo")])
    conversation = await conversation_with(store, small, "Hecho.")
    await turn(conversation, "Hola")
    await conversation.titled()

    await conversation.rename("Otra cosa")

    [summary] = await store.summaries()
    assert summary.title == "Otra cosa"
    await conversation.close()


async def test_an_empty_title_by_hand_is_an_error() -> None:
    conversation = await conversation_with(
        MemorySessionStore(), FakeModelClient([]), "Hecho."
    )

    with pytest.raises(SessionError, match="needs some text"):
        await conversation.rename("  \n ")
    await conversation.close()


async def test_without_a_titler_there_are_no_titles() -> None:
    # `-p` and the evals (spec hito 10, §1.12).
    store = MemorySessionStore()
    conversation = await World(
        store, FakeModelClient([reply("Hecho.")])
    ).sessions.start()

    await turn(conversation, "Hola")
    await conversation.titled()

    assert not any(isinstance(entry, TitleEntry) for entry in entries(store))
    await conversation.close()


class AnswersWhenAllowed(FakeModelClient):
    """A small model that answers once the test lets it."""

    def __init__(self, response: ModelResponse) -> None:
        super().__init__([])
        self.asked = asyncio.Event()
        self.allowed = asyncio.Event()
        self._response = response

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.asked.set()
        await self.allowed.wait()
        return self._response


async def test_a_title_that_comes_during_the_next_turn_loses_nothing() -> None:
    # One save at a time: the title's and the turn's never cross.
    store = MemorySessionStore()
    small = AnswersWhenAllowed(titled("Dos turnos"))
    conversation = await conversation_with(store, small, "A.", "B.")
    await turn(conversation, "uno")
    await small.asked.wait()

    async def second() -> None:
        await turn(conversation, "dos")

    running = asyncio.create_task(second())
    small.allowed.set()
    await running
    await conversation.titled()
    await conversation.close()

    saved = entries(store)
    assert TitleEntry(title="Dos turnos") in saved
    texts = [e.message.text for e in saved if isinstance(e, MessageEntry)]
    assert texts == ["uno", "A.", "dos", "B."]
    # The session reads back whole.
    session = await store.read(FIRST)
    assert session.title == TitleEntry(title="Dos turnos")


@pytest.mark.parametrize("line", ["/new", "/resume 20261026-091502-0aaa"])
async def test_ctrl_c_while_a_command_waits_for_the_title_still_switches(
    line: str,
) -> None:
    # Review of the audit after hito 10: Ctrl+C at "[naming the session…]"
    # in /new or /resume left maha on the closed session, and the next turn
    # went to a new id; the resumed one stayed locked.
    store = MemorySessionStore()
    other = await conversation_with(store, FakeModelClient([]), "A.")
    other.id = "20261026-091502-0aaa"
    await turn(other, "Otra")
    await other.close()
    small = NeverAnswers()
    fake = FakeModelClient([reply("Hecho.")])
    world = World(store, fake, titler=titler(small), tokens=("b01c", "c0de"))
    conversation = await world.sessions.start()
    await turn(conversation, "Hola")
    await small.asked.wait()
    commands = Commands(
        world.sessions,
        conversation,
        catalog=MemoryCatalog(),
        provider="opencode-go",
        read=ScriptedInput(),
        discard=None,
        out=io.StringIO(),
        err=io.StringIO(),
        home=Path("/home/ane"),
    )
    command = parse_command(line)
    assert command is not None

    running = asyncio.create_task(commands.run(command))
    await asyncio.sleep(0.05)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert commands.conversation is not conversation
    assert conversation.id not in store.locked
    # The resumed one asks for its title too: skipped the same way.
    closing = asyncio.create_task(commands.conversation.close())
    await asyncio.sleep(0.01)
    closing.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await closing
    assert store.locked == set()


async def test_a_resume_that_fails_does_not_say_it_waits_for_the_title() -> None:
    # Second review of the audit after hito 10: "[naming the session…]" was
    # said before the step that can fail, and nothing waited after it.
    store = MemorySessionStore()
    small = NeverAnswers()
    world = World(store, FakeModelClient([reply("Hecho.")]), titler=titler(small))
    conversation = await world.sessions.start()
    await turn(conversation, "Hola")
    await small.asked.wait()
    out, err = io.StringIO(), io.StringIO()
    commands = Commands(
        world.sessions,
        conversation,
        catalog=MemoryCatalog(),
        provider="opencode-go",
        read=ScriptedInput(),
        discard=None,
        out=out,
        err=err,
        home=Path("/home/ane"),
    )
    command = parse_command("/resume 20261026-091502-0bad")
    assert command is not None

    await asyncio.wait_for(commands.run(command), timeout=2)

    assert err.getvalue().startswith("error: no session")
    assert "naming the session" not in out.getvalue()
    assert commands.conversation is conversation
    assert conversation.naming
    closing = asyncio.create_task(conversation.close(title=False))
    await closing
    assert store.locked == set()


async def test_ctrl_c_while_exit_waits_for_the_title_leaves_cleanly() -> None:
    # Review of the audit after hito 10: our Ctrl+C handler was gone while
    # leaving, so a KeyboardInterrupt unwound asyncio; /exit then ended with
    # 130 and an unsaved session was never told.
    store = MemorySessionStore()
    small = NeverAnswers()
    world = World(store, FakeModelClient([reply("Hecho.")]), titler=titler(small))
    out = io.StringIO()

    async def press_when_asked() -> None:
        await small.asked.wait()
        await asyncio.sleep(0.05)
        signal.raise_signal(signal.SIGINT)

    pressing = asyncio.create_task(press_when_asked())
    code = await converse(
        world.sessions,
        provider="opencode-go",
        catalog=MemoryCatalog(),
        read_line=ScriptedInput("Hola", "/exit"),
        out=out,
        err=io.StringIO(),
    )
    await pressing

    assert code == 0
    assert "[naming the session; Ctrl+C skips it]" in out.getvalue()
    assert FIRST not in store.locked


async def test_a_closing_signal_while_exit_waits_for_the_title_says_so() -> None:
    # Review of the audit after hito 10 (R16): it ended as a plain /exit.
    store = MemorySessionStore()
    small = NeverAnswers()
    world = World(store, FakeModelClient([reply("Hecho.")]), titler=titler(small))

    async def close_window_when_asked() -> None:
        await small.asked.wait()
        await asyncio.sleep(0.05)
        signal.raise_signal(signal.SIGHUP)

    closing = asyncio.create_task(close_window_when_asked())
    code = await converse(
        world.sessions,
        provider="opencode-go",
        catalog=MemoryCatalog(),
        read_line=ScriptedInput("Hola", "/exit"),
        out=io.StringIO(),
        err=io.StringIO(),
    )
    await closing

    assert code == 128 + signal.SIGHUP
    assert FIRST not in store.locked


class WaitsAtThePrompt:
    """What the person types, then a prompt that waits for ever."""

    def __init__(self, *lines: str) -> None:
        self._lines = list(lines)

    async def __call__(self) -> str:
        if self._lines:
            return self._lines.pop(0)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class HungUp(io.StringIO):
    """A terminal whose window was closed: writing to it fails with EIO."""

    dead = False

    def write(self, text: str) -> int:
        if self.dead:
            raise OSError(errno.EIO, "Input/output error")
        return super().write(text)


async def promptly(leaving: Coroutine[None, None, int]) -> int:
    """What `leaving` returns, if it ends within two seconds. Not wait_for:
    its cancel would end a wait for the title, as a second signal does."""
    task = asyncio.create_task(leaving)
    done, _ = await asyncio.wait([task], timeout=2)
    if not done:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        pytest.fail("maha waited for the title")
    return task.result()


@pytest.mark.parametrize("number", [signal.SIGTERM, signal.SIGHUP])
async def test_a_closing_signal_at_the_prompt_does_not_wait_for_the_title(
    number: signal.Signals,
) -> None:
    # Second review of the audit after hito 10: the signal was spent on the
    # prompt, and leaving then waited for the title with nothing to cut it,
    # up to the HTTP time limit, with nobody left to press Ctrl+C.
    store = MemorySessionStore()
    small = NeverAnswers()
    world = World(store, FakeModelClient([reply("Hecho.")]), titler=titler(small))

    async def signal_when_asked() -> None:
        await small.asked.wait()
        await asyncio.sleep(0.05)
        signal.raise_signal(number)

    sending = asyncio.create_task(signal_when_asked())
    code = await promptly(
        converse(
            world.sessions,
            provider="opencode-go",
            catalog=MemoryCatalog(),
            read_line=WaitsAtThePrompt("Hola"),
            out=io.StringIO(),
            err=io.StringIO(),
        )
    )
    await sending

    assert code == 128 + number
    saved = [e.message.text for e in entries(store) if isinstance(e, MessageEntry)]
    assert saved == ["Hola", "Hecho."]
    assert FIRST not in store.locked


class HungUpTerminal(HungUp):
    """A closed window that was a terminal: the spinner draws on it."""

    def isatty(self) -> bool:
        return True


async def test_a_closed_window_while_the_spinner_spins_ends_with_129() -> None:
    # Third review of the audit after hito 10: stopping the spinner, in the
    # cleanup of the cut answer, wrote to the dead terminal; its EIO took
    # the place of the cancellation, and maha ended with a traceback.
    store = MemorySessionStore()
    world = World(store, FakeModelClient([[HANG]]))
    out = HungUpTerminal()

    async def close_the_window() -> None:
        await asyncio.sleep(0.2)  # the model never answers; the spinner spins
        out.dead = True
        signal.raise_signal(signal.SIGHUP)

    closing = asyncio.create_task(close_the_window())
    code = await promptly(
        converse(
            world.sessions,
            provider="opencode-go",
            catalog=MemoryCatalog(),
            read_line=WaitsAtThePrompt("Hola"),
            out=out,
            err=out,
        )
    )
    await closing

    assert code == 128 + signal.SIGHUP
    assert FIRST not in store.locked


async def test_a_closed_window_while_new_waits_for_the_title_ends_with_129() -> None:
    # Third review too: "[new session]" in the cleanup of the cut /new, then
    # "error: internal", both to the dead terminal.
    store = MemorySessionStore()
    small = NeverAnswers()
    world = World(store, FakeModelClient([reply("Hecho.")]), titler=titler(small))
    out = HungUp()

    async def close_the_window() -> None:
        await small.asked.wait()
        await asyncio.sleep(0.1)  # /new waits for the title
        out.dead = True
        signal.raise_signal(signal.SIGHUP)

    closing = asyncio.create_task(close_the_window())
    code = await promptly(
        converse(
            world.sessions,
            provider="opencode-go",
            catalog=MemoryCatalog(),
            read_line=WaitsAtThePrompt("Hola", "/new"),
            out=out,
            err=out,
        )
    )
    await closing

    assert code == 128 + signal.SIGHUP
    assert store.locked == set()


async def test_a_closed_window_with_an_unsaved_session_ends_with_129(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Third review too: "session not saved" at the end, after a closing
    # signal, goes to a dead terminal; it ends nothing. The disk keeps
    # failing, so the warning is due.
    monkeypatch.setattr("tests.fakes.sessions.MemoryLog", BrokenLog)
    monkeypatch.setattr(BrokenLog, "failures", 10)
    store = MemorySessionStore()
    world = World(store, FakeModelClient([reply("Hecho.")]))
    out = HungUp()
    answered = asyncio.Event()

    async def read() -> str:
        if not answered.is_set():
            answered.set()
            return "Hola"
        out.dead = True
        signal.raise_signal(signal.SIGHUP)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    code = await promptly(
        converse(
            world.sessions,
            provider="opencode-go",
            catalog=MemoryCatalog(),
            read_line=read,
            out=out,
            err=out,
        )
    )

    assert code == 128 + signal.SIGHUP
    assert BrokenLog.failures < 10  # it did try to save
    assert FIRST not in store.locked


async def test_a_closed_window_seen_before_its_signal_ends_with_129() -> None:
    # Third review of the audit after hito 10, by hand with maha in a pty:
    # the prompt got its end of file before the loop handled SIGHUP; the
    # new line after it hit the dead terminal with no closing signal yet,
    # and maha ended with 1.
    store = MemorySessionStore()
    world = World(store, FakeModelClient([reply("Hecho.")]))
    out = HungUp()
    answered = False

    async def read() -> str:
        nonlocal answered
        if not answered:
            answered = True
            return "Hola"
        out.dead = True
        raise EOFError

    code = await promptly(
        converse(
            world.sessions,
            provider="opencode-go",
            catalog=MemoryCatalog(),
            read_line=read,
            out=out,
            err=out,
        )
    )

    assert code == 128 + signal.SIGHUP
    saved = [e.message.text for e in entries(store) if isinstance(e, MessageEntry)]
    assert saved == ["Hola", "Hecho."]
    assert FIRST not in store.locked


async def test_a_closed_window_when_leaving_does_not_skip_closing() -> None:
    # Third review too: "naming the session" to a dead terminal, before its
    # SIGHUP, skipped the close; what was pending would be lost.
    store = MemorySessionStore()
    small = NeverAnswers()
    world = World(store, FakeModelClient([reply("Hecho.")]), titler=titler(small))
    out = HungUp()
    lines = ["Hola", "/exit"]

    async def read() -> str:
        line = lines.pop(0)
        if line == "/exit":
            await small.asked.wait()
            out.dead = True
        return line

    code = await promptly(
        converse(
            world.sessions,
            provider="opencode-go",
            catalog=MemoryCatalog(),
            read_line=read,
            out=out,
            err=out,
        )
    )

    assert code == 128 + signal.SIGHUP
    assert FIRST not in store.locked


async def test_a_closed_window_while_a_title_comes_still_closes_the_session() -> None:
    # Second review of the audit after hito 10: "naming the session" was
    # written to the dead terminal before closing, and its EIO left the
    # session unclosed, with a traceback instead of 129.
    store = MemorySessionStore()
    small = NeverAnswers()
    world = World(store, FakeModelClient([reply("Hecho.")]), titler=titler(small))
    out = HungUp()

    async def close_the_window() -> None:
        await small.asked.wait()
        await asyncio.sleep(0.05)
        out.dead = True
        signal.raise_signal(signal.SIGHUP)

    closing = asyncio.create_task(close_the_window())
    code = await promptly(
        converse(
            world.sessions,
            provider="opencode-go",
            catalog=MemoryCatalog(),
            read_line=WaitsAtThePrompt("Hola"),
            out=out,
            err=out,
        )
    )
    await closing

    assert code == 128 + signal.SIGHUP
    assert FIRST not in store.locked
