"""Read-only tools over the working directory (spec hito 4, §1.6).

Every path is resolved (following symbolic links) and must stay inside the
working directory; secret files are refused. No threads: a thread blocked on
the disk would keep `maha` from exiting on Ctrl+C (spec hito 2, §12).
"""

import asyncio
import os
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePath
from typing import IO

from pydantic import BaseModel, Field

from mharness.domain.paths import SKIPPED_DIRS, is_secret
from mharness.domain.tools import Permission, ToolError

# A file with a NUL byte in its first bytes is binary.
BINARY_PROBE = 8 * 1024
READ_MAX_LINES = 2000
READ_MAX_CHARS = 100_000
# A longer line is cut: one huge line must not fill the context.
READ_MAX_LINE = 2000


class Workspace:
    """The working directory: the only place the tools can see."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, raw: str) -> Path:
        """The real path of `raw`, which must stay inside the root.

        `../`, absolute paths and links that point outside do not escape:
        the check runs on the resolved path.
        """
        path = (self.root / raw).resolve()
        if not path.is_relative_to(self.root):
            # Reading outside needs approval, which arrives in hito 5.
            raise ToolError(f"outside the working directory: {raw}")
        return path

    def relative(self, path: Path) -> PurePath:
        return PurePath(path.relative_to(self.root))

    def check_not_secret(self, path: Path, raw: str) -> None:
        if is_secret(self.relative(path)):
            raise ToolError(f"secret file, not readable: {raw}")


def is_binary(path: Path) -> bool:
    with path.open("rb") as file:
        return b"\0" in file.read(BINARY_PROBE)


class ReadFileParams(BaseModel):
    path: str = Field(description="Path relative to the working directory")
    offset: int = Field(default=1, ge=1, description="First line to read, from 1")
    limit: int | None = Field(
        default=None, ge=1, description=f"Lines to read, at most {READ_MAX_LINES}"
    )


class ReadFile:
    name = "read_file"
    description = (
        "Read a text file of the working directory. Lines come numbered. "
        'Use offset and limit for long files. Example: {"path": "src/app.py"}'
    )
    params = ReadFileParams
    permission: Permission = "read"

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    async def run(self, params: ReadFileParams) -> str:
        path = self._workspace.resolve(params.path)
        self._workspace.check_not_secret(path, params.path)
        if not path.exists():
            raise ToolError(f"file not found: {params.path}")
        if path.is_dir():
            raise ToolError(f"is a directory, use list_dir: {params.path}")
        if is_binary(path):
            raise ToolError(f"binary file, not readable: {params.path}")
        limit = min(params.limit or READ_MAX_LINES, READ_MAX_LINES)
        with path.open(encoding="utf-8", errors="replace", newline="") as file:
            return _numbered_lines(file, params.offset, limit)

    def summary(self, result: str) -> str:
        lines = sum(1 for line in result.splitlines() if _NUMBERED.match(line))
        cut = " (truncated)" if result.endswith("]") and "[truncated" in result else ""
        return f"{lines} lines{cut}"


_NUMBERED = re.compile(r"^ *\d+\t")


def _numbered_lines(file: IO[str], offset: int, limit: int) -> str:
    """Lines `offset` to `offset + limit - 1`, numbered like `cat -n`."""
    shown: list[str] = []
    chars = 0
    number = 0
    while (line := _next_line(file)) is not None:
        number += 1
        if number < offset:
            continue
        if len(shown) == limit or chars + len(line) > READ_MAX_CHARS:
            return "\n".join(
                [
                    *shown,
                    f"… [truncated at line {number - 1}; "
                    f"use offset={number} to read more]",
                ]
            )
        shown.append(f"{number:>6}\t{line}")
        chars += len(line)
    if not shown:
        if number == 0:
            return "(empty file)"
        return f"(no lines from offset {offset}: the file has {number} lines)"
    return "\n".join(shown)


def _next_line(file: IO[str]) -> str | None:
    """The next line without its line ending, cut if it is too long."""
    line = file.readline(READ_MAX_LINE + 1)
    if not line:
        return None
    if len(line) > READ_MAX_LINE and not line.endswith(("\n", "\r")):
        # Skip the rest of the long line.
        while (rest := file.readline(64 * 1024)) and not rest.endswith(("\n", "\r")):
            pass
        return line[:READ_MAX_LINE] + " … [line cut]"
    return line.rstrip("\r\n")


LIST_MAX_ENTRIES = 500


class ListDirParams(BaseModel):
    path: str = Field(
        default=".", description="Directory relative to the working directory"
    )


class ListDir:
    name = "list_dir"
    description = (
        'List a directory of the working directory. Directories end in "/". '
        'Example: {"path": "src"}'
    )
    params = ListDirParams
    permission: Permission = "read"

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    async def run(self, params: ListDirParams) -> str:
        path = self._workspace.resolve(params.path)
        if is_secret(self._workspace.relative(path)):
            raise ToolError(f"secret directory, not listable: {params.path}")
        if not path.exists():
            raise ToolError(f"directory not found: {params.path}")
        if not path.is_dir():
            raise ToolError(f"not a directory, use read_file: {params.path}")
        entries = sorted(path.iterdir(), key=lambda entry: entry.name)
        if not entries:
            return "(empty directory)"
        lines = [self._entry(entry) for entry in entries[:LIST_MAX_ENTRIES]]
        if len(entries) > LIST_MAX_ENTRIES:
            lines.append(
                f"… [truncated: {LIST_MAX_ENTRIES} of {len(entries)} entries shown]"
            )
        return "\n".join(lines)

    def _entry(self, entry: Path) -> str:
        name = f"{entry.name}/" if entry.is_dir() else entry.name
        # Shown, so the model knows it exists and does not ask for it.
        relative = PurePath(entry.relative_to(self._workspace.root))
        return f"{name} [secret]" if is_secret(relative) else name

    def summary(self, result: str) -> str:
        if result == "(empty directory)":
            return "0 entries"
        entries = sum(1 for line in result.splitlines() if not line.startswith("… ["))
        return f"{entries} entries"


# Searching walks at most this many files; it yields control every few files,
# so Ctrl+C can stop it.
WALK_MAX_FILES = 20_000
WALK_YIELD_EVERY = 100


@dataclass(frozen=True)
class _Found:
    real: Path  # resolved, inside the working directory
    relative: PurePath  # to the working directory: what the model sees
    in_base: PurePath  # to the directory searched: what patterns match


class _Walk:
    """The files under a directory. Skips SKIPPED_DIRS, secrets, and links
    that point outside."""

    def __init__(self, workspace: Workspace, base: Path) -> None:
        self._workspace = workspace
        self._base = base
        self.stopped_early = False

    async def files(self) -> AsyncIterator[_Found]:
        seen = 0
        root = self._workspace.root
        for dirpath, dirnames, filenames in os.walk(self._base):
            directory = Path(dirpath)
            # Pruned in place, so os.walk does not go into them.
            dirnames[:] = sorted(
                name
                for name in dirnames
                if name not in SKIPPED_DIRS
                and not is_secret(PurePath((directory / name).relative_to(root)))
            )
            for name in sorted(filenames):
                seen += 1
                if seen > WALK_MAX_FILES:
                    self.stopped_early = True
                    return
                if seen % WALK_YIELD_EVERY == 0:
                    await asyncio.sleep(0)
                path = directory / name
                relative = PurePath(path.relative_to(root))
                real = path.resolve()
                if not real.is_relative_to(root) or is_secret(relative):
                    continue
                if is_secret(PurePath(real.relative_to(root))):
                    continue
                yield _Found(real, relative, PurePath(path.relative_to(self._base)))


def _check_pattern(pattern: str) -> None:
    pure = PurePath(pattern)
    if pure.is_absolute() or ".." in pure.parts:
        raise ToolError("the pattern must be relative, without '..'")


GLOB_MAX_RESULTS = 200


class GlobParams(BaseModel):
    pattern: str = Field(description='Pattern like "**/*.py" or "src/*.md"')
    path: str = Field(
        default=".",
        description="Directory to search in, relative to the working directory",
    )


class Glob:
    name = "glob"
    description = (
        "Find files by name pattern, relative to the working directory. "
        '"**" matches any number of directories. Example: {"pattern": "**/*.py"}'
    )
    params = GlobParams
    permission: Permission = "read"

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    async def run(self, params: GlobParams) -> str:
        _check_pattern(params.pattern)
        base = self._workspace.resolve(params.path)
        if not base.is_dir():
            raise ToolError(f"not a directory: {params.path}")
        walk = _Walk(self._workspace, base)
        found = [
            str(file.relative)
            async for file in walk.files()
            if file.in_base.full_match(params.pattern)
        ]
        lines = found[:GLOB_MAX_RESULTS]
        if len(found) > GLOB_MAX_RESULTS:
            lines.append(
                f"… [truncated: {GLOB_MAX_RESULTS} of {len(found)} files shown]"
            )
        if walk.stopped_early:
            lines.append(f"… [stopped after {WALK_MAX_FILES} files; narrow the path]")
        return "\n".join(lines) if lines else "(no files match)"

    def summary(self, result: str) -> str:
        if result == "(no files match)":
            return "0 files"
        files = sum(1 for line in result.splitlines() if not line.startswith("… ["))
        return f"{files} files"


GREP_MAX_MATCHES = 100
GREP_MAX_LINE = 300
# Larger files are skipped: a huge log would block the loop while read.
GREP_MAX_FILE_BYTES = 2 * 1024 * 1024


class GrepParams(BaseModel):
    pattern: str = Field(description="Python regular expression")
    path: str = Field(
        default=".",
        description="File or directory to search, relative to the working directory",
    )
    glob: str | None = Field(
        default=None,
        description='Only files that match, like "*.py" (by name) or "src/**/*.py"',
    )


class Grep:
    name = "grep"
    description = (
        "Search file contents with a Python regular expression. Gives "
        '"path:line: text". Example: {"pattern": "def main", "glob": "*.py"}'
    )
    params = GrepParams
    permission: Permission = "read"

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    async def run(self, params: GrepParams) -> str:
        try:
            regex = re.compile(params.pattern)
        except re.error as exc:
            raise ToolError(f"invalid regular expression: {exc}") from None
        if params.glob:
            _check_pattern(params.glob)
        base = self._workspace.resolve(params.path)
        if not base.exists():
            raise ToolError(f"not found: {params.path}")
        if base.is_file():
            self._workspace.check_not_secret(base, params.path)
            found = _search(base, self._workspace.relative(base), regex)
            return _grep_result(found, stopped_early=False)
        walk = _Walk(self._workspace, base)
        matches: list[str] = []
        async for file in walk.files():
            if params.glob and not _glob_matches(file.in_base, params.glob):
                continue
            matches.extend(_search(file.real, file.relative, regex))
            # One more than shown: it tells whether something was left out.
            if len(matches) > GREP_MAX_MATCHES:
                break
        return _grep_result(matches, stopped_early=walk.stopped_early)

    def summary(self, result: str) -> str:
        if result == "(no matches)":
            return "0 matches"
        found = sum(1 for line in result.splitlines() if not line.startswith("… ["))
        return f"{found} matches" if found != 1 else "1 match"


def _glob_matches(in_base: PurePath, pattern: str) -> bool:
    # Without "/", by file name, as ripgrep does: "*.py" anywhere.
    if "/" not in pattern:
        return fnmatchcase(in_base.name, pattern)
    return in_base.full_match(pattern)


def _search(path: Path, relative: PurePath, regex: re.Pattern[str]) -> list[str]:
    """The matching lines of one text file, as "path:line: text"."""
    if path.stat().st_size > GREP_MAX_FILE_BYTES or is_binary(path):
        return []
    found = []
    with path.open(encoding="utf-8", errors="replace", newline="") as file:
        for number, line in enumerate(file, start=1):
            text = line.rstrip("\r\n")
            if regex.search(text):
                found.append(f"{relative}:{number}: {text[:GREP_MAX_LINE]}")
                if len(found) > GREP_MAX_MATCHES:
                    break
    return found


def _grep_result(matches: list[str], *, stopped_early: bool) -> str:
    lines = matches[:GREP_MAX_MATCHES]
    if len(matches) > GREP_MAX_MATCHES:
        lines.append(f"… [stopped at {GREP_MAX_MATCHES} matches; narrow the search]")
    if stopped_early:
        lines.append(f"… [stopped after {WALK_MAX_FILES} files; narrow the path]")
    return "\n".join(lines) if lines else "(no matches)"
