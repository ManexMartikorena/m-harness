"""The model's questions in the terminal (spec hito 10, §1.11).

```
  ┌ Database · Which database does the project use?
  │ 1. SQLite — A local file
  │ 2. PostgreSQL — A server
  │ 3. Other — write your own answer
  └ Choose 1-3:
```

An answer is the option's number or its label; with `multi_select`,
several, separated by commas. "Other" asks for the person's own text.
Everything shown comes from the model: cleaned before it is printed.
"""

from collections.abc import Sequence
from typing import TextIO

from mharness.adapters.cli.input import Discard, ReadLine
from mharness.adapters.cli.text import clean_line
from mharness.domain.question import OTHER, Answer, Question

OTHER_DESCRIPTION = "write your own answer"


class TerminalQuestions:
    """Asks with the same reader as the conversation, as an approval does."""

    def __init__(
        self, read_line: ReadLine, out: TextIO, *, discard: Discard | None = None
    ) -> None:
        self._read = read_line
        self._out = out
        self._discard = discard

    async def ask(self, questions: Sequence[Question]) -> list[Answer] | None:
        # Only what is typed while seeing the question answers it.
        if self._discard is not None and self._discard():
            print("  (discarded typed input)", file=self._out)
        answers = []
        for number, question in enumerate(questions, 1):
            count = f" ({number}/{len(questions)})" if len(questions) > 1 else ""
            choices = await self._one(question, count)
            if choices is None:
                return None
            answers.append(Answer(header=question.header, choices=choices))
        return answers

    async def _one(self, question: Question, count: str) -> tuple[str, ...] | None:
        out = self._out
        header = clean_line(question.header)
        print(f"  ┌ {header}{count} · {clean_line(question.question)}", file=out)
        labels = [option.label for option in question.options]
        for number, option in enumerate(question.options, 1):
            shown = f"{clean_line(option.label)} — {clean_line(option.description)}"
            print(f"  │ {number}. {shown}", file=out)
        other = len(labels) + 1
        print(f"  │ {other}. {OTHER} — {OTHER_DESCRIPTION}", file=out)
        prompt = (
            f"Choose one or more, separated by commas (1-{other})"
            if question.multi_select
            else f"Choose 1-{other}"
        )
        while True:
            print(f"  └ {prompt}: ", end="", file=out, flush=True)
            line = await self._line()
            if line is None:
                return None
            chosen = _choices(line, labels, multi=question.multi_select)
            if chosen is None:
                continue
            if OTHER not in chosen:
                return tuple(chosen)
            own = await self._own()
            if own is None:
                return None
            return tuple(own if choice == OTHER else choice for choice in chosen)

    async def _own(self) -> str | None:
        """The person's own answer; never empty."""
        while True:
            print("  └ Your answer: ", end="", file=self._out, flush=True)
            line = await self._line()
            if line is None or line:
                return line

    async def _line(self) -> str | None:
        try:
            return (await self._read()).strip()
        except EOFError:
            # Ctrl+D: no answer.
            print(file=self._out, flush=True)
            return None


def _choices(line: str, labels: list[str], *, multi: bool) -> list[str] | None:
    """The labels a line names, in its order and once each; None if it
    names nothing valid, or more than one without `multi`."""
    parts = [part.strip() for part in line.split(",")] if multi else [line]
    by_name = {label.strip().casefold(): label for label in labels}
    by_name[OTHER.casefold()] = OTHER
    chosen: list[str] = []
    for part in parts:
        if not part:
            return None
        # The label first: with options "2" and "4", "2" is the first one
        # (audit after hito 10, I6). Numbers only in ASCII: "²" is a digit
        # for isdigit(), and not for int() (I5).
        if part.casefold() in by_name:
            label = by_name[part.casefold()]
        elif part.isascii() and part.isdecimal() and 1 <= int(part) <= len(labels) + 1:
            label = labels[int(part) - 1] if int(part) <= len(labels) else OTHER
        else:
            return None
        if label not in chosen:
            chosen.append(label)
    return chosen or None
