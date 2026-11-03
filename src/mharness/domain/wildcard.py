"""Wildcard patterns matched in linear time (deep audit after hito 9, H1).

A regular expression with backtracking takes exponential time on a pattern
like `*a*a*a*a*a*a*a*a*b` and a long name, and freezes maha: a cloned
repository can bring such a `.gitignore` rule, and the model can write such
a glob. Here every possible position is followed at once (an NFA
simulation): the time grows with the length of the path times that of the
pattern, never more.
"""

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePath
from re import Pattern


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

# A state is the token next to match, and whether an AnyFolders that begun
# is inside its folders (1) or not (0).
type _State = tuple[int, int]


def matches(tokens: tuple[Token, ...], text: str) -> bool:
    """Whether `text`, whole, matches `tokens`."""
    states = _closure(tokens, {(0, 0)})
    for char in text:
        states = _closure(tokens, _step(tokens, states, char))
        if not states:
            return False
    return (len(tokens), 0) in states


def _step(tokens: tuple[Token, ...], states: set[_State], char: str) -> set[_State]:
    after: set[_State] = set()
    for index, _inside in states:
        if index == len(tokens):
            continue
        match tokens[index]:
            case Literal(char=expected):
                if char == expected:
                    after.add((index + 1, 0))
            case OneChar():
                if char != "/":
                    after.add((index + 1, 0))
            case CharClass(regex=regex):
                if char != "/" and regex.fullmatch(char):
                    after.add((index + 1, 0))
            case Star():
                if char != "/":
                    after.add((index, 0))
            case AnyChars():
                after.add((index, 0))
            case AnyFolders():
                # Inside its folders until a "/" may end them.
                after.add((index, 1))
                if char == "/":
                    after.add((index + 1, 0))
    return after


def _closure(tokens: tuple[Token, ...], states: set[_State]) -> set[_State]:
    """With what matches nothing: a star, `**` and `**/` may be empty."""
    found = set(states)
    pending = list(states)
    while pending:
        index, inside = pending.pop()
        empty = index < len(tokens) and inside == 0
        if empty and isinstance(tokens[index], Star | AnyChars | AnyFolders):
            state = (index + 1, 0)
            if state not in found:
                found.add(state)
                pending.append(state)
    return found


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
