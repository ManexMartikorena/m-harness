"""File tools over the working directory (spec hito 4, §1.6, and spec hito
5, §1.6 to §1.8).

Every path is resolved (following symbolic links). Reading outside the
working directory, or a secret file, asks the user first, one call at a time
(spec hito 5, §1.6). Writing always asks. No threads: a thread blocked on the
disk would keep `maha` from exiting on Ctrl+C (spec hito 2, §12).
"""

import asyncio
import contextlib
import difflib
import errno
import io
import os
import re
import secrets
import stat
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePath
from typing import IO

from pydantic import BaseModel, Field

from mharness.domain.approval import ApprovalRequest
from mharness.domain.paths import (
    SECRET_DIR,
    SECRET_FILE,
    SKIPPED_DIRS,
    change_warning,
    is_inside,
    is_secret_at,
    read_warning,
)
from mharness.domain.tools import Permission, ToolError

MIB = 1024 * 1024
# A file with a NUL byte in its first bytes is binary.
BINARY_PROBE = 8 * 1024
READ_MAX_LINES = 2000
READ_MAX_CHARS = 100_000
# A longer line is cut: one huge line must not fill the context.
READ_MAX_LINE = 2000


def _count(number: int, singular: str, plural: str | None = None) -> str:
    """ "1 line", "3 lines": the summaries the terminal shows."""
    word = singular if number == 1 else plural or f"{singular}s"
    return f"{number} {word}"


def _count_lines(
    result: str, empty: str, singular: str, plural: str | None = None
) -> str:
    """How many results a listing gives: its lines, without the "… [" notes,
    or none if it is the `empty` text."""
    if result == empty:
        return _count(0, singular, plural)
    found = sum(1 for line in result.splitlines() if not line.startswith("… ["))
    return _count(found, singular, plural)


class Workspace:
    """The working directory: the tools see it without asking. The rules of
    what asks live in `domain.paths`; this resolves paths on the disk."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, raw: str) -> Path:
        """The real path of `raw`, relative to the root.

        `../`, absolute paths and links that point outside do not hide where
        they go: every check runs on the resolved path.
        """
        try:
            return (self.root / raw).resolve()
        except ValueError:
            # A NUL in the path (spec mejora-2026-10-23-deuda-hito-5, A5).
            raise ToolError(f"invalid path: {raw}") from None

    def contains(self, path: Path) -> bool:
        return is_inside(path, self.root)

    def secret(self, path: Path) -> bool:
        return is_secret_at(path, self.root)

    def shown(self, path: Path) -> str:
        """What the model and the user see: relative inside, absolute
        outside."""
        if self.contains(path):
            return str(path.relative_to(self.root))
        return str(path)

    def warning(self, path: Path, secret: str | None) -> str | None:
        return read_warning(path, self.root, secret=secret)


class _Asked:
    """What the last question of a tool showed, so `run()` does only that.

    Between the question and `run()` a link or the file can change (TOCTOU:
    time of check to time of use). `run()` resolves the path again and
    compares: the same call, the same resolved path (decision D1, review of
    PR 2, fix 5) and, to change a file, the same bytes it would replace
    (decision W6). One slot is enough because calls run one at a time; with
    parallel calls (hito 15) it must keep one per call.
    """

    def __init__(self) -> None:
        self._last: tuple[BaseModel, Path] | None = None
        # The bytes the question showed; None: the file did not exist.
        self.old: bytes | None = None

    def forget(self) -> None:
        self._last = None
        self.old = None

    def remember(self, params: BaseModel, path: Path, old: bytes | None = None) -> None:
        self._last = (params, path)
        self.old = old

    def same(self, params: BaseModel, path: Path) -> bool:
        return self._last == (params, path)

    def check(
        self, params: BaseModel, raw: str, path: Path, warning: str | None
    ) -> None:
        """For reading: a call that needs a question runs only as asked."""
        if warning is not None and not self.same(params, path):
            raise _changed(raw)


def _changed(raw: str) -> ToolError:
    return ToolError(f"{raw} changed after the question; ask again")


def _request(
    tool: str, title: str, workspace: Workspace, path: Path, raw: str, warning: str
) -> ApprovalRequest:
    """A question about reading `path`: never for the whole session."""
    shown = workspace.shown(path)
    detail = str(path) if raw == shown else f"{path} (asked: {raw})"
    return ApprovalRequest(
        tool=tool, title=title, detail=detail, scope=None, warning=warning
    )


@contextlib.contextmanager
def _reading(raw: str) -> Iterator[None]:
    """A failure to read `raw` (no rights, a disk error) as a clean error,
    not an internal one (review of PR 2, fix 3)."""
    try:
        yield
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise ToolError(f"cannot read {raw}: {reason}") from None


def _open_regular(path: Path) -> IO[bytes] | None:
    """`path` open for reading, or None if it is not a regular file.

    Opened without waiting and checked on the open file, not before: a FIFO
    that replaces the file after a check would block a plain open (spec
    hito 5, §12.11).
    """
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)
    try:
        regular = stat.S_ISREG(os.fstat(descriptor).st_mode)
    except OSError:
        os.close(descriptor)
        raise
    if not regular:
        os.close(descriptor)
        return None
    return open(descriptor, "rb")


def is_binary(file: IO[bytes]) -> bool:
    """Whether the open `file` is binary; it is left at the start."""
    binary = b"\0" in file.read(BINARY_PROBE)
    file.seek(0)
    return binary


def _as_text(file: IO[bytes]) -> IO[str]:
    return io.TextIOWrapper(file, encoding="utf-8", errors="replace", newline="")


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
        self._asked = _Asked()

    async def approval(self, params: ReadFileParams) -> ApprovalRequest | None:
        self._asked.forget()
        path = self._workspace.resolve(params.path)
        warning = self._workspace.warning(path, SECRET_FILE)
        if warning is None:
            return None
        # Before asking: no useless question (spec hito 5, §1.2). Only what
        # the metadata tells: whether it is binary waits for the approval.
        _check_exists(path, params.path)
        self._asked.remember(params, path)
        shown = self._workspace.shown(path)
        return _request(
            self.name, f"read {shown}", self._workspace, path, params.path, warning
        )

    async def run(self, params: ReadFileParams) -> str:
        path = self._workspace.resolve(params.path)
        warning = self._workspace.warning(path, SECRET_FILE)
        self._asked.check(params, params.path, path, warning)
        limit = min(params.limit or READ_MAX_LINES, READ_MAX_LINES)
        with _reading(params.path):
            _check_exists(path, params.path)
            file = _open_regular(path)
            if file is None:
                raise ToolError(f"not a regular file: {params.path}")
            with _as_text(file) as text:
                if is_binary(file):
                    raise ToolError(f"binary file, not readable: {params.path}")
                return _numbered_lines(text, params.offset, limit)

    def summary(self, result: str) -> str:
        lines = sum(1 for line in result.splitlines() if _NUMBERED.match(line))
        cut = " (truncated)" if result.endswith("]") and "[truncated" in result else ""
        return _count(lines, "line") + cut


_NUMBERED = re.compile(r"^ *\d+\t")


def _check_exists(path: Path, raw: str) -> None:
    if not path.exists():
        raise ToolError(f"file not found: {raw}")
    if path.is_dir():
        raise ToolError(f"is a directory, use list_dir: {raw}")
    # Before asking; `_open_regular()` checks again on the open file.
    if not path.is_file():
        raise ToolError(f"not a regular file: {raw}")


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
        return f"(no lines from offset {offset}: the file has {_count(number, 'line')})"
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
        self._asked = _Asked()

    async def approval(self, params: ListDirParams) -> ApprovalRequest | None:
        self._asked.forget()
        path = self._workspace.resolve(params.path)
        warning = self._workspace.warning(path, SECRET_DIR)
        if warning is None:
            return None
        _check_dir(path, params.path)
        self._asked.remember(params, path)
        shown = self._workspace.shown(path)
        return _request(
            self.name, f"list {shown}", self._workspace, path, params.path, warning
        )

    async def run(self, params: ListDirParams) -> str:
        path = self._workspace.resolve(params.path)
        warning = self._workspace.warning(path, SECRET_DIR)
        self._asked.check(params, params.path, path, warning)
        _check_dir(path, params.path)
        with _reading(params.path):
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
        return f"{name} [secret]" if self._workspace.secret(entry) else name

    def summary(self, result: str) -> str:
        return _count_lines(result, "(empty directory)", "entry", "entries")


def _check_dir(path: Path, raw: str) -> None:
    if not path.exists():
        raise ToolError(f"directory not found: {raw}")
    if not path.is_dir():
        raise ToolError(f"not a directory, use read_file: {raw}")


# Searching walks at most this many files; it yields control every few files,
# so Ctrl+C can stop it.
WALK_MAX_FILES = 20_000
WALK_YIELD_EVERY = 100


@dataclass(frozen=True)
class _Found:
    real: Path  # resolved, inside the limit of the walk
    shown: str  # what the model sees: relative inside, absolute outside
    in_base: PurePath  # to the directory searched: what patterns match


class _Walk:
    """The files under a directory. Skips SKIPPED_DIRS, secrets, and links
    that leave the limit: the working directory, or the approved directory
    when the search is outside (spec hito 5, §1.6)."""

    def __init__(self, workspace: Workspace, base: Path) -> None:
        self._workspace = workspace
        self._base = base
        self._inside = workspace.contains(base)
        self._limit = workspace.root if self._inside else base
        self.stopped_early = False

    def _shown(self, path: Path) -> str:
        # A search outside shows every path absolute, also the ones of the
        # working directory.
        return self._workspace.shown(path) if self._inside else str(path)

    async def files(self) -> AsyncIterator[_Found]:
        seen = 0
        workspace = self._workspace
        for dirpath, dirnames, filenames in os.walk(self._base):
            directory = Path(dirpath)
            # Pruned in place, so os.walk does not go into them.
            dirnames[:] = sorted(
                name
                for name in dirnames
                if name not in SKIPPED_DIRS and not workspace.secret(directory / name)
            )
            for name in sorted(filenames):
                seen += 1
                if seen > WALK_MAX_FILES:
                    self.stopped_early = True
                    return
                if seen % WALK_YIELD_EVERY == 0:
                    await asyncio.sleep(0)
                path = directory / name
                real = path.resolve()
                if not real.is_relative_to(self._limit) or workspace.secret(path):
                    continue
                if workspace.secret(real):
                    continue
                in_base = PurePath(path.relative_to(self._base))
                yield _Found(real, self._shown(path), in_base)


def _check_pattern(pattern: str) -> None:
    pure = PurePath(pattern)
    if pure.is_absolute() or ".." in pure.parts:
        raise ToolError("the pattern must be relative, without '..'")


def _check_glob(pattern: str, base: Path, raw: str) -> None:
    _check_pattern(pattern)
    if not base.is_dir():
        raise ToolError(f"not a directory: {raw}")


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
        self._asked = _Asked()

    async def approval(self, params: GlobParams) -> ApprovalRequest | None:
        self._asked.forget()
        base = self._workspace.resolve(params.path)
        # Secrets found while walking are skipped, never asked about.
        warning = self._workspace.warning(base, None)
        if warning is None:
            return None
        _check_glob(params.pattern, base, params.path)
        self._asked.remember(params, base)
        title = f"glob {params.pattern} in {self._workspace.shown(base)}"
        return _request(self.name, title, self._workspace, base, params.path, warning)

    async def run(self, params: GlobParams) -> str:
        base = self._workspace.resolve(params.path)
        self._asked.check(
            params, params.path, base, self._workspace.warning(base, None)
        )
        _check_glob(params.pattern, base, params.path)
        walk = _Walk(self._workspace, base)
        found = [
            file.shown
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
        return _count_lines(result, "(no files match)", "file")


GREP_MAX_MATCHES = 100
GREP_MAX_LINE = 300
# Larger files are not searched: a huge log would block the loop while read.
GREP_MAX_FILE_BYTES = 2 * MIB


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
        self._asked = _Asked()

    async def approval(self, params: GrepParams) -> ApprovalRequest | None:
        self._asked.forget()
        base = self._workspace.resolve(params.path)
        warning = self._warning(base)
        if warning is None:
            return None
        _check_grep(params, base)
        self._asked.remember(params, base)
        title = f'grep "{params.pattern}" in {self._workspace.shown(base)}'
        if params.glob:
            title += f" (glob: {params.glob})"
        return _request(self.name, title, self._workspace, base, params.path, warning)

    def _warning(self, base: Path) -> str | None:
        # One secret file asks, as read_file; a secret directory is walked,
        # and the walk skips its secrets without asking.
        secret = SECRET_FILE if base.is_file() else None
        return self._workspace.warning(base, secret)

    async def run(self, params: GrepParams) -> str:
        base = self._workspace.resolve(params.path)
        self._asked.check(params, params.path, base, self._warning(base))
        regex = _check_grep(params, base)
        if base.is_file():
            with _reading(params.path):
                found = _search(base, self._workspace.shown(base), regex, params.path)
            return _grep_result(found, stopped_early=False)
        walk = _Walk(self._workspace, base)
        matches: list[str] = []
        async for file in walk.files():
            if params.glob and not _glob_matches(file.in_base, params.glob):
                continue
            try:
                matches.extend(_search(file.real, file.shown, regex))
            except OSError:
                # Skipped, as secrets, binary and large files (review of
                # PR 2, fix 8).
                continue
            # One more than shown: it tells whether something was left out.
            if len(matches) > GREP_MAX_MATCHES:
                break
        return _grep_result(matches, stopped_early=walk.stopped_early)

    def summary(self, result: str) -> str:
        return _count_lines(result, "(no matches)", "match", "matches")


def _check_grep(params: GrepParams, base: Path) -> re.Pattern[str]:
    try:
        regex = re.compile(params.pattern)
    except re.error as exc:
        raise ToolError(f"invalid regular expression: {exc}") from None
    if params.glob:
        _check_pattern(params.glob)
    if not base.exists():
        raise ToolError(f"not found: {params.path}")
    if not base.is_dir() and not base.is_file():
        raise ToolError(f"not a regular file: {params.path}")
    if base.is_file():
        with _reading(params.path):
            _check_search_size(base.stat().st_size, params.path)
    return regex


def _check_search_size(size: int, raw: str) -> None:
    if size > GREP_MAX_FILE_BYTES:
        raise ToolError(
            f"file too large to search ({size / MIB:.1f} MiB, "
            f"max {GREP_MAX_FILE_BYTES // MIB} MiB); use run_command"
        )


def _glob_matches(in_base: PurePath, pattern: str) -> bool:
    # Without "/", by file name, as ripgrep does: "*.py" anywhere.
    if "/" not in pattern:
        return fnmatchcase(in_base.name, pattern)
    return in_base.full_match(pattern)


def _search(
    path: Path, shown: str, regex: re.Pattern[str], raw: str | None = None
) -> list[str]:
    """The matching lines of one text file, as "path:line: text".

    With `raw`, the one file the model asked for: what cannot be searched is
    an error, not "(no matches)" (spec mejora-2026-10-23-deuda-hito-5, A4).
    Without it, walking: it is skipped.
    """
    # A FIFO or a device: opening it would block.
    file = _open_regular(path)
    if file is None:
        if raw is None:
            return []
        raise ToolError(f"not a regular file: {raw}")
    found = []
    with _as_text(file) as lines:
        size = os.fstat(file.fileno()).st_size
        binary = size <= GREP_MAX_FILE_BYTES and is_binary(file)
        if raw is not None:
            _check_search_size(size, raw)
            if binary:
                raise ToolError(f"binary file, not searchable: {raw}")
        if size > GREP_MAX_FILE_BYTES or binary:
            return []
        for number, line in enumerate(lines, start=1):
            text = line.rstrip("\r\n")
            if regex.search(text):
                found.append(f"{shown}:{number}: {text[:GREP_MAX_LINE]}")
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


# Writing (spec hito 5, §1.7).

WRITE_PREVIEW_LINES = 20
# The diff shown before an overwrite or an edit (spec hito 5, §1.8).
DIFF_CONTEXT = 3
DIFF_MAX_LINES = 60
# Random names tried for the temporary file before giving up.
TEMP_TRIES = 100
# A larger file is not overwritten or edited: reading it and computing its
# diff would block the loop (review of PR 2, fix 2).
CHANGE_MAX_FILE_BYTES = 2 * MIB


def _split(text: str) -> list[str]:
    """The lines of `text` without their endings, split as `read_file`
    numbers them: at "\n", "\r" or "\r\n"."""
    lines = []
    for line in io.StringIO(text, newline="").readlines():
        if line.endswith("\r\n"):
            line = line[:-2]
        elif line.endswith(("\n", "\r")):
            line = line[:-1]
        lines.append(line)
    return lines


def _preview(text: str) -> str:
    """The first lines of a new file, as the user reads them."""
    lines = _split(text)
    if not lines:
        return "(empty file)"
    shown = lines[:WRITE_PREVIEW_LINES]
    if len(lines) > WRITE_PREVIEW_LINES:
        shown.append(f"… [{len(lines) - WRITE_PREVIEW_LINES} more lines]")
    return "\n".join(shown)


def _diff(old: str, new: str) -> str:
    """A unified diff from `old` to `new`, without the "---"/"+++" header:
    the path is in the title of the question."""
    lines = list(
        difflib.unified_diff(_split(old), _split(new), n=DIFF_CONTEXT, lineterm="")
    )[2:]
    if not lines:
        # Same lines, different bytes: only the line endings change.
        return "(only line endings change)"
    shown = lines[:DIFF_MAX_LINES]
    if len(lines) > DIFF_MAX_LINES:
        shown.append(f"… [{len(lines) - DIFF_MAX_LINES} more diff lines]")
    before, after = _endings(old), _endings(new)
    if before and after and before != after:
        # The diff compares lines without their endings: it would not show it
        # (review of PR 2, fix 4).
        shown.insert(0, f"(line endings change: {before} → {after})")
    return "\n".join(shown)


def _endings(text: str) -> str | None:
    """The line ending style of `text`: "CRLF", "LF", "mixed" (also a lone
    "\r"), or None without line endings."""
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    if cr or (crlf and lf):
        return "mixed"
    if crlf:
        return "CRLF"
    if lf:
        return "LF"
    return None


def _check_target(workspace: Workspace, path: Path, raw: str) -> None:
    """What would make writing `path` fail, found before asking."""
    if path.is_dir():
        raise ToolError(f"is a directory: {raw}")
    if path.exists() and not path.is_file():
        raise ToolError(f"not a regular file: {raw}")
    for parent in path.parents:
        if parent.exists():
            if not parent.is_dir():
                raise ToolError(f"not a directory: {workspace.shown(parent)}")
            return


def _current_bytes(path: Path, raw: str, verb: str) -> bytes | None:
    """The bytes of the file to `verb`, or None if it does not exist.

    Bytes, not text: a question about a secret or a file outside must not
    tell the model whether it is text before the user approves (review of
    PR 2, fix 1); the bytes still let `run()` see a change (decision W6).
    """
    if not path.exists():
        return None
    with _reading(raw):
        file = _open_regular(path)
        if file is None:
            raise ToolError(f"not a regular file: {raw}")
        with file:
            size = os.fstat(file.fileno()).st_size
            if size > CHANGE_MAX_FILE_BYTES:
                raise ToolError(
                    f"file too large to {verb} ({size / MIB:.1f} MiB, "
                    f"max {CHANGE_MAX_FILE_BYTES // MIB} MiB); use run_command"
                )
            return file.read()


def _decode(data: bytes, raw: str) -> str:
    """The text of `data`, read as `newline=""` does: endings as they are."""
    if b"\0" in data[:BINARY_PROBE]:
        raise ToolError(f"binary file, not writable: {raw}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ToolError(f"not a UTF-8 text file: {raw}") from None


def _create_temporary(path: Path) -> tuple[int, Path]:
    """A new hidden file next to `path`, so the rename stays on the same
    file system.

    Created like `open("w")` does, with mode 0o666 and the umask applied by
    the system, not with the 0o600 of `tempfile.mkstemp`. O_EXCL makes the
    name ours; O_NOFOLLOW refuses a link planted with that name.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    for _ in range(TEMP_TRIES):
        # A fixed length: a long name would not fit with a suffix (spec
        # mejora-2026-10-23-deuda-hito-5, D6).
        temporary = path.with_name(f".maha-{secrets.token_hex(8)}.tmp")
        try:
            return os.open(temporary, flags, 0o666), temporary
        except FileExistsError:
            continue
    raise FileExistsError(errno.EEXIST, "no free temporary file name")


def _write_atomically(path: Path, text: str) -> None:
    """Write `text` to `path` in UTF-8, as is: a reader sees the old file or
    the new one, never half of it.

    Written to a temporary file in the same folder, flushed to the disk and
    renamed over `path`; then the folder is flushed too, so the rename
    survives a power cut. An existing file keeps its mode. On any failure, or
    a cancellation, before the rename, the temporary file is removed and
    `path` is untouched.
    """
    try:
        mode: int | None = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = None
    descriptor, temporary = _create_temporary(path)
    try:
        with open(descriptor, "w", encoding="utf-8", newline="") as file:
            if mode is not None:
                os.fchmod(file.fileno(), mode)
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    _sync_folder(path.parent)


def _sync_folder(folder: Path) -> None:
    """Flush the entries of `folder` to the disk (POSIX).

    The fsync of a file does not cover its entry in the folder: the rename
    needs an fsync of the folder too (fsync(2)). A failure is ignored: the
    file is already replaced, and some file systems cannot flush a folder.
    """
    with contextlib.suppress(OSError):
        descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _as_shown(
    workspace: Workspace,
    asked: _Asked,
    params: WriteFileParams | EditFileParams,
    verb: str,
) -> tuple[Path, bytes | None]:
    """The start of `run()` for write_file and edit_file: the same call, the
    same resolved path and the same bytes the question showed (decisions D1
    and W6, review of PR 2, fix 5). Gives the path and its bytes."""
    path = workspace.resolve(params.path)
    if not asked.same(params, path):
        raise _changed(params.path)
    _check_target(workspace, path, params.path)
    data = _current_bytes(path, params.path, verb)
    if data != asked.old:
        raise _changed(params.path)
    return path, data


def _write(workspace: Workspace, path: Path, text: str, *, parents: bool) -> None:
    """Write `text` to `path` atomically; `parents` creates its folders. A
    failure is a clean error (decision A2), and removes the folders it
    created (spec mejora-2026-10-23-deuda-hito-5, D3)."""
    created: list[Path] = []
    try:
        if parents:
            _make_folders(path.parent, created)
        _write_atomically(path, text)
    except BaseException as exc:
        _remove_folders(created)
        if not isinstance(exc, OSError):
            raise
        reason = exc.strerror or str(exc)
        raise ToolError(f"cannot write {workspace.shown(path)}: {reason}") from None


def _make_folders(folder: Path, created: list[Path]) -> None:
    """Create `folder` and its missing parents, outermost first, adding to
    `created` each one as it is made."""
    missing = []
    while not folder.exists():
        missing.append(folder)
        folder = folder.parent
    for new in reversed(missing):
        new.mkdir()
        created.append(new)


def _remove_folders(created: list[Path]) -> None:
    """Remove the folders a failed write created, innermost first, if they
    are still empty."""
    for folder in reversed(created):
        with contextlib.suppress(OSError):
            folder.rmdir()


class WriteFileParams(BaseModel):
    path: str = Field(description="Path relative to the working directory")
    content: str = Field(description="The whole new content of the file")


class WriteFile:
    name = "write_file"
    description = (
        "Create or overwrite a text file in the working directory. The user "
        'approves it first. Example: {"path": "notes.txt", "content": "…"}'
    )
    params = WriteFileParams
    permission: Permission = "effect"

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace
        self._asked = _Asked()

    async def approval(self, params: WriteFileParams) -> ApprovalRequest | None:
        self._asked.forget()
        workspace = self._workspace
        path = workspace.resolve(params.path)
        _check_target(workspace, path, params.path)
        try:
            params.content.encode("utf-8")
        except UnicodeEncodeError:
            raise ToolError("content is not valid UTF-8") from None
        warning = change_warning(path, workspace.root)
        data = _current_bytes(path, params.path, "overwrite")
        shown = workspace.shown(path)
        if data is None:
            lines = _count(len(_split(params.content)), "line")
            title = f"create {shown} ({lines})"
            body = _preview(params.content)
        else:
            title = f"overwrite {shown}"
            try:
                body = _diff(_old_text(data, params), params.content)
            except ToolError:
                # With a warning, what depends on the content waits for the
                # approval (review of PR 2, fix 1).
                if warning is None:
                    raise
                body = _preview(params.content)
        detail = body if params.path == shown else f"(asked: {params.path})\n{body}"
        self._asked.remember(params, path, data)
        return ApprovalRequest(
            tool=self.name,
            title=title,
            detail=detail,
            scope=self.name if warning is None else None,
            warning=warning,
        )

    async def run(self, params: WriteFileParams) -> str:
        workspace = self._workspace
        path, data = _as_shown(workspace, self._asked, params, "overwrite")
        if data is not None:
            _old_text(data, params)
        _write(workspace, path, params.content, parents=True)
        lines = _count(len(_split(params.content)), "line")
        return f"wrote {workspace.shown(path)} ({lines})"

    def summary(self, result: str) -> str:
        # "wrote notas.txt (3 lines)" → "3 lines".
        return result[result.rfind("(") + 1 : -1]


def _old_text(data: bytes, params: WriteFileParams) -> str:
    """The text that `params` overwrites; the errors that depend on it."""
    old = _decode(data, params.path)
    if old == params.content:
        raise ToolError("nothing to change")
    return old


# Editing (spec hito 5, §1.8).

# A "\n" with no "\r" before it.
_LONE_LF = re.compile(r"(?<!\r)\n")


class EditFileParams(BaseModel):
    path: str = Field(description="Path relative to the working directory")
    old_string: str = Field(description="The exact text to replace")
    new_string: str = Field(description="The text to put in its place")
    replace_all: bool = Field(
        default=False, description="Replace every occurrence of old_string"
    )


def _check_strings(params: EditFileParams) -> None:
    """What is wrong with the strings alone, found before the disk."""
    if not params.old_string:
        raise ToolError("old_string is empty")
    if params.old_string == params.new_string:
        raise ToolError("nothing to change")
    try:
        params.new_string.encode("utf-8")
    except UnicodeEncodeError:
        raise ToolError("new_string is not valid UTF-8") from None


def _replaced(text: str, params: EditFileParams) -> tuple[str, int]:
    """`text` after the edit, and how many replacements it makes.

    Exact matches first. With none, in a file with CRLF, the lone "\\n" of
    both strings become "\\r\\n": the model sees the lines without their
    endings (decision 9b).
    """
    old, new = params.old_string, params.new_string
    found = text.count(old)
    if found == 0 and "\r\n" in text and _LONE_LF.search(old):
        old = _LONE_LF.sub("\r\n", old)
        new = _LONE_LF.sub("\r\n", new)
        found = text.count(old)
    if found == 0:
        raise ToolError(
            f"old_string not found in {params.path}; "
            "read the file and copy the text exactly"
        )
    if found > 1 and not params.replace_all:
        raise ToolError(
            f"old_string appears {found} times in {params.path}; "
            "add context to make it unique or use replace_all"
        )
    return text.replace(old, new), found


def _edited(data: bytes, params: EditFileParams) -> tuple[str, str, int]:
    """The text before and after the edit, and how many replacements; the
    errors that depend on the content."""
    old = _decode(data, params.path)
    new, found = _replaced(old, params)
    if new == old:
        # Possible after adapting to CRLF: "a\n" for "a\r\n" (decision C).
        raise ToolError("nothing to change")
    return old, new, found


def _strings(params: EditFileParams) -> str:
    """The strings of the call, for a question that cannot derive anything
    from the content (review of PR 2, fix 1)."""
    lines = ["old_string:", *_split(params.old_string)]
    lines += ["new_string:", *_split(params.new_string)]
    if params.replace_all:
        lines.append("replace_all: true")
    shown = lines[:DIFF_MAX_LINES]
    if len(lines) > DIFF_MAX_LINES:
        shown.append(f"… [{len(lines) - DIFF_MAX_LINES} more lines]")
    return "\n".join(shown)


class EditFile:
    name = "edit_file"
    description = (
        "Replace an exact text in a file. old_string must appear exactly once "
        "(or use replace_all). Read the file first. The user approves it. "
        'Example: {"path": "app.py", "old_string": "return 1", '
        '"new_string": "return 2"}'
    )
    params = EditFileParams
    permission: Permission = "effect"

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace
        self._asked = _Asked()

    async def approval(self, params: EditFileParams) -> ApprovalRequest | None:
        self._asked.forget()
        _check_strings(params)
        workspace = self._workspace
        path = workspace.resolve(params.path)
        _check_target(workspace, path, params.path)
        data = _current_bytes(path, params.path, "edit")
        if data is None:
            raise ToolError(f"file not found: {params.path}")
        warning = change_warning(path, workspace.root)
        try:
            old, new, _ = _edited(data, params)
            body = _diff(old, new)
        except ToolError:
            # With a warning, what depends on the content waits for the
            # approval (review of PR 2, fix 1).
            if warning is None:
                raise
            body = _strings(params)
        shown = workspace.shown(path)
        detail = body if params.path == shown else f"(asked: {params.path})\n{body}"
        self._asked.remember(params, path, data)
        return ApprovalRequest(
            tool=self.name,
            title=f"edit {shown}",
            detail=detail,
            scope=self.name if warning is None else None,
            warning=warning,
        )

    async def run(self, params: EditFileParams) -> str:
        workspace = self._workspace
        path, data = _as_shown(workspace, self._asked, params, "edit")
        if data is None:
            # approval() refuses a missing file, so it appeared.
            raise _changed(params.path)
        _, new, found = _edited(data, params)
        _write(workspace, path, new, parents=False)
        return f"edited {workspace.shown(path)} ({_count(found, 'replacement')})"

    def summary(self, result: str) -> str:
        # "edited app.py (1 replacement)" → "1 replacement".
        return result[result.rfind("(") + 1 : -1]
