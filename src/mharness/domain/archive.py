"""The archive of a session: what left the working window, whole (spec hito
11, §1.5).

An index, not the source: the session's file is. What goes in: each
message that is archived, and each tool output too big for the context
(§1.6). What comes out: hits of a search, and an item read by lines.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from mharness.domain.messages import Role

# A whole output, an archived message, or what the archivist wrote of
# some archived steps.
type ItemKind = Literal["output", "message", "summary"]

# How the ids of each kind start: `out-17`, `msg-3`, `sum-40`.
ID_PREFIX: dict[ItemKind, str] = {"output": "out", "message": "msg", "summary": "sum"}
_KIND: dict[str, ItemKind] = {prefix: kind for kind, prefix in ID_PREFIX.items()}
ITEM_ID = re.compile(r"(out|msg|sum)-([1-9][0-9]{0,17})")

# What a search gives at most (§1.9).
SEARCH_HITS = 5
SEARCH_CHARS = 8_000

NOTHING_ARCHIVED = "nothing archived yet"


class ArchiveError(Exception):
    """The archive cannot be read or written: the disk failed, or the file
    is broken."""


class ItemNotFound(ArchiveError):
    """No item has that id."""


class ArchiveItem(BaseModel, frozen=True):
    """Something to archive."""

    kind: ItemKind
    # Where it was in the conversation: the index of its message.
    position: int = Field(ge=0)
    role: Role
    # The tool that gave it, for an output or a tool message.
    tool: str | None = None
    text: str
    # Its number, when it has one already: a message's comes from its
    # position, and a summary's from where its steps end, so that archiving
    # them again adds nothing; an output's, when the archive is made again
    # from the session. None: the next one of its kind.
    number: int | None = Field(default=None, ge=1)


class Hit(BaseModel, frozen=True):
    """One item found by a search, with the text around what matched."""

    id: str
    kind: ItemKind
    position: int
    role: Role
    tool: str | None
    snippet: str


class ItemLines(BaseModel, frozen=True):
    """Some lines of an archived item."""

    id: str
    # The first line given, from 1, and how many the item has.
    offset: int
    lines: list[str]
    total: int


def item_id(kind: ItemKind, number: int) -> str:
    return f"{ID_PREFIX[kind]}-{number}"


def message_item(
    position: int, role: Role, text: str, tool: str | None = None
) -> ArchiveItem:
    """An archived message, numbered by its position: `msg-1` is the
    first message of the conversation."""
    return ArchiveItem(
        kind="message",
        position=position,
        role=role,
        tool=tool,
        text=text,
        number=position + 1,
    )


def parse_id(text: str) -> tuple[ItemKind, int] | None:
    """The kind and number of an id; None if it is not one."""
    match = ITEM_ID.fullmatch(text)
    if match is None:
        return None
    return _KIND[match.group(1)], int(match.group(2))


def search_terms(query: str) -> list[str]:
    """The words of a query, as a full-text search takes them: letters,
    digits and `_`, without operators the model did not mean."""
    return re.findall(r"\w+", query)


class ArchiveNotes(BaseModel, frozen=True):
    """What the archivist writes of the steps that leave the window (§1.7):
    a summary of them alone, searchable in the archive, and the new index
    of everything archived, shown to the model."""

    summary: str = Field(min_length=1)
    index: str = Field(min_length=1)
