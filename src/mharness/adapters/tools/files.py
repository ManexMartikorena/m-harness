"""Read-only tools over the working directory (spec hito 4, §1.6).

Every path is resolved (following symbolic links) and must stay inside the
working directory; secret files are refused. No threads: a thread blocked on
the disk would keep `maha` from exiting on Ctrl+C (spec hito 2, §12).
"""

import re
from pathlib import Path, PurePath
from typing import IO

from pydantic import BaseModel, Field

from mharness.domain.paths import is_secret
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
