"""The conversation in the terminal: read, send, show (spec hito 2, §1.11).

The answer is shown as it arrives (spec hito 3, §1.10), with every tool
call the agent makes (spec hito 4, §1.9).
"""

import asyncio
import json
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from importlib.metadata import version
from typing import TextIO

from mharness.adapters.cli.spinner import Spinner, use_color
from mharness.application.agent import Agent
from mharness.domain.agent_events import ToolCallProposed, ToolFinished, TurnFinished
from mharness.domain.errors import ModelError
from mharness.domain.events import TextDelta
from mharness.domain.messages import ToolCallBlock
from mharness.domain.model import Usage

DISTRIBUTION = "m-harness"
# Terminal convention for a program stopped by Ctrl+C: 128 + SIGINT.
EXIT_INTERRUPTED = 130
# A tool call is shown in one line, cut to this length.
MAX_CALL = 100

type ReadLine = Callable[[], Awaitable[str]]


class _Sigint:
    """Whether Ctrl+C asked to cancel the task, and that request was not
    handled yet. Tells it apart from any other cancellation."""

    def __init__(self) -> None:
        self.pending = False


class StdinLines:
    """Reads lines from a file descriptor without blocking the event loop.

    Raises `EOFError` at the end (Ctrl+D). It uses no thread: a thread blocked
    in `input()` keeps `maha` from exiting on Ctrl+C.
    """

    def __init__(self, fd: int = 0) -> None:
        self._fd = fd
        self._buffer = b""

    async def readline(self) -> str:
        while b"\n" not in self._buffer:
            chunk = await self._read()
            if not chunk:
                if not self._buffer:
                    raise EOFError
                # Last line without a newline.
                self._buffer += b"\n"
            self._buffer += chunk
        line, _, self._buffer = self._buffer.partition(b"\n")
        # Splitting bytes at b"\n" never cuts a UTF-8 character.
        return line.decode("utf-8", errors="replace").removesuffix("\r")

    async def _read(self) -> bytes:
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[None] = loop.create_future()

        def on_readable() -> None:
            # It may fire again before the reader is removed.
            if not ready.done():
                ready.set_result(None)

        try:
            loop.add_reader(self._fd, on_readable)
        except PermissionError:
            # A regular file (`maha < notes.txt`) cannot be watched; reading
            # it never blocks.
            return os.read(self._fd, 4096)
        try:
            await ready
        finally:
            loop.remove_reader(self._fd)
        return os.read(self._fd, 4096)


async def converse(
    agent: Agent,
    *,
    provider: str,
    model: str,
    read_line: ReadLine | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Run the conversation until /exit, Ctrl+D or Ctrl+C; return the exit code."""
    read = read_line or StdinLines().readline
    # Looked up now, not at import time, in case they were replaced.
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    assert task is not None
    sigint = _Sigint()

    def on_sigint() -> None:
        sigint.pending = True
        task.cancel()

    loop.add_signal_handler(signal.SIGINT, on_sigint)
    try:
        return await _turns(agent, provider, model, read, out, err, sigint)
    except asyncio.CancelledError:
        # Ctrl+C at the prompt ends `maha`; an answer handles its own.
        if not sigint.pending:
            raise
        task.uncancel()
        print(file=out)
        return EXIT_INTERRUPTED
    finally:
        loop.remove_signal_handler(signal.SIGINT)


async def _turns(
    agent: Agent,
    provider: str,
    model: str,
    read: ReadLine,
    out: TextIO,
    err: TextIO,
    sigint: _Sigint,
) -> int:
    print(
        f"maha {version(DISTRIBUTION)} · {provider} · {model} · /exit to quit",
        file=out,
    )
    while True:
        print("> ", end="", file=out, flush=True)
        try:
            line = (await read()).strip()
        except EOFError:
            print(file=out)
            return 0
        if not line:
            continue
        if line == "/exit":
            return 0
        await _answer(agent, line, out, err, sigint)


async def _answer(
    agent: Agent, line: str, out: TextIO, err: TextIO, sigint: _Sigint
) -> None:
    """Show one answer as it arrives.

    A model error or Ctrl+C ends only this answer, which is not kept (spec
    hito 3, §1.10).
    """
    # True while the cursor is after text, not at the start of a line.
    wrote = False
    # Covers each wait for the model (spec hito 3, §1.12).
    spinner = Spinner(out, color=use_color())
    spinner.start()
    try:
        async with aclosing(agent.run(line)) as events:
            async for event in events:
                match event:
                    case TextDelta(text=text):
                        await spinner.stop()
                        out.write(text)
                        out.flush()
                        wrote = True
                    case ToolCallProposed(call=call):
                        await spinner.stop()
                        if wrote:
                            print(file=out)
                            wrote = False
                        print(f"  → {_call(call)}", file=out, flush=True)
                    case ToolFinished():
                        mark = "✗" if event.result.is_error else "✓"
                        print(f"  {mark} {event.summary}", file=out, flush=True)
                        if event.internal_error:
                            print(
                                f'warning: tool "{event.call.name}" failed: '
                                f"{event.internal_error}",
                                file=err,
                                flush=True,
                            )
                        # The model is called again.
                        spinner.start()
                    case TurnFinished():
                        await spinner.stop()
                        if wrote:
                            print(file=out)
                            wrote = False
                        _show_turn(event, out)
    except ModelError as exc:
        await spinner.stop()
        # The text already shown stays; the error starts on a new line.
        if wrote:
            print(file=out)
        print(f"error: {exc}", file=err, flush=True)
    except asyncio.CancelledError:
        if not sigint.pending:
            raise
        sigint.pending = False
        # Without this, asyncio would keep treating the task as cancelled.
        task = asyncio.current_task()
        assert task is not None
        task.uncancel()
        await spinner.stop()
        if wrote:
            print(file=out)
        print("  [interrupted]", file=out, flush=True)
    finally:
        await spinner.stop()


def _call(call: ToolCallBlock) -> str:
    """`name(arg="value", …)` in one line, at most 100 characters."""
    try:
        arguments = json.loads(call.arguments or "{}")
    except ValueError, RecursionError:
        arguments = None
    if isinstance(arguments, dict):
        shown = ", ".join(
            f"{key}={json.dumps(value, ensure_ascii=False)}"
            for key, value in arguments.items()
        )
    else:
        # As the model wrote it: the loop answers it with an error.
        shown = call.arguments
    text = " ".join(f"{call.name}({shown})".split())
    return text if len(text) <= MAX_CALL else text[: MAX_CALL - 1] + "…"


def _show_turn(turn: TurnFinished, out: TextIO) -> None:
    if turn.reason == "max_steps":
        print(f"  [step limit reached: {turn.steps}]", file=out)
    usage = turn.usage
    # All zeros means the provider did not report them: nothing to show.
    if usage == Usage():
        out.flush()
        return
    calls = ""
    if turn.tool_calls:
        calls = f" · {turn.tool_calls} call" + ("s" if turn.tool_calls > 1 else "")
    print(
        f"  [tokens: {usage.input_tokens} in · {usage.output_tokens} out{calls}]",
        file=out,
        flush=True,
    )
