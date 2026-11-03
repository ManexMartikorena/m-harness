"""Wildcard patterns matched in linear time (deep audit after hito 9, H1).

A regular expression with backtracking takes exponential time on a pattern
like `*a*a*a*a*a*a*a*a*b` and a long name, and freezes maha: a cloned
repository can bring such a `.gitignore` rule, and the model can write such
a glob. Here every possible position is followed at once (an NFA
simulation): the time grows with the length of the path, and the states
move as bits of an integer, so a long pattern costs little more (review of
the deep audit).
"""

from dataclasses import dataclass
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import PurePath
from re import Pattern
from types import UnionType


@dataclass(frozen=True)
class Literal:
    """One character, as it is."""

    char: str


@dataclass(frozen=True)
class OneChar:
    """`?`: any character but "/"."""


@dataclass(frozen=True)
class Star:
    """`*`: any characters but "/", also none."""


@dataclass(frozen=True)
class CharClass:
    """`[...]`: one character of the class; never "/"."""

    regex: Pattern[str]


@dataclass(frozen=True)
class AnyChars:
    """A trailing `**`: anything, "/" included, also nothing."""


@dataclass(frozen=True)
class AnyFolders:
    """`**/`: nothing, or any folders followed by "/"."""


type Token = Literal | OneChar | Star | CharClass | AnyChars | AnyFolders

# The characters whose masks a program keeps; others are worked out each
# time, so that a name of many different characters cannot grow it.
_MAX_CACHED = 256


class _Program:
    """The tokens as bit masks: bit i is "token i is next to match"
    (Shift-And, as agrep). One character moves every state at once, with
    a few operations on integers, whatever the length of the pattern."""

    def __init__(self, tokens: tuple[Token, ...]) -> None:
        self.accept = 1 << len(tokens)
        self.folders = _mask(tokens, AnyFolders)
        # What may match nothing: a star, `**` and `**/`.
        self.empty = _mask(tokens, Star | AnyChars | AnyFolders)
        self._stars = _mask(tokens, Star)
        self._any = _mask(tokens, AnyChars)
        self._one = _mask(tokens, OneChar)
        # Positions, not masks: a mask per character or per class would
        # take memory with the square of the length.
        self._literals: dict[str, list[int]] = {}
        self._classes: list[tuple[int, Pattern[str]]] = []
        for index, token in enumerate(tokens):
            if isinstance(token, Literal):
                self._literals.setdefault(token.char, []).append(index)
            elif isinstance(token, CharClass):
                self._classes.append((index, token.regex))
        self._masks: dict[str, tuple[int, int]] = {}

    def masks(self, char: str) -> tuple[int, int]:
        """The tokens `char` matches and moves past, and those it matches
        and stays on."""
        found = self._masks.get(char)
        if found is not None:
            return found
        positions = list(self._literals.get(char, ()))
        stay = self._any
        advance = 0
        if char != "/":
            positions += [i for i, regex in self._classes if regex.fullmatch(char)]
            advance = self._one
            stay |= self._stars
        advance |= _from_positions(positions)
        if len(self._masks) < _MAX_CACHED:
            self._masks[char] = (advance, stay)
        return advance, stay

    def closure(self, states: int) -> int:
        """With what matches nothing. Adding `empty` carries a state through
        a whole run of tokens that may be empty in one operation."""
        return states | ((states & self.empty) + self.empty) ^ self.empty


def _mask(tokens: tuple[Token, ...], kind: type | UnionType) -> int:
    return _from_positions(
        [i for i, token in enumerate(tokens) if isinstance(token, kind)]
    )


def _from_positions(positions: list[int]) -> int:
    """The integer with those bits set. From bytes: adding the bits one by
    one would take time with the square of the length."""
    if not positions:
        return 0
    data = bytearray(max(positions) // 8 + 1)
    for i in positions:
        data[i // 8] |= 1 << i % 8
    return int.from_bytes(data, "little")


# Bounded: a repository may bring many rules.
@lru_cache(maxsize=4096)
def _program(tokens: tuple[Token, ...]) -> _Program:
    return _Program(tokens)


def matches(tokens: tuple[Token, ...], text: str) -> bool:
    """Whether `text`, whole, matches `tokens`."""
    program = _program(tokens)
    # Outside: the token next to match. Inside: an AnyFolders within its
    # folders, until a "/" may end them; nothing it holds may be empty.
    outside = program.closure(1)
    inside = 0
    for char in text:
        advance, stay = program.masks(char)
        states = outside | inside
        outside = ((states & advance) << 1) | (states & stay)
        if char == "/":
            outside |= (states & program.folders) << 1
        inside = states & program.folders
        outside = program.closure(outside)
        if not (outside | inside):
            return False
    return bool(outside & program.accept)


def glob_matches(pattern: str, path: PurePath) -> bool:
    """`PurePath.full_match` without its regular expression: segment by
    segment with `fnmatchcase`, which does not backtrack, and a `**`
    segment for any folders, also none."""
    parts = pattern.split("/")
    names = path.parts
    # reachable[j]: the first j names are matched by the parts so far.
    reachable = [True] + [False] * len(names)
    for part in parts:
        if part == "**":
            for j in range(1, len(names) + 1):
                reachable[j] = reachable[j] or reachable[j - 1]
            continue
        reachable = [False] + [
            reachable[j - 1] and fnmatchcase(names[j - 1], part)
            for j in range(1, len(names) + 1)
        ]
    return reachable[len(names)]
