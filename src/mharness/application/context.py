"""The archivist: a cheap model that summarizes what leaves the working
window and keeps its index (spec hito 11, §1.7).

```json
{"summary": "msg-1 to msg-14: fixed the rounding…", "index": "…"}
```

It reads the previous index and the steps that leave, delimited as data:
what a file or a web said there is never followed (DESIGN §10). Its index
is recursive, as MemGPT's: the new one takes in the previous one, and what
was archived is never read again. If its window is smaller than what it
has to read, it reads it in parts. If it fails, the archive goes on with
the index the code writes alone: nothing is lost, it is all in the archive.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import ValidationError

from mharness.application.pricing import call_cost
from mharness.domain.archive import ArchiveNotes, item_id
from mharness.domain.context import ContextPolicy, estimate, fit
from mharness.domain.errors import ModelError
from mharness.domain.messages import (
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from mharness.domain.model import ModelRequest, Usage
from mharness.domain.prompt import render
from mharness.ports.catalog import ModelCatalog
from mharness.ports.model import ModelClient

# What the archivist may write in one call (§1.7).
ARCHIVIST_TOKENS = 4_000
# Characters of each block it reads: the whole of it is in the archive.
BLOCK_CHARS = 2_000
# The least it reads in one call, even with a tiny window.
MIN_PART_CHARS = 8_000
# Tries of each call: an answer that is not the JSON, or a failure.
TRIES = 2

_CONVERSATION = "conversation"


@dataclass(frozen=True)
class ArchivistCall:
    """One call of the archivist, paid as any (§1.7)."""

    model: str
    usage: Usage
    # None if neither the provider nor the catalog gives a price.
    cost: Decimal | None


@dataclass(frozen=True)
class Archived:
    """What the archivist gave: its notes, None if it failed, and its
    calls."""

    notes: ArchiveNotes | None
    calls: list[ArchivistCall] = field(default_factory=list)


class Archivist:
    """Asks the archivist model for the summary and the index."""

    def __init__(
        self,
        client: ModelClient,
        *,
        model: str,
        template: str,
        catalog: ModelCatalog,
        provider: str,
        failed: Callable[[str], None] = lambda kind: None,
    ) -> None:
        self.model = model
        self._client = client
        self._template = template
        self._catalog = catalog
        self._provider = provider
        # Told the kind of each failure, for maha.log: never its message,
        # which may hold what the person wrote.
        self._failed = failed

    async def archive(
        self,
        messages: Sequence[Message],
        *,
        first: int,
        previous: str | None,
        instructions: str | None = None,
    ) -> Archived:
        """The notes of `messages`, which were at `first` and after in the
        conversation, on top of the `previous` index. With the person's
        `instructions` (`/compact`)."""
        calls: list[ArchivistCall] = []
        summaries: list[str] = []
        index = previous
        for part in self._parts(conversation_text(messages, first=first)):
            notes = await self._ask(part, index, instructions, calls)
            if notes is None:
                return Archived(None, calls)
            summaries.append(notes.summary)
            index = notes.index
        assert index is not None
        return Archived(
            ArchiveNotes(summary="\n\n".join(summaries), index=index), calls
        )

    async def _ask(
        self,
        part: str,
        previous: str | None,
        instructions: str | None,
        calls: list[ArchivistCall],
    ) -> ArchiveNotes | None:
        text = render(
            self._template,
            {
                "instructions": _instructions(instructions),
                "previous": _unclosed(previous or "(none yet)", "previous-index"),
                _CONVERSATION: part,
            },
        )
        request = ModelRequest(
            model=self.model,
            messages=[Message(role="user", blocks=[TextBlock(text=text)])],
            max_tokens=ARCHIVIST_TOKENS,
        )
        for _ in range(TRIES):
            try:
                response = await self._client.complete(request)
            except ModelError as exc:
                self._failed(type(exc).__name__)
                continue
            calls.append(
                ArchivistCall(
                    model=self.model,
                    usage=response.usage,
                    cost=call_cost(response, self.model, self._catalog, self._provider),
                )
            )
            notes = parse_notes(response.message.text)
            if notes is not None:
                return notes
            self._failed("InvalidNotes")
        return None

    def _parts(self, text: str) -> list[str]:
        """`text` in parts the archivist's window takes, cut between
        steps."""
        room = self._part_chars()
        if len(text) <= room:
            return [text]
        parts: list[str] = []
        current: list[str] = []
        size = 0
        for step in text.split("\n\n"):
            if current and size + len(step) + 2 > room:
                parts.append("\n\n".join(current))
                current, size = [], 0
            current.append(fit(step, room))
            size += len(current[-1]) + 2
        if current:
            parts.append("\n\n".join(current))
        return parts

    def _part_chars(self) -> int:
        """The characters of conversation that fit in one call."""
        info = self._catalog.get(self._provider, self.model)
        policy = ContextPolicy(window=info.context if info is not None else None)
        fixed = estimate(self._template) + ARCHIVIST_TOKENS + 2_000
        return max((policy.ceiling - fixed) * 4, MIN_PART_CHARS)


def conversation_text(messages: Sequence[Message], *, first: int) -> str:
    """The steps as the archivist reads them: each message with its id, and
    each block cut to `BLOCK_CHARS`; the whole is in the archive."""
    names: dict[str, str] = {}
    lines: list[str] = []
    for position, message in enumerate(messages, start=first):
        said: list[str] = []
        for block in message.blocks:
            match block:
                case TextBlock(text=text) if text.strip():
                    said.append(fit(text.strip(), BLOCK_CHARS))
                case ToolCallBlock(id=call, name=name, arguments=arguments):
                    names[call] = name
                    said.append(f"→ {name} {fit(arguments, BLOCK_CHARS)}")
                case ToolResultBlock(call_id=call, content=content, is_error=failed):
                    mark = "✗" if failed else "←"
                    tool = names.get(call, "tool")
                    said.append(f"{mark} {tool}: {fit(content, BLOCK_CHARS)}")
        if message.interrupted:
            said.append("[interrupted by the user]")
        if said:
            head = f"[{item_id('message', position + 1)} {message.role}]"
            lines.append(head + "\n" + "\n".join(said))
    return _unclosed("\n\n".join(lines), _CONVERSATION)


def parse_notes(text: str) -> ArchiveNotes | None:
    """The archivist's JSON, also inside a code fence or with words around
    it; None if there is none."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return ArchiveNotes.model_validate(json.loads(text[start : end + 1]))
    except ValueError, ValidationError, RecursionError:
        return None


def _instructions(instructions: str | None) -> str:
    if instructions is None or not instructions.strip():
        return ""
    said = _unclosed(instructions.strip(), "instructions")
    return (
        "\nThe person asked for this archive now, and said what to keep in "
        f"mind; follow it in what you write:\n<instructions>\n{said}\n"
        "</instructions>\n"
    )


def _unclosed(text: str, tag: str) -> str:
    """Text that cannot close its own delimiter early."""
    return text.replace(f"</{tag}>", f"<\\/{tag}>")
