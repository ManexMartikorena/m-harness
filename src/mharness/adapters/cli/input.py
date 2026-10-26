"""What the person types: one reader for the conversation and for the
questions, so no line goes to the wrong one (spec
mejora-2026-10-23-deuda-hito-5, B3)."""

import asyncio
import os
import select
import termios
from collections.abc import Awaitable, Callable

type ReadLine = Callable[[], Awaitable[str]]
# Drops what was typed ahead; True if there was something.
type Discard = Callable[[], bool]


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

    def discard(self) -> bool:
        """Drop what was typed ahead: the lines kept in the buffer and what
        the terminal still holds. Before a question, so a pasted "y" cannot
        answer it (spec mejora-2026-10-26-deuda-pre-hito-6, A2). True if
        something was dropped."""
        dropped = bool(self._buffer)
        self._buffer = b""
        if os.isatty(self._fd):
            # Readable now: a whole line waits in the terminal's queue.
            ready, _, _ = select.select([self._fd], [], [], 0)
            dropped = dropped or bool(ready)
            # Also a line not finished yet, which select does not see.
            termios.tcflush(self._fd, termios.TCIFLUSH)
        return dropped

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
