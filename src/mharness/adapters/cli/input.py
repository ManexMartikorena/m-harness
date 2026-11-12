"""What the person types: one reader for the conversation and for the
questions, so no line goes to the wrong one (spec
mejora-2026-10-23-deuda-hito-5, B3)."""

import asyncio
import contextlib
import os
import select
import signal
import termios
import time
from collections.abc import Awaitable, Callable, Iterator
from typing import TextIO

type ReadLine = Callable[[], Awaitable[str]]
# Everything until the end of the input, at most so many bytes.
type ReadAll = Callable[[int], Awaitable[str]]


# What a terminal puts around pasted text once asked to (bracketed paste).
PASTE_START = "\x1b[200~"
PASTE_END = "\x1b[201~"
# Asks for it, and stops asking.
PASTE_ON = "\x1b[?2004h"
PASTE_OFF = "\x1b[?2004l"

# What read_all() asks for at a time: a pipe holds 64 KiB on Linux.
_BIG_READ = 64 * 1024


class InputTooLarge(Exception):
    """The input passed the limit of `read_all()`."""


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
        # The end of input came while looking for more of a line: the next
        # read ends (review of the audit after hito 10).
        self._ended = False

    async def readline(self) -> str:
        """The next line. A paste of several lines is one (audit after hito
        10, I4, decision 2 of the maintainer): what the terminal marks as
        pasted (bracketed paste). Lines that only arrive together are not
        joined: those typed ahead during an answer would become one turn
        (R15, decision of the maintainer, 2026-11-11)."""
        line = await self._line()
        if PASTE_START in line:
            while PASTE_END not in line.rpartition(PASTE_START)[2]:
                try:
                    line += "\n" + await self._line()
                except EOFError:
                    self._ended = True
                    break
            return line.replace(PASTE_START, "").replace(PASTE_END, "")
        return line

    async def _line(self) -> str:
        if self._ended and not self._buffer:
            self._ended = False
            raise EOFError
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

    async def read_all(self, limit: int) -> str:
        """Everything until the end (`git diff | maha -p …`), as text; more
        than `limit` bytes raises `InputTooLarge`. Bytes that are not UTF-8
        are replaced, as `read_file` does."""
        chunks = [self._buffer]
        size = len(self._buffer)
        self._buffer = b""
        while size <= limit:
            chunk = await self._read(_BIG_READ)
            if not chunk:
                return b"".join(chunks).decode("utf-8", errors="replace")
            chunks.append(chunk)
            size += len(chunk)
        mb, rest = divmod(limit, 1024**2)
        raise InputTooLarge(
            f"the input is larger than {f'{mb} MB' if not rest else f'{limit} bytes'}"
        )

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

    async def _read(self, size: int = 4096) -> bytes:
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
            return os.read(self._fd, size)
        try:
            await ready
        finally:
            loop.remove_reader(self._fd)
        return os.read(self._fd, size)


# A Ctrl+Z handled this soon after going on came before stopping: the
# kernel drops the stop signals that come while stopped, on SIGCONT.
_STALE = 0.1


def _stop() -> None:
    """Stop maha as Ctrl+Z would; it goes on here after `fg`.

    By SIGTSTP with its default action, as editors do, not SIGSTOP: in a
    process group no shell can continue any more (orphaned), the kernel
    drops it, and maha goes on instead of staying stopped for ever (third
    review of the audit after hito 10)."""
    ours = signal.signal(signal.SIGTSTP, signal.SIG_DFL)
    try:
        # To this thread: stopped before it returns.
        signal.raise_signal(signal.SIGTSTP)
    finally:
        signal.signal(signal.SIGTSTP, ours)


def _foreground(fd: int) -> bool:
    """Whether maha has the terminal: after `bg`, changing it would stop
    maha again with SIGTTOU (third review of the audit after hito 10). A
    terminal that is not maha's own (no job control there) is always."""
    try:
        return os.tcgetpgrp(fd) == os.getpgrp()
    except OSError:
        return True


@contextlib.contextmanager
def bracketed_paste(fd: int, out: TextIO) -> Iterator[None]:
    """Ask the terminal to mark what is pasted, while the conversation lasts
    (audit after hito 10, I4). Its marks are not echoed as `^[[200~`: the
    terminal ignores them, as it ignores every escape it does not know.
    Only with a terminal on both sides; everything is left as it was.

    Ctrl+Z gives the terminal back as it was before stopping, and `fg`
    asks again, as editors do: the shell turns the marks off in between
    (second review of the audit after hito 10)."""
    if not (os.isatty(fd) and out.isatty()):
        yield
        return
    try:
        before = termios.tcgetattr(fd)
    except termios.error:
        yield
        return
    quiet = list(before)
    quiet[3] = before[3] & ~termios.ECHOCTL

    def ask() -> None:
        if not _foreground(fd):
            return
        with contextlib.suppress(termios.error):
            termios.tcsetattr(fd, termios.TCSANOW, quiet)
        with contextlib.suppress(OSError, ValueError):
            out.write(PASTE_ON)
            out.flush()

    def give_back() -> None:
        if not _foreground(fd):
            return
        with contextlib.suppress(OSError, ValueError):
            out.write(PASTE_OFF)
            out.flush()
        with contextlib.suppress(termios.error):
            termios.tcsetattr(fd, termios.TCSANOW, before)

    back = -_STALE

    def suspend() -> None:
        nonlocal back
        if time.monotonic() - back < _STALE:
            # Two Ctrl+Z close together stopped maha twice (third review
            # of the audit after hito 10).
            return
        give_back()
        _stop()
        back = time.monotonic()
        ask()

    try:
        loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    ask()
    if loop is not None:
        loop.add_signal_handler(signal.SIGTSTP, suspend)
        loop.add_signal_handler(signal.SIGCONT, ask)
    try:
        yield
    finally:
        if loop is not None:
            loop.remove_signal_handler(signal.SIGTSTP)
            loop.remove_signal_handler(signal.SIGCONT)
        give_back()
