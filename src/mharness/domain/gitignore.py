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
    # Trailing spaces go, unless escaped with "\".
    while line.endswith(" ") and not line.endswith("\\ "):
        line = line[:-1]
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
    regex = body if anchored else _ANY_FOLDERS + body
    return _Rule(re.compile(regex, re.DOTALL), negated, dir_only)


def _translate(pattern: str) -> str:
    """The regular expression of a pattern: "*", "?", "[...]", "**" and "\\"."""
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
        elif char == "[" and (end := _class_end(pattern, i)) != -1:
            out.append(_class(pattern[i + 1 : end]))
            i = end
        elif char == "\\" and i + 1 < len(pattern):
            i += 1
            out.append(re.escape(pattern[i]))
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


def _class_end(pattern: str, start: int) -> int:
    """Where the "]" of the class at `start` is, or -1: a "]" right after the
    "[" (or "[!") is part of the class."""
    i = start + 1
    if pattern[i : i + 1] in ("!", "^"):
        i += 1
    if pattern[i : i + 1] == "]":
        i += 1
    return pattern.find("]", i)


def _class(inside: str) -> str:
    negated = inside[:1] in ("!", "^")
    if negated:
        inside = inside[1:]
    inside = inside.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    # A class never matches the "/" between folders.
    return f"[^/{inside}]" if negated else f"(?!/)[{inside}]"
