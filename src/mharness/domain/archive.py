"""The archive of a session: what left the working window, whole (spec hito
11, §1.5).

An index, not the source: the session's file is. What goes in: each
message that is archived, and each tool output too big for the context
(§1.6). What comes out: hits of a search, and an item read by lines.
"""

import bisect
import re
import unicodedata
from functools import cache
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


# The characters of a search's fragment, about 40 words (§1.9).
SNIPPET_CHARS = 300
# The places of each word a fragment looks at, at most: FTS5's own
# snippet() grows with the square of the matches, and took minutes over an
# output with the words on every line (hand verification of hito 11).
SNIPPET_MAX_PLACES = 2_000


def snippet(text: str, terms: list[str], size: int = SNIPPET_CHARS) -> str:
    """The part of `text`, about `size` characters, with the most words of
    `terms`, found as the archive's search finds them: whole words,
    without case or accents. Cut at spaces, with "…" where text was left
    out; the start, if no word is there. Its cost is bounded: each word is
    looked for in `SNIPPET_MAX_PLACES` places at most."""
    if len(text) <= size:
        return text
    places: dict[str, list[int]] = {}
    for term in dict.fromkeys(_plain(term) for term in terms if term):
        found: list[int] = []
        for match in _word(term).finditer(text):
            found.append(match.start())
            if len(found) == SNIPPET_MAX_PLACES:
                break
        if found:
            places[term] = found
    if not places:
        return _window(text, 0, size)
    half = size // 2
    rarest = min(places.values(), key=len)
    best, best_score = rarest[0], -1
    for place in rarest:
        score = sum(
            1
            for found in places.values()
            if bisect.bisect_right(found, place + half)
            > bisect.bisect_left(found, place - half)
        )
        if score > best_score:
            best, best_score = place, score
    return _window(text, max(0, min(best - half, len(text) - size)), size)


def _window(text: str, start: int, size: int) -> str:
    """`size` characters of `text` from `start`, without halves of words."""
    end = min(len(text), start + size)
    if start > 0:
        space = text.find(" ", start, end)
        newline = text.find("\n", start, end)
        cuts = [cut for cut in (space, newline) if cut >= 0]
        start = min(cuts) + 1 if cuts else start
    if end < len(text):
        cut = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
        end = cut if cut > start else end
    return (
        ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    )


def _plain(word: str) -> str:
    """`word` without accents and in lower case."""
    decomposed = unicodedata.normalize("NFKD", word)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


@cache
def _accented() -> dict[str, str]:
    """Each base letter and the Latin letters with accents built on it."""
    letters: dict[str, str] = {}
    for code in range(0xC0, 0x250):
        char = chr(code)
        base = _plain(char)
        if len(base) == 1 and base.isascii() and base.isalpha() and base != char:
            letters[base] = letters.get(base, base) + char.lower()
    return letters


@cache
def _word(term: str) -> re.Pattern[str]:
    """A whole word, `term` with or without accents, in any case."""
    letters = _accented()
    parts = (
        f"[{re.escape(letters[char])}]" if char in letters else re.escape(char)
        for char in term
    )
    return re.compile(r"(?<!\w)" + "".join(parts) + r"(?!\w)", re.IGNORECASE)


class ArchiveNotes(BaseModel, frozen=True):
    """What the archivist writes of the steps that leave the window (§1.7):
    a summary of them alone, searchable in the archive, and the new index
    of everything archived, shown to the model."""

    summary: str = Field(min_length=1)
    index: str = Field(min_length=1)
