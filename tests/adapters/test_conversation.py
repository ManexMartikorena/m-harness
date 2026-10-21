import asyncio
import contextlib
import io
import os
import signal
from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path

import pytest

from mharness.adapters.cli.conversation import EXIT_INTERRUPTED, StdinLines, converse
from mharness.adapters.cli.spinner import CLEAR_LINE
from mharness.application.chat import Chat
from mharness.domain.errors import ModelAuthError, ModelUnavailableError
from mharness.domain.events import TextDelta
from mharness.domain.model import Usage
from tests.fakes.model import END, FakeModelClient, Gate, reply

HEADER = f"maha {version('m-harness')} · opencode-go · glm-5.3-flash · /exit to quit"


class ScriptedInput:
    """Returns the scripted lines, then raises EOFError (Ctrl+D)."""

    def __init__(self, *lines: str) -> None:
        self._lines = list(lines)

    async def __call__(self) -> str:
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)


async def run(fake: FakeModelClient, *lines: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = await converse(
        Chat(fake, model="glm-5.3-flash"),
        provider="opencode-go",
        model="glm-5.3-flash",
        read_line=ScriptedInput(*lines),
        out=out,
        err=err,
    )
    return code, out.getvalue(), err.getvalue()


async def test_shows_the_answer_and_the_tokens() -> None:
    fake = FakeModelClient(
        [
            reply("Hola, Ane.", usage=Usage(input_tokens=12, output_tokens=9)),
            reply("Te llamas Ane.", usage=Usage(input_tokens=31, output_tokens=5)),
        ]
    )

    code, out, err = await run(fake, "Hola, soy Ane", "¿Cómo me llamo?", "/exit")

    assert code == 0
    assert err == ""
    assert out == (
        f"{HEADER}\n"
        "> Hola, Ane.\n"
        "  [tokens: 12 in · 9 out]\n"
        "> Te llamas Ane.\n"
        "  [tokens: 31 in · 5 out]\n"
        "> "
    )


async def test_exit_command_ends_with_zero() -> None:
    code, _, _ = await run(FakeModelClient([]), "/exit", "never read")

    assert code == 0


async def test_end_of_input_ends_with_zero() -> None:
    code, out, _ = await run(FakeModelClient([]))

    assert code == 0
    assert out == f"{HEADER}\n> \n"


async def test_empty_line_does_not_call_the_model() -> None:
    fake = FakeModelClient([])

    code, _, _ = await run(fake, "", "   ", "/exit")

    assert code == 0
    assert fake.requests == []


async def test_model_error_goes_to_stderr_and_the_conversation_goes_on() -> None:
    fake = FakeModelClient([ModelAuthError("HTTP 401: Invalid key"), reply("Hola.")])

    code, out, err = await run(fake, "Hola", "Hola otra vez", "/exit")

    assert code == 0
    assert err == "error: HTTP 401: Invalid key\n"
    assert "Hola.\n" in out


async def test_ctrl_c_ends_with_130() -> None:
    async def interrupt() -> str:
        signal.raise_signal(signal.SIGINT)
        await asyncio.Event().wait()  # waits for input that never comes
        raise AssertionError("not cancelled")

    out = io.StringIO()
    code = await converse(
        Chat(FakeModelClient([]), model="m"),
        provider="p",
        model="m",
        read_line=interrupt,
        out=out,
        err=io.StringIO(),
    )

    assert code == EXIT_INTERRUPTED


async def test_other_cancellations_propagate() -> None:
    started = asyncio.Event()

    async def wait_forever() -> str:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("not cancelled")

    task = asyncio.create_task(
        converse(
            Chat(FakeModelClient([]), model="m"),
            provider="p",
            model="m",
            read_line=wait_forever,
            out=io.StringIO(),
            err=io.StringIO(),
        )
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.fixture
def pipe() -> Iterator[tuple[int, int]]:
    read_fd, write_fd = os.pipe()
    yield read_fd, write_fd
    for fd in (read_fd, write_fd):
        with contextlib.suppress(OSError):  # the test may have closed it
            os.close(fd)


async def test_stdin_lines_reads_line_by_line(pipe: tuple[int, int]) -> None:
    read_fd, write_fd = pipe
    os.write(write_fd, "Hola, soy Ane\r\n¿Cómo me llamo?\nsin salto".encode())
    os.close(write_fd)
    lines = StdinLines(read_fd)

    assert await lines.readline() == "Hola, soy Ane"
    assert await lines.readline() == "¿Cómo me llamo?"
    assert await lines.readline() == "sin salto"
    with pytest.raises(EOFError):
        await lines.readline()


async def test_stdin_lines_waits_for_a_whole_line(pipe: tuple[int, int]) -> None:
    read_fd, write_fd = pipe
    lines = StdinLines(read_fd)
    pending = asyncio.create_task(lines.readline())

    os.write(write_fd, b"Ho")
    await asyncio.sleep(0.01)
    assert not pending.done()
    os.write(write_fd, b"la\n")

    assert await pending == "Hola"


async def test_stdin_lines_reads_a_regular_file(tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    path.write_text("Hola\n", encoding="utf-8")
    fd = os.open(path, os.O_RDONLY)
    try:
        lines = StdinLines(fd)

        assert await lines.readline() == "Hola"
        with pytest.raises(EOFError):
            await lines.readline()
    finally:
        os.close(fd)


# Streaming (spec hito 3, §1.10).


async def test_text_is_shown_before_the_stream_ends() -> None:
    gate = Gate()
    fake = FakeModelClient(
        [[TextDelta(text="Hola, "), gate, TextDelta(text="Ane."), END]]
    )
    out = io.StringIO()
    task = asyncio.ensure_future(
        converse(
            Chat(fake, model="m"),
            provider="p",
            model="m",
            read_line=ScriptedInput("Hola"),
            out=out,
            err=io.StringIO(),
        )
    )
    for _ in range(100):
        if out.getvalue().endswith("Hola, "):
            break
        await asyncio.sleep(0)

    assert out.getvalue().endswith("> Hola, ")
    gate.release()
    assert await task == 0
    assert out.getvalue().endswith("> Hola, Ane.\n> \n")


async def test_no_token_line_when_usage_is_all_zeros() -> None:
    code, out, _ = await run(FakeModelClient([reply("Hola.")]), "Hola", "/exit")

    assert code == 0
    assert out == f"{HEADER}\n> Hola.\n> "


async def test_error_mid_stream_keeps_the_text_and_goes_on() -> None:
    fake = FakeModelClient(
        [[TextDelta(text="Hol"), ModelUnavailableError("cut")], reply("Hola.")]
    )

    code, out, err = await run(fake, "Hola", "Hola otra vez", "/exit")

    assert code == 0
    assert out == f"{HEADER}\n> Hol\n> Hola.\n> "
    assert err == "error: cut\n"


# Spinner (spec hito 3, §1.12).


class FakeTerminal(io.StringIO):
    """A StringIO that says it is a terminal."""

    def isatty(self) -> bool:
        return True


async def converse_until_spinning(
    fake: FakeModelClient, gate: Gate, out: io.StringIO, err: io.StringIO
) -> int:
    task = asyncio.ensure_future(
        converse(
            Chat(fake, model="m"),
            provider="p",
            model="m",
            read_line=ScriptedInput("Hola"),
            out=out,
            err=err,
        )
    )
    if out.isatty():
        for _ in range(200):  # at most 2 s
            if "⠋" in out.getvalue():
                break
            await asyncio.sleep(0.01)
    else:
        # Time for a spinner that should not appear.
        await asyncio.sleep(0.15)
    gate.release()
    return await task


@pytest.mark.parametrize("no_color", ["", "1"])
async def test_spinner_is_erased_before_the_first_text(
    no_color: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NO_COLOR", no_color)
    gate = Gate()
    fake = FakeModelClient([[gate, TextDelta(text="Hola."), END]])
    out = FakeTerminal()

    code = await converse_until_spinning(fake, gate, out, io.StringIO())

    text = out.getvalue()
    assert code == 0
    assert "⠋" in text
    assert ("\x1b[3" in text) is (no_color == "")
    assert f"{CLEAR_LINE}Hola.\n" in text


async def test_spinner_is_erased_before_an_error() -> None:
    gate = Gate()
    fake = FakeModelClient([[gate, ModelUnavailableError("down")]])
    out, err = FakeTerminal(), io.StringIO()

    code = await converse_until_spinning(fake, gate, out, err)

    assert code == 0
    assert out.getvalue().endswith(f"{CLEAR_LINE}> \n")
    assert err.getvalue() == "error: down\n"


async def test_no_escape_codes_when_not_a_terminal() -> None:
    gate = Gate()
    fake = FakeModelClient([[gate, TextDelta(text="Hola."), END]])
    out = io.StringIO()

    await converse_until_spinning(fake, gate, out, io.StringIO())

    assert "\x1b" not in out.getvalue()
    assert "maha 0" in out.getvalue()  # only the header mentions maha
