"""A spinner with "maha" while the first token arrives (spec hito 3, §1.12).

Drawn with ANSI escape codes by hand, until Rich arrives in hito 19.
"""

import asyncio
import os
from collections.abc import Mapping
from typing import TextIO

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# Red, yellow, green, cyan, blue and magenta.
COLORS = (31, 33, 32, 36, 34, 35)
WORD = "maha"
INTERVAL = 0.1
RESET = "\x1b[0m"
# Back to the start of the line and erase all of it.
CLEAR_LINE = "\r\x1b[2K"


def frame(n: int, *, color: bool) -> str:
    """The n-th frame: spinner char, space and "maha".

    In colour, letter i takes colour (i + n) mod 6, so the colours move along
    the word from one frame to the next.
    """
    spinner = FRAMES[n % len(FRAMES)]
    if not color:
        return f"{spinner} {WORD}"
    letters = "".join(
        f"\x1b[{COLORS[(i + n) % len(COLORS)]}m{letter}"
        for i, letter in enumerate(WORD)
    )
    return f"{spinner} {letters}{RESET}"


def use_color(environ: Mapping[str, str] = os.environ) -> bool:
    """False if NO_COLOR is set and not empty (https://no-color.org)."""
    return not environ.get("NO_COLOR")


class Spinner:
    """Spins on its own line until stopped. Only on a real terminal."""

    def __init__(self, out: TextIO, *, color: bool) -> None:
        self._out = out
        self._color = color
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        # Redirected output (`maha < notes.txt > answer.txt`) gets no codes.
        if self._task is None and self._out.isatty():
            self._task = asyncio.create_task(self._spin())

    async def stop(self) -> None:
        """Stop and erase the line. Safe to call more than once."""
        if self._task is None:
            return
        task, self._task = self._task, None
        task.cancel()
        # Waits without raising the spinner's own CancelledError; a
        # cancellation of the caller still propagates.
        await asyncio.wait([task])
        self._out.write(CLEAR_LINE)
        self._out.flush()

    async def _spin(self) -> None:
        n = 0
        while True:
            self._out.write("\r" + frame(n, color=self._color))
            self._out.flush()
            n += 1
            await asyncio.sleep(INTERVAL)
