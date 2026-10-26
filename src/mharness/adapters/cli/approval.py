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
        # Nothing is cut: what you approve is seen whole (A3).
        _print(out, "  ┌ ", clean_line(request.title))
        lines = [clean(line) for line in request.detail.splitlines()]
        for line in lines[:DETAIL_MAX_LINES]:
            _print(out, "  │ ", line)
        rest = lines[DETAIL_MAX_LINES:]
        if rest:
            print(f"  │ … [{len(rest)} more lines: v to view them]", file=out)
        if request.warning:
            warning = f"! {clean_line(request.warning)}"
            if self._color:
                warning = f"{YELLOW}{warning}{RESET}"
            print(f"  │ {warning}", file=out)
        always = request.scope is not None
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
                for line in rest:
                    _print(out, "  │ ", line)
            if answer in _ANSWERS:
                return _ANSWERS[answer]


def _print(out: TextIO, prefix: str, line: str) -> None:
    """`line` in pieces of `DETAIL_MAX_LINE`; the next ones start with ↪."""
    pieces = [
        line[start : start + DETAIL_MAX_LINE]
        for start in range(0, len(line), DETAIL_MAX_LINE)
    ] or [""]
    print(f"{prefix}{pieces[0]}", file=out)
    for piece in pieces[1:]:
        print(f"  │ ↪ {piece}", file=out)


class DenyAll:
    """Denies without asking: the input is not a terminal (`maha <
    notes.txt`), and its next line could "approve" a command."""

    def __init__(self, out: TextIO) -> None:
        self._out = out

    async def decide(self, request: ApprovalRequest) -> Decision:
        print("  (denied: input is not a terminal)", file=self._out, flush=True)
        return "deny"
