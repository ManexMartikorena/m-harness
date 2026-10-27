import asyncio
import contextlib
import io
import json
import os
import pty
import signal
from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path

import pytest

from mharness.adapters.cli.approval import TerminalApproval
from mharness.adapters.cli.conversation import EXIT_INTERRUPTED, converse
from mharness.adapters.cli.input import StdinLines
from mharness.adapters.cli.spinner import CLEAR_LINE
from mharness.adapters.commands import LocalCommandRunner
from mharness.adapters.tools import RunCommand
from mharness.application.agent import Agent
from mharness.application.sessions import Sessions
from mharness.application.tools import ToolRegistry
from mharness.domain.approval import ApprovalRequest, Decision
from mharness.domain.errors import ModelAuthError, ModelUnavailableError
from mharness.domain.events import TextDelta
from mharness.domain.messages import ToolCallBlock, ToolResultBlock
from mharness.domain.model import Usage
from mharness.domain.tools import ToolError
from tests.adapters.test_local_runner import gone, written_pid
from tests.fakes.approval import FakeApproval
from tests.fakes.catalog import MemoryCatalog
from tests.fakes.model import END, HANG, FakeModelClient, Gate, reply, tool_calls
from tests.fakes.sessions import MemorySessionStore
from tests.fakes.terminal import ScriptedInput
from tests.fakes.tools import FakeTool
from tests.fakes.tracing import MemoryTraceSink

HEADER = (
    f"maha {version('m-harness')} · opencode-go · glm-5.3-flash · /help for commands"
)


def solo(agent: Agent) -> Sessions:
    """Sessions in memory whose new conversation is `agent`."""
    return Sessions(
        MemorySessionStore(),
        lambda model, history: agent,
        cwd="/home/ana/proyecto",
        provider="opencode-go",
        model=agent.model,
        version="0.6.0",
        traces=MemoryTraceSink(),
    )


async def run(fake: FakeModelClient, *lines: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = await converse(
        solo(
            Agent(
                fake,
                ToolRegistry(),
                gate=FakeApproval(),
                model="glm-5.3-flash",
                catalog=MemoryCatalog(),
                provider="opencode-go",
            )
        ),
        provider="opencode-go",
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
        solo(
            Agent(
                FakeModelClient([]),
                ToolRegistry(),
                gate=FakeApproval(),
                model="m",
                catalog=MemoryCatalog(),
                provider="opencode-go",
            )
        ),
        provider="p",
        read_line=interrupt,
        out=out,
        err=io.StringIO(),
    )

    assert code == EXIT_INTERRUPTED


@pytest.mark.parametrize(
    ("number", "code"), [(signal.SIGTERM, 143), (signal.SIGHUP, 129)]
)
async def test_closing_signals_end_with_128_plus_the_signal(
    number: signal.Signals, code: int
) -> None:
    # Closing the window (SIGHUP) or `kill` (SIGTERM) end maha like Ctrl+C
    # does, without going back to the prompt (spec
    # mejora-2026-10-26-deuda-pre-hito-6, A4).
    async def close() -> str:
        signal.raise_signal(number)
        await asyncio.Event().wait()
        raise AssertionError("not cancelled")

    result = await converse(
        solo(
            Agent(
                FakeModelClient([]),
                ToolRegistry(),
                gate=FakeApproval(),
                model="m",
                catalog=MemoryCatalog(),
                provider="opencode-go",
            )
        ),
        provider="p",
        read_line=close,
        out=io.StringIO(),
        err=io.StringIO(),
    )

    assert result == code


async def test_sigterm_during_a_command_kills_it(tmp_path: Path) -> None:
    # The command runs in its own group, so the terminal's SIGHUP never
    # reaches it: maha has to kill it on its way out.
    pidfile = tmp_path / "pid"
    command = f"sleep 30 & echo $! > {pidfile}; wait"
    call = ToolCallBlock(
        id="c1", name="run_command", arguments=json.dumps({"command": command})
    )
    tools = ToolRegistry([RunCommand(tmp_path, LocalCommandRunner(), {})])
    agent = Agent(
        FakeModelClient([tool_calls(call)]),
        tools,
        gate=FakeApproval(["once"]),
        model="m",
        catalog=MemoryCatalog(),
        provider="opencode-go",
    )

    async def close_when_it_runs() -> int:
        pid = await written_pid(pidfile)
        signal.raise_signal(signal.SIGTERM)
        return pid

    closing = asyncio.create_task(close_when_it_runs())
    result = await converse(
        solo(agent),
        provider="p",
        read_line=ScriptedInput("ejecuta"),
        out=io.StringIO(),
        err=io.StringIO(),
    )
    grandchild = await closing

    assert result == 143
    assert await gone(grandchild)


async def test_other_cancellations_propagate() -> None:
    started = asyncio.Event()

    async def wait_forever() -> str:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("not cancelled")

    task = asyncio.create_task(
        converse(
            solo(
                Agent(
                    FakeModelClient([]),
                    ToolRegistry(),
                    gate=FakeApproval(),
                    model="m",
                    catalog=MemoryCatalog(),
                    provider="opencode-go",
                )
            ),
            provider="p",
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


async def test_stdin_lines_discards_what_it_kept(pipe: tuple[int, int]) -> None:
    # A pasted block lands whole in the buffer: its next line must not answer
    # a question (spec mejora-2026-10-26-deuda-pre-hito-6, A2).
    read_fd, write_fd = pipe
    os.write(write_fd, b"borra los temporales\ny\n")
    lines = StdinLines(read_fd)
    assert await lines.readline() == "borra los temporales"

    assert lines.discard() is True
    assert lines.discard() is False
    os.write(write_fd, b"n\n")
    assert await lines.readline() == "n"


async def test_stdin_lines_discards_what_the_terminal_holds() -> None:
    # Typed ahead and not read yet: still in the terminal's queue.
    main, side = pty.openpty()
    try:
        lines = StdinLines(side)
        os.write(main, b"y\n")
        await asyncio.sleep(0.05)

        assert lines.discard() is True
        os.write(main, b"n\n")
        assert await lines.readline() == "n"
    finally:
        os.close(main)
        os.close(side)


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
            solo(
                Agent(
                    fake,
                    ToolRegistry(),
                    gate=FakeApproval(),
                    model="m",
                    catalog=MemoryCatalog(),
                    provider="opencode-go",
                )
            ),
            provider="p",
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
            solo(
                Agent(
                    fake,
                    ToolRegistry(),
                    gate=FakeApproval(),
                    model="m",
                    catalog=MemoryCatalog(),
                    provider="opencode-go",
                )
            ),
            provider="p",
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


# Ctrl+C during an answer (spec hito 3, §1.10).


async def interrupt_when(out: io.StringIO, text: str) -> None:
    """Press Ctrl+C once `text` is on the screen."""
    for _ in range(200):  # at most 2 s
        if text in out.getvalue():
            break
        await asyncio.sleep(0.01)
    signal.raise_signal(signal.SIGINT)


async def test_ctrl_c_during_an_answer_goes_back_to_the_prompt() -> None:
    fake = FakeModelClient([[TextDelta(text="Esperando"), HANG], reply("Hola.")])
    out = io.StringIO()
    pressing = asyncio.ensure_future(interrupt_when(out, "Esperando"))

    code = await converse(
        solo(
            Agent(
                fake,
                ToolRegistry(),
                gate=FakeApproval(),
                model="m",
                catalog=MemoryCatalog(),
                provider="opencode-go",
            )
        ),
        provider="p",
        read_line=ScriptedInput("Cuéntame algo", "Hola", "/exit"),
        out=out,
        err=io.StringIO(),
    )
    await pressing

    assert code == 0
    assert out.getvalue().endswith("> Esperando\n  [interrupted]\n> Hola.\n> ")
    # The cut answer is kept, marked (spec hito 6, §1.7): the model sees it.
    sent = fake.requests[1].messages
    assert [(m.text, m.interrupted) for m in sent] == [
        ("Cuéntame algo", False),
        ("Esperando", True),
        ("Hola", False),
    ]


async def test_ctrl_c_while_the_spinner_spins() -> None:
    fake = FakeModelClient([[HANG]])
    out = FakeTerminal()
    pressing = asyncio.ensure_future(interrupt_when(out, "⠋"))

    code = await converse(
        solo(
            Agent(
                fake,
                ToolRegistry(),
                gate=FakeApproval(),
                model="m",
                catalog=MemoryCatalog(),
                provider="opencode-go",
            )
        ),
        provider="p",
        read_line=ScriptedInput("Hola"),
        out=out,
        err=io.StringIO(),
    )
    await pressing

    assert code == 0
    assert out.getvalue().endswith(f"{CLEAR_LINE}  [interrupted]\n> \n")


# Tool calls in the terminal (spec hito 4, §1.9).


def call(id: str, arguments: str = '{"text": "Hola"}') -> ToolCallBlock:
    return ToolCallBlock(id=id, name="echo", arguments=arguments)


async def run_with_tools(
    fake: FakeModelClient, *lines: str, tool: FakeTool | None = None, steps: int = 25
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    registry = ToolRegistry([tool or FakeTool()])
    code = await converse(
        solo(
            Agent(
                fake,
                registry,
                gate=FakeApproval(),
                model="m",
                catalog=MemoryCatalog(),
                provider="opencode-go",
                max_steps=steps,
            )
        ),
        provider="p",
        read_line=ScriptedInput(*lines),
        out=out,
        err=err,
    )
    return code, out.getvalue(), err.getvalue()


async def test_shows_each_call_and_the_answer() -> None:
    fake = FakeModelClient(
        [
            tool_calls(
                call("c1"),
                text="Voy a mirarlo.",
                usage=Usage(input_tokens=200, output_tokens=30),
            ),
            reply("Dice Hola.", usage=Usage(input_tokens=274, output_tokens=92)),
        ]
    )

    code, out, err = await run_with_tools(fake, "¿Qué dice?", "/exit")

    assert code == 0
    assert err == ""
    assert out.endswith(
        "> Voy a mirarlo.\n"
        '  → echo(text="Hola")\n'
        "  ✓ 10 chars\n"
        "Dice Hola.\n"
        "  [tokens: 474 in · 122 out · 1 call]\n"
        "> "
    )


async def test_a_failed_call_is_marked() -> None:
    fake = FakeModelClient([tool_calls(call("c1", '{"text": 3}')), reply("Vaya.")])

    _, out, _ = await run_with_tools(fake, "Hola", "/exit")

    assert "  → echo(text=3)\n  ✗ error: invalid arguments: text:" in out


async def test_invalid_json_arguments_are_shown_as_written() -> None:
    fake = FakeModelClient([tool_calls(call("c1", '{"text": ')), reply("Vaya.")])

    _, out, _ = await run_with_tools(fake, "Hola", "/exit")

    assert '  → echo({"text": )\n' in out


async def test_deeply_nested_arguments_are_shown_as_written() -> None:
    # json.loads raises RecursionError, not ValueError (spec
    # mejora-2026-10-23-deuda-hito-5, A1).
    nested = "[" * 100_000 + "]" * 100_000
    fake = FakeModelClient([tool_calls(call("c1", nested)), reply("Vaya.")])

    code, out, _ = await run_with_tools(fake, "Hola", "/exit")

    assert code == 0
    assert "  → echo([[[[" in out
    assert "  ✗ error: arguments are not a valid JSON object" in out


async def test_long_calls_are_cut() -> None:
    long_text = "x" * 300
    arguments = f'{{"text": "{long_text}"}}'
    fake = FakeModelClient([tool_calls(call("c1", arguments)), reply("Ok.")])

    _, out, _ = await run_with_tools(fake, "Hola", "/exit")

    shown = next(line for line in out.splitlines() if "→" in line).split("→ ")[1]
    assert len(shown) == 100
    assert shown.endswith("…")


async def test_calls_are_counted_in_plural() -> None:
    usage = Usage(input_tokens=1, output_tokens=1)
    fake = FakeModelClient(
        [tool_calls(call("c1"), call("c2"), usage=usage), reply("Ok.", usage=usage)]
    )

    _, out, _ = await run_with_tools(fake, "Hola", "/exit")

    assert "  [tokens: 2 in · 2 out · 2 calls]\n" in out


async def test_step_limit_is_shown() -> None:
    usage = Usage(input_tokens=1, output_tokens=1)
    fake = FakeModelClient([tool_calls(call(f"c{i}"), usage=usage) for i in range(2)])

    _, out, _ = await run_with_tools(fake, "Hola", "/exit", steps=2)

    assert "  [step limit reached: 2]\n  [tokens: 2 in · 2 out · 2 calls]\n" in out


async def test_internal_tool_error_goes_to_stderr() -> None:
    fake = FakeModelClient([tool_calls(call("c1")), reply("Vaya.")])

    _, out, err = await run_with_tools(
        fake, "Hola", "/exit", tool=FakeTool(results=[KeyError("boom")])
    )

    assert '  ✗ error: internal error in tool "echo"\n' in out
    assert err == "warning: tool \"echo\" failed: KeyError: 'boom'\n"


class BrokenGate:
    """The terminal fails while asking, as an EIO would."""

    async def decide(self, request: ApprovalRequest) -> Decision:
        raise OSError(5, "Input/output error")


async def test_an_unexpected_error_ends_only_the_answer() -> None:
    # Not a ModelError: maha says so and goes back to the prompt, keeping
    # what the agent kept (spec mejora-2026-10-26-deuda-pre-hito-6, B1).
    request = ApprovalRequest(tool="echo", title="echo", detail="", scope=None)
    tool = FakeTool(permission="effect", requests=[request])
    fake = FakeModelClient([tool_calls(call("c1")), reply("Sigo.")])
    out, err = io.StringIO(), io.StringIO()

    code = await converse(
        solo(
            Agent(
                fake,
                ToolRegistry([tool]),
                gate=BrokenGate(),
                model="m",
                catalog=MemoryCatalog(),
                provider="opencode-go",
            )
        ),
        provider="p",
        read_line=ScriptedInput("Hola", "Otra", "/exit"),
        out=out,
        err=err,
    )

    assert code == 0
    assert err.getvalue() == "error: internal: OSError: [Errno 5] Input/output error\n"
    assert "Sigo." in out.getvalue()


async def test_ctrl_c_during_a_tool_goes_back_to_the_prompt() -> None:
    gate = asyncio.Event()  # never set: the tool waits
    fake = FakeModelClient([tool_calls(call("c1")), reply("Hola.")])
    out = io.StringIO()
    pressing = asyncio.ensure_future(interrupt_when(out, "→ echo"))
    agent = Agent(
        fake,
        ToolRegistry([FakeTool(gate=gate)]),
        gate=FakeApproval(),
        model="m",
        catalog=MemoryCatalog(),
        provider="opencode-go",
    )

    code = await converse(
        solo(agent),
        provider="p",
        read_line=ScriptedInput("Usa la herramienta", "/exit"),
        out=out,
        err=io.StringIO(),
    )
    await pressing

    assert code == 0
    assert out.getvalue().endswith('  → echo(text="Hola")\n  [interrupted]\n> ')
    # The tool had started: the turn is kept (spec hito 5, §1.5).
    result = agent.messages[-1].blocks[0]
    assert isinstance(result, ToolResultBlock)
    assert (result.content, result.is_error) == ("error: cancelled by the user", True)


async def test_ctrl_c_during_the_question_starts_a_new_line() -> None:
    # The question leaves the cursor after "Allow? …:" (spec
    # mejora-2026-10-26-deuda-pre-hito-6, B8).
    async def no_answer() -> str:
        await asyncio.Event().wait()
        raise AssertionError("not cancelled")

    request = ApprovalRequest(tool="echo", title="echo", detail="", scope=None)
    tool = FakeTool(permission="effect", requests=[request])
    fake = FakeModelClient([tool_calls(call("c1"))])
    out = io.StringIO()
    pressing = asyncio.ensure_future(interrupt_when(out, "Allow?"))
    agent = Agent(
        fake,
        ToolRegistry([tool]),
        gate=TerminalApproval(no_answer, out),
        model="m",
        catalog=MemoryCatalog(),
        provider="opencode-go",
    )

    await converse(
        solo(agent),
        provider="p",
        read_line=ScriptedInput("Usa la herramienta", "/exit"),
        out=out,
        err=io.StringIO(),
    )
    await pressing

    assert "  └ Allow? [y] yes · [n] no: \n  [interrupted]\n" in out.getvalue()


async def test_control_characters_from_the_model_and_tools_are_escaped() -> None:
    # ESC and \r could repaint the screen, and bidi controls reorder it: the
    # question below a call could lie (spec mejora-2026-10-23-deuda-hito-5,
    # A2).
    tool = FakeTool("echo", results=[ToolError("bad\x1b[2J")])
    fake = FakeModelClient(
        [
            tool_calls(
                call("c1", '{"text": "a\\u001b[31mb\\u202ec"}'),
                text="Mira\x1b]0;title\x07\r",
            ),
            reply("Fin\x9b."),
        ]
    )

    _, out, _ = await run_with_tools(fake, "Hola", "/exit", tool=tool)

    for unsafe in ("\x1b", "\r", "\u202e", "\x9b", "\x07"):
        assert unsafe not in out
    assert "Mira\\x1b]0;title\\x07\\x0d" in out
    # json.dumps already writes ESC as \u001b; the bidi control is escaped.
    assert '→ echo(text="a\\u001b[31mb\\u202ec")' in out
    assert "✗ error: bad\\x1b[2J" in out
    assert "Fin\\x9b." in out


# The question in the conversation (spec hito 5, §1.10 and §4.6.3)


async def converse_asking(
    fake: FakeModelClient, tool: FakeTool, *lines: str
) -> tuple[int, str]:
    """The conversation and the question read the same input."""
    out = io.StringIO()
    read = ScriptedInput(*lines)
    gate = TerminalApproval(read, out)
    code = await converse(
        solo(
            Agent(
                fake,
                ToolRegistry([tool]),
                gate=gate,
                model="m",
                catalog=MemoryCatalog(),
                provider="opencode-go",
            )
        ),
        provider="p",
        read_line=read,
        out=out,
        err=io.StringIO(),
    )
    return code, out.getvalue()


WRITE_REQUEST = ApprovalRequest(
    tool="write", title="create notas.txt (1 line)", detail="Hola", scope="write"
)


async def test_an_approved_call_runs_after_the_question() -> None:
    tool = FakeTool("write", permission="effect", requests=[WRITE_REQUEST])
    fake_calls = [ToolCallBlock(id="c1", name="write", arguments='{"text": "Hola"}')]
    fake = FakeModelClient([tool_calls(*fake_calls), reply("Hecho.")])

    code, out = await converse_asking(fake, tool, "Escribe", "y", "/exit")

    assert code == 0
    assert (
        '  → write(text="Hola")\n'
        "  ┌ create notas.txt (1 line)\n"
        "  │ Hola\n"
        "  └ Allow? [y] yes · [a] always this session · [n] no: "
        "  ✓ 10 chars\n"
        "Hecho.\n"
    ) in out


async def test_a_denied_call_ends_the_turn_and_says_so() -> None:
    tool = FakeTool("write", permission="effect", requests=[WRITE_REQUEST])
    calls = [ToolCallBlock(id="c1", name="write", arguments='{"text": "Hola"}')]
    fake = FakeModelClient([tool_calls(*calls)])

    code, out = await converse_asking(fake, tool, "Escribe", "n", "/exit")

    assert code == 0
    assert (
        "  └ Allow? [y] yes · [a] always this session · [n] no: "
        "  ✗ error: the user denied this call\n"
        "  [denied: tell maha how to continue]\n"
    ) in out
    assert tool.calls == []
