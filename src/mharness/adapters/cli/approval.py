"""The question before a tool call, in the terminal (spec hito 5, §1.10).

```
  ┌ run: uv run pytest -q
  │ in /home/ane/proyecto
  └ Allow? [y] yes · [a] always this session · [n] no:
```

Everything in the question can come from the model or from a file, so it
is cleaned of control characters before it is shown: it must not be able
to fake what you approve.
"""

from typing import TextIO

from mharness.adapters.cli.input import Discard, ReadLine
from mharness.adapters.cli.text import clean, clean_line
from mharness.domain.approval import ApprovalRequest, Decision

DETAIL_MAX_LINES = 60
# A longer line goes on in more lines, never cut.
DETAIL_MAX_LINE = 200
WITH_ALWAYS = "[y] yes · [a] always this session · [n] no"
WITHOUT_ALWAYS = "[y] yes · [n] no"
VIEW_ALL = " · [v] view all"
YELLOW = "\x1b[33m"
RESET = "\x1b[0m"

_ANSWERS: dict[str, Decision] = {
    "y": "once",
    "yes": "once",
    "s": "once",
    "sí": "once",
    "si": "once",
    "n": "deny",
    "no": "deny",
}


class TerminalApproval:
    """Asks in the terminal, with the same reader as the conversation."""

    def __init__(
        self,
        read_line: ReadLine,
        out: TextIO,
        *,
        color: bool = False,
        discard: Discard | None = None,
    ) -> None:
        self._read = read_line
        self._out = out
        self._color = color
        self._discard = discard

    async def decide(self, request: ApprovalRequest) -> Decision:
        out = self._out
        # Only what is typed while seeing the question answers it (spec
        # mejora-2026-10-26-deuda-pre-hito-6, A2).
        if self._discard is not None and self._discard():
            print("  (discarded typed input)", file=out)
        # Nothing is cut: what you approve is seen whole (A3), now or with
        # v. The rows on the screen count, not the lines: one huge line is
        # not a screenful (audit after hito 10, H10).
        _print(out, "  ┌ ", clean_line(request.title))
        rows = _rows(request.detail)
        for row in rows[:DETAIL_MAX_LINES]:
            print(row, file=out)
        rest = rows[DETAIL_MAX_LINES:]
        if rest:
            print(f"  │ … [{len(rest)} more lines: v to view them]", file=out)
        if request.warning:
            warning = f"! {clean_line(request.warning)}"
            if self._color:
                warning = f"{YELLOW}{warning}{RESET}"
            print(f"  │ {warning}", file=out)
        always = request.scope is not None
        if always and request.covers:
            # What [a] lets run from now on (audit after hito 10, H1).
            print(f"  │ [a] covers {clean_line(request.covers)}", file=out)
        choices = WITH_ALWAYS if always else WITHOUT_ALWAYS
        if rest:
            choices += VIEW_ALL
        while True:
            print(f"  └ Allow? {choices}: ", end="", file=out, flush=True)
            try:
                answer = (await self._read()).strip().casefold()
            except EOFError:
                # Ctrl+D: no answer is a no.
                print(file=out, flush=True)
                return "deny"
            if answer == "a" and always:
                return "session"
            if answer == "v" and rest:
                for row in rest:
                    print(row, file=out)
            if answer in _ANSWERS:
                return _ANSWERS[answer]


def show_covered(request: ApprovalRequest, out: TextIO) -> None:
    """A change that runs without asking, by an earlier "always": seen,
    not asked (audit after hito 10, P4). Only what is worth reviewing."""
    if not request.review:
        return
    _print(out, "  ┌ ", f"{clean_line(request.title)} (allowed this session)")
    rows = _rows(request.detail)
    for row in rows[:DETAIL_MAX_LINES]:
        print(row, file=out)
    rest = len(rows) - DETAIL_MAX_LINES
    if rest > 0:
        print(f"  │ … [{rest} more lines]", file=out)
    print("  └", file=out, flush=True)


def _print(out: TextIO, prefix: str, line: str) -> None:
    """`line` in pieces of `DETAIL_MAX_LINE`; the next ones start with ↪."""
    for row in _pieces(prefix, line):
        print(row, file=out)


def _rows(detail: str) -> list[str]:
    """The rows of `detail` on the screen, clean, in pieces."""
    return [row for line in detail.splitlines() for row in _pieces("  │ ", clean(line))]


def _pieces(prefix: str, line: str) -> list[str]:
    pieces = [
        line[start : start + DETAIL_MAX_LINE]
        for start in range(0, len(line), DETAIL_MAX_LINE)
    ] or [""]
    return [f"{prefix}{pieces[0]}", *(f"  │ ↪ {piece}" for piece in pieces[1:])]


class DenyAll:
    """Denies without asking: the input is not a terminal (`maha <
    notes.txt`), and its next line could "approve" a command."""

    def __init__(self, out: TextIO) -> None:
        self._out = out

    async def decide(self, request: ApprovalRequest) -> Decision:
        print("  (denied: input is not a terminal)", file=self._out, flush=True)
        return "deny"
