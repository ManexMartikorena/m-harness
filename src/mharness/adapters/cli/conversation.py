"""The conversation in the terminal: read, send, show (spec hito 2, §1.11).

The answer is shown as it arrives (spec hito 3, §1.10).
"""

import asyncio
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from importlib.metadata import version
from typing import TextIO

from mharness.application.chat import Chat
from mharness.domain.errors import ModelError
from mharness.domain.events import MessageEnd, TextDelta
from mharness.domain.model import Usage

DISTRIBUTION = "m-harness"
# Terminal convention for a program stopped by Ctrl+C: 128 + SIGINT.
EXIT_INTERRUPTED = 130

type ReadLine = Callable[[], Awaitable[str]]


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
    chat: Chat,
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
    interrupted = False

    def on_sigint() -> None:
        nonlocal interrupted
        interrupted = True
        task.cancel()

    loop.add_signal_handler(signal.SIGINT, on_sigint)
    try:
        return await _turns(chat, provider, model, read, out, err)
    except asyncio.CancelledError:
        if not interrupted:
            raise
        task.uncancel()
        print(file=out)
        return EXIT_INTERRUPTED
    finally:
        loop.remove_signal_handler(signal.SIGINT)


async def _turns(
    chat: Chat, provider: str, model: str, read: ReadLine, out: TextIO, err: TextIO
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
        await _answer(chat, line, out, err)


async def _answer(chat: Chat, line: str, out: TextIO, err: TextIO) -> None:
    """Show one answer as it arrives; a model error ends only this turn."""
    wrote = False
    try:
        async with aclosing(chat.stream(line)) as events:
            async for event in events:
                match event:
                    case TextDelta(text=text):
                        out.write(text)
                        out.flush()
                        wrote = True
                    case MessageEnd(usage=usage):
                        print(file=out)
                        _show_tokens(usage, out)
    except ModelError as exc:
        # The text already shown stays; the error starts on a new line.
        if wrote:
            print(file=out)
        print(f"error: {exc}", file=err, flush=True)


def _show_tokens(usage: Usage, out: TextIO) -> None:
    # All zeros means the provider did not report them: nothing to show.
    if usage == Usage():
        return
    print(
        f"  [tokens: {usage.input_tokens} in · {usage.output_tokens} out]",
        file=out,
        flush=True,
    )
