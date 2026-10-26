"""`.gitignore` rules, as gitignore(5) describes them, without the disk
(spec mejora-2026-10-23-deuda-hito-5, E6).

Each `.gitignore` applies to its folder and below. Its patterns become
regular expressions over the path relative to that folder. The last rule
that matches decides; a deeper file is added later, so it wins. Case
matters, as in git on Linux.
"""

import re
from dataclasses import dataclass
from pathlib import PurePath

# Any number of folders, also none: "**/" at the start or "/**/" inside.
_ANY_FOLDERS = "(?:.*/)?"
# The POSIX classes of "[[:name:]]", in ASCII, as git's wildmatch.
_POSIX = {
    "alnum": "a-zA-Z0-9",
    "alpha": "a-zA-Z",
    "blank": " \t",
    "cntrl": "\x00-\x1f\x7f",
    "digit": "0-9",
    "graph": "!-~",
    "lower": "a-z",
    "print": " -~",
    "punct": re.escape("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"),
    "space": " \t\n\r\f\v",
    "upper": "A-Z",
    "xdigit": "0-9A-Fa-f",
}


@dataclass(frozen=True)
class _Rule:
    regex: re.Pattern[str]
    negated: bool
    dir_only: bool


class GitIgnore:
    """The rules of every `.gitignore` read so far."""

    def __init__(self) -> None:
        self._sets: list[tuple[PurePath, tuple[_Rule, ...]]] = []

    def add(self, base: PurePath, text: str) -> None:
        """The rules of the `.gitignore` of folder `base`; added after the
        files of the folders above it."""
        rules = tuple(rule for line in text.splitlines() if (rule := _parse(line)))
        if rules:
            self._sets.append((base, rules))

    def ignores(self, path: PurePath, *, is_dir: bool) -> bool:
        ignored = False
        for base, rules in self._sets:
            if path == base or not path.is_relative_to(base):
                continue
            relative = path.relative_to(base).as_posix()
            for rule in rules:
                if rule.dir_only and not is_dir:
                    continue
                if rule.regex.fullmatch(relative):
                    ignored = not rule.negated
        return ignored


def _parse(line: str) -> _Rule | None:
    """One line of a `.gitignore`, or None for a blank line or a comment."""
    line = _trim(line)
    if not line or line.startswith("#"):
        return None
    negated = line.startswith("!")
    if negated:
        line = line[1:]
    dir_only = line.endswith("/")
    if dir_only:
        line = line[:-1]
    if not line:
        return None
    # A "/" at the start or in the middle anchors the pattern to the folder of
    # the file; without one, it matches a name at any depth.
    anchored = "/" in line
    if line.startswith("/"):
        line = line[1:]
    body = _translate(line)
    if body is None:
        # git matches nothing with it.
        return None
    regex = body if anchored else _ANY_FOLDERS + body
    return _Rule(re.compile(regex, re.DOTALL), negated, dir_only)


def _trim(line: str) -> str:
    """Without its trailing spaces, unless escaped with "\\". A "\\\\" is
    a "\\", so a space after it is not escaped (spec
    mejora-2026-10-26-deuda-pre-hito-6, B7)."""
    kept = 0
    i = 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            kept = min(i, len(line))
            continue
        if line[i] != " ":
            kept = i + 1
        i += 1
    return line[:kept]


def _translate(pattern: str) -> str | None:
    """The regular expression of a pattern: "*", "?", "[...]", "**" and "\\".
    None if git matches nothing with it: a "[" that never closes, or a "\\"
    at the end (B7)."""
    out = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**", i) and (i == 0 or pattern[i - 1] == "/"):
            if pattern[i + 2 : i + 3] == "/":
                out.append(_ANY_FOLDERS)
                i += 3
                continue
            if i + 2 == len(pattern):
                out.append(".*")
                i += 2
                continue
        if char == "*":
            out.append("[^/]*")
            # Any other "**" is a "*".
            while pattern.startswith("*", i + 1):
                i += 1
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            found = _class(pattern, i)
            if found is None:
                return None
            regex, i = found
            out.append(regex)
        elif char == "\\":
            if i + 1 == len(pattern):
                return None
            i += 1
            out.append(re.escape(pattern[i]))
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


def _class(pattern: str, start: int) -> tuple[str, int] | None:
    """The regular expression of the class that opens at `start`, and where
    its "]" is; None if it never closes, as git's wildmatch.

    A "]" right after the "[" (or "[!") is part of it, "\\" escapes, "a-z"
    is a range and "[:digit:]" a POSIX class. A class never matches the "/"
    between folders.
    """
    i = start + 1
    negated = pattern[i : i + 1] in ("!", "^")
    if negated:
        i += 1
    items: list[str] = []
    first = True
    while i < len(pattern):
        char = pattern[i]
        if char == "]" and not first:
            inside = "".join(items)
            if negated:
                return f"[^/{inside}]", i
            return (f"(?!/)[{inside}]" if inside else "(?!)"), i
        first = False
        if char == "[" and pattern.startswith(":", i + 1):
            close = pattern.find(":]", i + 2)
            if close == -1 or pattern[i + 2 : close] not in _POSIX:
                return None
            items.append(_POSIX[pattern[i + 2 : close]])
            i = close + 2
            continue
        if char == "\\":
            i += 1
            if i == len(pattern):
                return None
            char = pattern[i]
        low = char
        i += 1
        if pattern.startswith("-", i) and pattern[i + 1 : i + 2] not in ("]", ""):
            i += 1
            if pattern[i] == "\\":
                i += 1
                if i == len(pattern):
                    return None
            high = pattern[i]
            i += 1
            # A reversed range matches nothing, as in git.
            if low <= high:
                items.append(f"{re.escape(low)}-{re.escape(high)}")
            continue
        items.append(re.escape(low))
    return None
