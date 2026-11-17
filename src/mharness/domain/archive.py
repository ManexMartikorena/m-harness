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

# A whole output, or an archived message.
type ItemKind = Literal["output", "message"]

# How the ids of each kind start: `out-17`, `msg-3`.
ID_PREFIX: dict[ItemKind, str] = {"output": "out", "message": "msg"}
ITEM_ID = re.compile(r"(out|msg)-([1-9][0-9]{0,17})")

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


def parse_id(text: str) -> tuple[ItemKind, int] | None:
    """The kind and number of an id; None if it is not one."""
    match = ITEM_ID.fullmatch(text)
    if match is None:
        return None
    kind: ItemKind = "output" if match.group(1) == "out" else "message"
    return kind, int(match.group(2))


def search_terms(query: str) -> list[str]:
    """The words of a query, as a full-text search takes them: letters,
    digits and `_`, without operators the model did not mean."""
    return re.findall(r"\w+", query)
