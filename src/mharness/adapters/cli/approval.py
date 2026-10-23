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

from mharness.adapters.cli.input import ReadLine
from mharness.adapters.cli.text import clean
from mharness.domain.approval import ApprovalRequest, Decision

DETAIL_MAX_LINES = 60
DETAIL_MAX_LINE = 200
WITH_ALWAYS = "[y] yes · [a] always this session · [n] no"
WITHOUT_ALWAYS = "[y] yes · [n] no"
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
        self, read_line: ReadLine, out: TextIO, *, color: bool = False
    ) -> None:
        self._read = read_line
        self._out = out
        self._color = color

    async def decide(self, request: ApprovalRequest) -> Decision:
        out = self._out
        print(f"  ┌ {clean(request.title)}", file=out)
        for line in _detail(request.detail):
            print(f"  │ {line}", file=out)
        if request.warning:
            warning = f"! {clean(request.warning)}"
            if self._color:
                warning = f"{YELLOW}{warning}{RESET}"
            print(f"  │ {warning}", file=out)
        always = request.scope is not None
        choices = WITH_ALWAYS if always else WITHOUT_ALWAYS
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
            if answer in _ANSWERS:
                return _ANSWERS[answer]


def _detail(detail: str) -> list[str]:
    """The lines of the detail, clean and cut."""
    lines = [clean(line) for line in detail.splitlines()]
    shown = [
        line if len(line) <= DETAIL_MAX_LINE else line[:DETAIL_MAX_LINE] + "…"
        for line in lines[:DETAIL_MAX_LINES]
    ]
    if len(lines) > DETAIL_MAX_LINES:
        shown.append(f"… [{len(lines) - DETAIL_MAX_LINES} more lines]")
    return shown


class DenyAll:
    """Denies without asking: the input is not a terminal (`maha <
    notes.txt`), and its next line could "approve" a command."""

    def __init__(self, out: TextIO) -> None:
        self._out = out

    async def decide(self, request: ApprovalRequest) -> Decision:
        print("  (denied: input is not a terminal)", file=self._out, flush=True)
        return "deny"
