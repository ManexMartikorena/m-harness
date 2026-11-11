import asyncio
import io
import re

import pytest

from mharness.adapters.cli.spinner import (
    CLEAR_LINE,
    COLORS,
    FRAMES,
    RESET,
    Spinner,
    frame,
    use_color,
)


class FakeTerminal(io.StringIO):
    """A StringIO that says it is a terminal."""

    def isatty(self) -> bool:
        return True


def color_of(letter_index: int, n: int) -> str:
    return f"\x1b[{COLORS[(letter_index + n) % len(COLORS)]}m"


@pytest.mark.parametrize("n", [0, 3, 10, 27])
def test_frame_without_color(n: int) -> None:
    assert frame(n, color=False) == f"{FRAMES[n % 10]} maha"


def test_frame_with_color_gives_each_letter_its_color() -> None:
    expected = "".join(color_of(i, 4) + letter for i, letter in enumerate("maha"))

    assert frame(4, color=True) == f"{FRAMES[4]} {expected}{RESET}"


def letter_colors(text: str) -> list[str]:
    return re.findall(r"\x1b\[(3[1-6])m", text)


def test_colors_move_one_place_per_frame() -> None:
    first = letter_colors(frame(0, color=True))
    second = letter_colors(frame(1, color=True))

    assert len(set(first)) == 4  # each letter in its own color
    # In the next frame, each letter takes the color of the one after it.
    assert second[:3] == first[1:]


@pytest.mark.parametrize(
    ("environ", "expected"),
    [({}, True), ({"NO_COLOR": ""}, True), ({"NO_COLOR": "1"}, False)],
)
def test_no_color(environ: dict[str, str], expected: bool) -> None:
    assert use_color(environ) is expected


async def test_spins_on_a_terminal_and_erases_the_line() -> None:
    out = FakeTerminal()
    spinner = Spinner(out, color=False)

    spinner.start()
    await asyncio.sleep(0.25)
    spinner.stop()

    text = out.getvalue()
    assert f"\r{frame(0, color=False)}" in text
    assert f"\r{frame(1, color=False)}" in text
    assert text.endswith(CLEAR_LINE)


async def test_draws_nothing_when_not_a_terminal() -> None:
    out = io.StringIO()
    spinner = Spinner(out, color=True)

    spinner.start()
    await asyncio.sleep(0.15)
    spinner.stop()

    assert out.getvalue() == ""


async def test_stop_twice_and_stop_without_start() -> None:
    out = FakeTerminal()
    never_started = Spinner(out, color=False)
    never_started.stop()
    assert out.getvalue() == ""

    spinner = Spinner(out, color=False)
    spinner.start()
    spinner.stop()
    spinner.stop()
    assert out.getvalue().count(CLEAR_LINE) == 1


async def test_stop_never_waits_and_nothing_is_drawn_after_it() -> None:
    # Second review of the audit after hito 10: stop() awaited the spinner,
    # so a second Ctrl+C while an answer was being cut, in that wait, left
    # the answer and ended maha. Now there is nothing to wait for.
    out = FakeTerminal()
    spinner = Spinner(out, color=False)
    spinner.start()
    await asyncio.sleep(0.05)

    # Not a coroutine: erased before anything else runs.
    spinner.stop()
    assert out.getvalue().endswith(CLEAR_LINE)
    await asyncio.sleep(0.25)

    assert out.getvalue().endswith(CLEAR_LINE)
